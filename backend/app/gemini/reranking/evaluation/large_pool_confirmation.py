"""Confirm the shipped names-plus-genres format at 2,000 games (Phase F).

Unlike the E3 format comparison, every request here goes through the product
path: `RerankRequest` with `candidate_format="names_genres"`, the product
system instruction, serializer, and strict response validation. Candidates
carry the same headline score the cards show, so the run also measures
whether Reasoning cites a supplied fact and never invents one.
"""

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import re
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gemini.client import GeminiAPIError, GeminiClient
from app.gemini.reranking.contracts import (
    RerankCandidate,
    RerankFilters,
    RerankRequest,
)
from app.gemini.reranking.evaluation.candidate_formats import (
    FORMAT_PROMPTS,
    CatalogueGame,
    TokenPacer,
    build_pool,
    load_catalogue,
)
from app.gemini.reranking.evaluation.harness import (
    elapsed_ms,
    evaluation_error_code,
)
from app.gemini.reranking.projection import (
    NAMES_GENRES_PROJECTION,
    project_rerank_candidates,
)
from app.gemini.reranking.reranker import (
    MAX_RERANK_OUTPUT_TOKENS,
    MAX_RERANK_REQUEST_BYTES,
    RerankRequestTooLarge,
    RerankResponseError,
    rerank_user_prompt_size_bytes,
    rerank_with_metadata,
)
from app.models import Game
from app.recommendations.ratings import (
    RATING_COLUMNS,
    RatingSource,
    game_ratings,
)

CONFIRMATION_VERSION = "rerank-large-pool-confirmation-v1"
CONFIRMATION_MODEL = "gemini-3.5-flash-lite"
CONFIRMATION_POOL_SIZE = 2_000
CONFIRMATION_REPEATS = 2
ESTIMATED_BYTES_PER_TOKEN = 3
_SCORE_PATTERN = re.compile(r"\b(\d{2,3})\b")


def load_headline_scores(session: Session) -> dict[int, tuple[str, int]]:
    """Map ready games to their card headline score, if any."""
    scores: dict[int, tuple[str, int]] = {}
    for row in session.execute(
        select(Game.steam_app_id, *RATING_COLUMNS).where(
            Game.igdb_status == "ready"
        )
    ):
        headline = game_ratings(row).headline
        if headline is not None:
            field = (
                "critic_score"
                if headline.source is RatingSource.CRITICS
                else "igdb_rating"
            )
            scores[row.steam_app_id] = (field, headline.score)
    return scores


def build_request(
    pool: Sequence[CatalogueGame],
    scores: dict[int, tuple[str, int]],
    prompt: str,
) -> RerankRequest:
    """Build the exact product request for one large whole-library pool."""
    candidates = tuple(
        RerankCandidate(
            steam_app_id=game.steam_app_id,
            title=game.title,
            genres=game.genres or ("Unknown",),
            themes=(),
            keywords=(),
            game_modes=(),
            profile_playtime_minutes=0,
            **(
                {scores[game.steam_app_id][0]: scores[game.steam_app_id][1]}
                if game.steam_app_id in scores
                else {}
            ),
        )
        for game in pool
    )
    return RerankRequest(
        prompt=prompt,
        filters=RerankFilters(),
        candidates=project_rerank_candidates(candidates, NAMES_GENRES_PROJECTION),
        candidate_format="names_genres",
    )


@dataclass(frozen=True)
class FactCheck:
    """Describe how one pick's reasoning used the supplied score."""

    steam_app_id: int
    title: str
    supplied_score: int | None
    cited_supplied_score: bool
    unsupported_numbers: tuple[int, ...]
    reasoning: str


def check_facts(
    reasoning: str,
    steam_app_id: int,
    title: str,
    scores: dict[int, tuple[str, int]],
) -> FactCheck:
    """Find the supplied score in reasoning and flag any other score."""
    supplied = scores.get(steam_app_id, (None, None))[1]
    title_numbers = {int(value) for value in _SCORE_PATTERN.findall(title)}
    numbers = [int(value) for value in _SCORE_PATTERN.findall(reasoning)]
    # Two- and three-digit numbers up to 100 read as scores; others (years,
    # hours) are not judged here.
    unsupported = tuple(
        number
        for number in numbers
        if 10 <= number <= 100
        and number != supplied
        and number not in title_numbers
    )
    return FactCheck(
        steam_app_id=steam_app_id,
        title=title,
        supplied_score=supplied,
        cited_supplied_score=supplied is not None and supplied in numbers,
        unsupported_numbers=unsupported,
        reasoning=reasoning,
    )


@dataclass(frozen=True)
class ConfirmationResult:
    prompt_id: str
    repeat: int
    status: str
    request_bytes: int
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    fit_share: float | None
    synthetic_picks: int
    facts: tuple[FactCheck, ...]
    error_code: str | None


@dataclass(frozen=True)
class ConfirmationReport:
    evaluation_version: str
    model_id: str
    started_at: str
    completed_at: str
    call_count: int
    pool_size: int
    real_games: int
    scored_real_games: int
    results: tuple[ConfirmationResult, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def plan_request_sizes(
    catalogue: Sequence[CatalogueGame],
    scores: dict[int, tuple[str, int]],
) -> dict[str, int]:
    """Measure each prompt's exact product request without calling Gemini."""
    pool = build_pool(catalogue, CONFIRMATION_POOL_SIZE)
    return {
        prompt.prompt_id: rerank_user_prompt_size_bytes(
            build_request(pool, scores, prompt.text)
        )
        for prompt in FORMAT_PROMPTS
    }


def run_confirmation(
    client: GeminiClient,
    catalogue: Sequence[CatalogueGame],
    scores: dict[int, tuple[str, int]],
    *,
    model_id: str = CONFIRMATION_MODEL,
    pacer: TokenPacer | None = None,
    clock: Callable[[], float] = monotonic,
    max_calls: int = 8,
) -> ConfirmationReport:
    """Make 4 prompts × 2 repeats through the product request path."""
    pacer = pacer or TokenPacer()
    pool = build_pool(catalogue, CONFIRMATION_POOL_SIZE)
    pool_by_id = {game.steam_app_id: game for game in pool}
    started_at = datetime.now(UTC).isoformat()
    results: list[ConfirmationResult] = []
    calls = 0

    for repeat in range(1, CONFIRMATION_REPEATS + 1):
        for prompt in FORMAT_PROMPTS:
            request = build_request(pool, scores, prompt.text)
            request_bytes = rerank_user_prompt_size_bytes(request)
            if request_bytes > MAX_RERANK_REQUEST_BYTES:
                results.append(
                    ConfirmationResult(
                        prompt.prompt_id, repeat, "too_large", request_bytes,
                        None, None, None, None, 0, (), "payload_too_large",
                    )
                )
                continue
            if calls >= max_calls:
                raise RuntimeError("The run exceeds the approved call budget.")
            entry = pacer.wait_for(
                request_bytes // ESTIMATED_BYTES_PER_TOKEN
                + MAX_RERANK_OUTPUT_TOKENS
            )
            calls += 1
            started = clock()
            try:
                response, metadata = rerank_with_metadata(
                    client,
                    model_id=model_id,
                    request=request,
                )
            except (
                GeminiAPIError,
                RerankRequestTooLarge,
                RerankResponseError,
            ) as error:
                results.append(
                    ConfirmationResult(
                        prompt.prompt_id, repeat, "failed", request_bytes,
                        None, None, elapsed_ms(clock, started), None, 0, (),
                        evaluation_error_code(error),
                    )
                )
                continue
            pacer.settle(
                entry,
                None
                if metadata.input_tokens is None
                else metadata.input_tokens + (metadata.output_tokens or 0),
            )
            picks = [pool_by_id[item.steam_app_id] for item in response.recommendations]
            fits = [prompt.fits(game) for game in picks]
            facts = tuple(
                check_facts(
                    item.reasoning,
                    item.steam_app_id,
                    pool_by_id[item.steam_app_id].title,
                    scores,
                )
                for item in response.recommendations
            )
            results.append(
                ConfirmationResult(
                    prompt.prompt_id, repeat, response.status.value,
                    request_bytes, metadata.input_tokens, metadata.output_tokens,
                    elapsed_ms(clock, started),
                    sum(fits) / len(fits) if fits else None,
                    sum(1 for game in picks if game.synthetic),
                    facts, None,
                )
            )

    real = [game for game in pool if not game.synthetic]
    return ConfirmationReport(
        evaluation_version=CONFIRMATION_VERSION,
        model_id=model_id,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        call_count=calls,
        pool_size=len(pool),
        real_games=len(real),
        scored_real_games=sum(1 for game in real if game.steam_app_id in scores),
        results=tuple(results),
    )


__all__ = [
    "build_request",
    "check_facts",
    "load_catalogue",
    "load_headline_scores",
    "plan_request_sizes",
    "run_confirmation",
]
