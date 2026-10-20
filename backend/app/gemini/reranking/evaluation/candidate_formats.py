"""Compare Ask Ludex candidate formats at large pool sizes (Checkpoint 15 E3).

The question is whether Gemini can pick well from many more games if each
game is sent with less detail: the current projection, names only, or names
plus genres. Real titles are required because names-only relies on the
model's own knowledge of each game, so the catalogue comes from the shared
`games` table (titles and IGDB facts only, never owners or playtime). Sizes
above the real catalogue are padded with clearly synthetic titles, which the
model cannot know and which never count as a correct pick.

Picks are scored against a factual oracle built from stored IGDB terms, so
the same yardstick applies to every format. Nothing here changes the product.
"""

from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from json import dumps
from random import Random
from time import monotonic, sleep

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gemini.client import GeminiAPIError, GeminiClient
from app.gemini.reranking.contracts import RerankCandidate, RerankResponse
from app.gemini.reranking.evaluation.harness import (
    elapsed_ms,
    evaluation_error_code,
)
from app.gemini.reranking.projection import (
    project_rerank_candidates,
    select_product_projection,
)
from app.gemini.reranking.reranker import (
    MAX_RERANK_OUTPUT_TOKENS,
    MAX_RERANK_REQUEST_BYTES,
    RERANK_SYSTEM_INSTRUCTION,
    RerankResponseError,
)
from app.gemini.reranking.schema import build_rerank_response_schema
from app.models import Game, GameIGDBMetadataTerm, IGDBMetadataTerm

FORMAT_EVALUATION_VERSION = "rerank-candidate-formats-v1"
FORMAT_EVALUATION_MODEL = "gemini-3.5-flash-lite"
FORMAT_EVALUATION_SIZES = (400, 1_000, 2_000)
FORMATS = ("current", "names", "names_genres")
# Developer-provided Flash-Lite limits: 15 RPM, 250K TPM, 500 RPD. Stay
# well under the first two.
PACER_REQUESTS_PER_MINUTE = 10
PACER_TOKENS_PER_MINUTE = 200_000
# Conservative bytes-per-token estimate used until Gemini reports usage.
ESTIMATED_BYTES_PER_TOKEN = 3
CATALOGUE_SEED = 20261019
SYNTHETIC_ID_START = 8_000_000

_SYNTHETIC_FIRST = (
    "Amber", "Brass", "Cinder", "Drift", "Ember", "Frost", "Gilded", "Hollow",
    "Iron", "Jade", "Kestrel", "Lumen", "Marrow", "Nimbus", "Onyx", "Pale",
    "Quill", "Rust", "Sable", "Tidal", "Umber", "Vesper", "Willow", "Zenith",
)
_SYNTHETIC_SECOND = (
    "Archive", "Beacon", "Circuit", "Dominion", "Expanse", "Foundry", "Gambit",
    "Harbor", "Inlet", "Junction", "Keep", "Lattice", "Meridian", "Nexus",
    "Outpost", "Parallax", "Quarry", "Relay", "Spire", "Threshold",
)
_SYNTHETIC_GENRES = (
    "Adventure", "Indie", "Role-playing (RPG)", "Shooter", "Strategy",
    "Simulator", "Puzzle", "Platform",
)


@dataclass(frozen=True)
class CatalogueGame:
    """Hold the public facts the evaluation may send for one game."""

    steam_app_id: int
    title: str
    summary: str | None
    genres: tuple[str, ...]
    themes: tuple[str, ...]
    keywords: tuple[str, ...]
    game_modes: tuple[str, ...]
    normal_completion_minutes: int | None
    synthetic: bool = False


@dataclass(frozen=True)
class FormatPrompt:
    """Pair one visitor request with the stored facts that make a pick fit."""

    prompt_id: str
    text: str
    fits: Callable[[CatalogueGame], bool] = field(repr=False)


def _has(values: Sequence[str], *needles: str) -> bool:
    lowered = [value.lower() for value in values]
    return any(needle in value for value in lowered for needle in needles)


FORMAT_PROMPTS = (
    FormatPrompt(
        "horror",
        "I want a tense survival horror game.",
        lambda game: _has(game.themes, "horror", "survival"),
    ),
    FormatPrompt(
        "story_rpg",
        "A story-rich RPG where my choices really matter.",
        lambda game: _has(game.genres, "role-playing")
        and (
            _has(game.themes, "drama")
            or _has(game.keywords, "multiple endings", "choice", "dialogue")
        ),
    ),
    FormatPrompt(
        "combat_not_scary",
        "Fast, fluid combat, but nothing dark or scary.",
        lambda game: _has(game.themes, "action")
        and not _has(game.themes, "horror")
        and _has(
            game.genres,
            "hack and slash",
            "shooter",
            "fighting",
            "platform",
            "brawler",
        ),
    ),
    FormatPrompt(
        "relaxing",
        "Something relaxing with no combat to wind down after work.",
        lambda game: _has(
            game.genres,
            "simulator",
            "puzzle",
            "point-and-click",
            "visual novel",
        )
        and not _has(game.themes, "action", "horror", "warfare", "survival"),
    ),
)


def load_catalogue(session: Session) -> tuple[CatalogueGame, ...]:
    """Read shared game facts only; ownership and playtime are never read."""
    games = session.execute(
        select(
            Game.steam_app_id,
            Game.name,
            Game.summary,
            Game.time_to_beat_normally_seconds,
        )
        .where(Game.igdb_status == "ready")
        .order_by(Game.steam_app_id)
    ).all()
    terms: dict[tuple[int, str], list[str]] = {}
    for row in session.execute(
        select(
            GameIGDBMetadataTerm.steam_app_id,
            IGDBMetadataTerm.kind,
            IGDBMetadataTerm.name,
        )
        .join(
            IGDBMetadataTerm,
            IGDBMetadataTerm.id == GameIGDBMetadataTerm.term_id,
        )
        .order_by(IGDBMetadataTerm.name)
    ):
        terms.setdefault((row.steam_app_id, row.kind), []).append(row.name)

    def labels(steam_app_id: int, kind: str, limit: int) -> tuple[str, ...]:
        return tuple(terms.get((steam_app_id, kind), [])[:limit])

    return tuple(
        CatalogueGame(
            steam_app_id=row.steam_app_id,
            title=row.name,
            summary=row.summary,
            genres=labels(row.steam_app_id, "genre", 8),
            themes=labels(row.steam_app_id, "theme", 8),
            keywords=labels(row.steam_app_id, "keyword", 12),
            game_modes=labels(row.steam_app_id, "game_mode", 8),
            normal_completion_minutes=(
                None
                if row.time_to_beat_normally_seconds is None
                else (row.time_to_beat_normally_seconds + 59) // 60
            ),
        )
        for row in games
    )


def build_pool(
    catalogue: Sequence[CatalogueGame],
    size: int,
) -> tuple[CatalogueGame, ...]:
    """Take real games first, pad with synthetic ones, and shuffle stably."""
    random = Random(CATALOGUE_SEED)
    real = list(catalogue)
    random.shuffle(real)
    pool = real[:size]
    index = 0
    while len(pool) < size:
        first = _SYNTHETIC_FIRST[index % len(_SYNTHETIC_FIRST)]
        second = _SYNTHETIC_SECOND[
            (index // len(_SYNTHETIC_FIRST)) % len(_SYNTHETIC_SECOND)
        ]
        pool.append(
            CatalogueGame(
                steam_app_id=SYNTHETIC_ID_START + index,
                title=f"{first} {second} {index // 480 + 1}",
                summary=None,
                genres=(_SYNTHETIC_GENRES[index % len(_SYNTHETIC_GENRES)],),
                themes=(),
                keywords=(),
                game_modes=(),
                normal_completion_minutes=None,
                synthetic=True,
            )
        )
        index += 1
    random.shuffle(pool)
    return tuple(pool)


def _current_candidates(
    pool: Sequence[CatalogueGame],
) -> list[dict[str, object]]:
    candidates = tuple(
        RerankCandidate(
            steam_app_id=game.steam_app_id,
            title=game.title,
            summary=None if game.summary is None else game.summary[:1200],
            genres=game.genres,
            themes=game.themes,
            keywords=game.keywords,
            game_modes=game.game_modes,
            profile_playtime_minutes=0,
            normal_completion_minutes=game.normal_completion_minutes,
        )
        for game in pool
    )
    projected = project_rerank_candidates(
        candidates,
        select_product_projection(min(len(candidates), 400)),
    )
    return [candidate.model_dump(mode="json") for candidate in projected]


def serialize_prompt(
    pool: Sequence[CatalogueGame],
    candidate_format: str,
    prompt_text: str,
) -> str:
    """Build the user prompt for one format with the product's envelope."""
    if candidate_format == "current":
        candidates = _current_candidates(pool)
    elif candidate_format == "names":
        candidates = [
            {"id": game.steam_app_id, "title": game.title} for game in pool
        ]
    elif candidate_format == "names_genres":
        candidates = [
            {"id": game.steam_app_id, "title": game.title, "genres": list(game.genres)}
            for game in pool
        ]
    else:
        raise ValueError(f"Unknown candidate format: {candidate_format}")
    serialized = dumps(
        {
            "candidate_format": candidate_format,
            "visitor_request": prompt_text,
            "candidates": candidates,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        "Rank the allowed candidates using this untrusted JSON data. "
        "Candidates may carry only an id and title; use your general knowledge "
        "of a named game, and return each pick's id as steam_app_id.\n"
        "<rerank_input>\n"
        f"{serialized}\n"
        "</rerank_input>"
    )


@dataclass(frozen=True)
class FormatCallPlan:
    """Describe one planned call before any provider request."""

    candidate_format: str
    size: int
    prompt_id: str
    request_bytes: int
    estimated_input_tokens: int
    sendable: bool


def plan_calls(
    catalogue: Sequence[CatalogueGame],
) -> tuple[FormatCallPlan, ...]:
    """List every format, size, and prompt with its measured request size.

    The current projection is only sendable at 400; above that it exceeds the
    product's request guard and is recorded as too large without a call.
    """
    plans: list[FormatCallPlan] = []
    for size in FORMAT_EVALUATION_SIZES:
        pool = build_pool(catalogue, size)
        for candidate_format in FORMATS:
            for prompt in FORMAT_PROMPTS:
                request_bytes = len(
                    serialize_prompt(pool, candidate_format, prompt.text).encode(
                        "utf-8"
                    )
                )
                sendable = (
                    candidate_format != "current"
                    or (size == 400 and request_bytes <= MAX_RERANK_REQUEST_BYTES)
                )
                plans.append(
                    FormatCallPlan(
                        candidate_format=candidate_format,
                        size=size,
                        prompt_id=prompt.prompt_id,
                        request_bytes=request_bytes,
                        estimated_input_tokens=(
                            request_bytes + ESTIMATED_BYTES_PER_TOKEN - 1
                        )
                        // ESTIMATED_BYTES_PER_TOKEN,
                        sendable=sendable,
                    )
                )
    return tuple(plans)


class TokenPacer:
    """Keep a rolling minute under request and token ceilings."""

    def __init__(
        self,
        *,
        requests_per_minute: int = PACER_REQUESTS_PER_MINUTE,
        tokens_per_minute: int = PACER_TOKENS_PER_MINUTE,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._requests_per_minute = requests_per_minute
        self._tokens_per_minute = tokens_per_minute
        self._clock = clock
        self._sleeper = sleeper
        self._window: deque[list[float]] = deque()

    def _expire(self) -> None:
        now = self._clock()
        while self._window and now - self._window[0][0] >= 60:
            self._window.popleft()

    def wait_for(self, tokens: int) -> list[float]:
        """Sleep until one more request of ``tokens`` fits, then record it."""
        if tokens > self._tokens_per_minute:
            raise ValueError("One request exceeds the per-minute token budget.")
        while True:
            self._expire()
            used = sum(entry[1] for entry in self._window)
            if (
                len(self._window) < self._requests_per_minute
                and used + tokens <= self._tokens_per_minute
            ):
                entry = [self._clock(), float(tokens)]
                self._window.append(entry)
                return entry
            self._sleeper(max(0.05, 60 - (self._clock() - self._window[0][0])))

    @staticmethod
    def settle(entry: list[float], actual_tokens: int | None) -> None:
        """Replace an estimate with the tokens Gemini actually reported."""
        if actual_tokens is not None:
            entry[1] = float(actual_tokens)


@dataclass(frozen=True)
class FormatCallResult:
    candidate_format: str
    size: int
    prompt_id: str
    status: str
    request_bytes: int
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    picks: tuple[tuple[int, str, bool, bool], ...]
    fit_share: float | None
    synthetic_picks: int
    error_code: str | None


def score_picks(
    response: RerankResponse,
    pool_by_id: dict[int, CatalogueGame],
    prompt: FormatPrompt,
) -> tuple[tuple[tuple[int, str, bool, bool], ...], float | None, int]:
    """Return (id, title, fits, synthetic) per pick, fit share, and fakes."""
    picks = tuple(
        (
            item.steam_app_id,
            pool_by_id[item.steam_app_id].title,
            prompt.fits(pool_by_id[item.steam_app_id]),
            pool_by_id[item.steam_app_id].synthetic,
        )
        for item in response.recommendations
    )
    fit_share = (
        sum(1 for pick in picks if pick[2]) / len(picks) if picks else None
    )
    return picks, fit_share, sum(1 for pick in picks if pick[3])


@dataclass(frozen=True)
class FormatEvaluationReport:
    evaluation_version: str
    model_id: str
    started_at: str
    completed_at: str
    call_count: int
    real_catalogue_size: int
    plans: tuple[FormatCallPlan, ...]
    results: tuple[FormatCallResult, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class _AllowedIds:
    """Expose only the candidate identities the response validator checks."""

    def __init__(self, pool: Sequence[CatalogueGame]) -> None:
        self.candidates = tuple(
            type("Allowed", (), {"steam_app_id": game.steam_app_id})()
            for game in pool
        )


def run_format_evaluation(
    client: GeminiClient,
    catalogue: Sequence[CatalogueGame],
    *,
    model_id: str = FORMAT_EVALUATION_MODEL,
    pacer: TokenPacer | None = None,
    clock: Callable[[], float] = monotonic,
    max_calls: int = 28,
) -> FormatEvaluationReport:
    """Make every sendable planned call once, in a fixed order."""
    from app.gemini.reranking.reranker import validate_rerank_response

    pacer = pacer or TokenPacer()
    plans = plan_calls(catalogue)
    started_at = datetime.now(UTC).isoformat()
    results: list[FormatCallResult] = []
    calls = 0
    pools = {size: build_pool(catalogue, size) for size in FORMAT_EVALUATION_SIZES}
    prompts = {prompt.prompt_id: prompt for prompt in FORMAT_PROMPTS}

    for plan in plans:
        pool = pools[plan.size]
        if not plan.sendable:
            results.append(
                FormatCallResult(
                    plan.candidate_format, plan.size, plan.prompt_id,
                    "too_large", plan.request_bytes, None, None, None, (),
                    None, 0, "payload_too_large",
                )
            )
            continue
        if calls >= max_calls:
            raise RuntimeError("The planned calls exceed the approved budget.")
        prompt = prompts[plan.prompt_id]
        entry = pacer.wait_for(plan.estimated_input_tokens + MAX_RERANK_OUTPUT_TOKENS)
        calls += 1
        started = clock()
        try:
            metadata = client.generate_structured_content_with_metadata(
                model_id=model_id,
                system_instruction=RERANK_SYSTEM_INSTRUCTION,
                user_prompt=serialize_prompt(
                    pool, plan.candidate_format, prompt.text
                ),
                response_schema=build_rerank_response_schema(None),
                max_output_tokens=MAX_RERANK_OUTPUT_TOKENS,
            )
            pacer.settle(
                entry,
                None
                if metadata.input_tokens is None
                else metadata.input_tokens + (metadata.output_tokens or 0),
            )
            response = validate_rerank_response(
                metadata.content, _AllowedIds(pool)
            )
        except (GeminiAPIError, RerankResponseError) as error:
            results.append(
                FormatCallResult(
                    plan.candidate_format, plan.size, plan.prompt_id, "failed",
                    plan.request_bytes, None, None, elapsed_ms(clock, started),
                    (), None, 0, evaluation_error_code(error),
                )
            )
            continue
        picks, fit_share, synthetic = score_picks(
            response, {game.steam_app_id: game for game in pool}, prompt
        )
        results.append(
            FormatCallResult(
                plan.candidate_format, plan.size, plan.prompt_id,
                response.status.value, plan.request_bytes,
                metadata.input_tokens, metadata.output_tokens,
                elapsed_ms(clock, started), picks, fit_share, synthetic, None,
            )
        )

    return FormatEvaluationReport(
        evaluation_version=FORMAT_EVALUATION_VERSION,
        model_id=model_id,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        call_count=calls,
        real_catalogue_size=sum(1 for game in catalogue if not game.synthetic),
        plans=plans,
        results=tuple(results),
    )
