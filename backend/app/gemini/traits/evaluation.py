from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import monotonic, sleep
from typing import Callable

from sqlalchemy.orm import Session

from app.gemini.client import (
    GeminiAPIError,
    GeminiClient,
    GeminiRateLimitError,
    GeminiStructuredContent,
    GeminiUnavailableError,
)
from app.gemini.traits.classifier import (
    GameTraitBatchClassification,
    GameTraitBatchEnvelopeError,
    validate_game_trait_batch_response,
)
from app.gemini.traits.contracts import (
    NUMERIC_TRAIT_FIELDS,
    GameTraitBatchRequestItem,
    GameTraitResponse,
    calculate_facts_fingerprint,
)
from app.gemini.traits.planning import load_game_trait_generation_plan
from app.gemini.traits.prompt import (
    GAME_TRAIT_SYSTEM_INSTRUCTION,
    MAX_GAME_TRAIT_BATCH_OUTPUT_TOKENS,
    build_game_trait_batch_user_prompt,
)


TRAIT_EVALUATION_VERSION = "trait-evaluation-v2-two-game"
TRAIT_EVALUATION_BATCH_SIZE = 2
TRAIT_EVALUATION_MAX_CALLS = 11


@dataclass(frozen=True)
class HumanTraitReference:
    steam_app_id: int
    name: str
    facts_fingerprint: str
    numeric_targets: tuple[int | None, ...]
    defensible_moods: tuple[str, ...]


@dataclass(frozen=True)
class TraitEvaluationGame:
    reference: HumanTraitReference
    request_item: GameTraitBatchRequestItem


@dataclass(frozen=True)
class TraitEvaluationGameResult:
    steam_app_id: int
    name: str
    status: str
    numeric_values: tuple[int | None, ...]
    moods: tuple[str, ...]
    numeric_matches: int
    numeric_reference_count: int
    unsupported_assertions: int
    reviewed_assertion_count: int
    defensible_moods: int
    returned_moods: int
    error_code: str | None


@dataclass(frozen=True)
class TraitEvaluationBatchResult:
    batch_id: str
    repeat_of: str | None
    attempts: int
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    unexpected_steam_app_ids: tuple[int, ...]
    games: tuple[TraitEvaluationGameResult, ...]
    error_code: str | None


@dataclass(frozen=True)
class TraitEvaluationReport:
    evaluation_version: str
    model_id: str
    started_at: str
    completed_at: str
    call_budget: int
    call_count: int
    stopped_early: bool
    numeric_agreement_basis_points: int
    unsupported_assertion_basis_points: int
    mood_agreement_basis_points: int
    evidence_verification_pass: bool
    repeat_consistency_pass: bool
    overall_pass: bool
    batches: tuple[TraitEvaluationBatchResult, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


TRAIT_EVALUATION_REFERENCES = (
    HumanTraitReference(
        730,
        "Counter-Strike 2",
        "ac7cfa447ddae71852bc4e3a4c99064fcfbc024ef9710c0c0cac0972cdf655ae",
        (0, 4, 4, 4, 4, 1),
        ("tense",),
    ),
    HumanTraitReference(
        4000,
        "Garry's Mod",
        "fd0a036982789d101663a9a16d9c22e3ddb8658f9f24b96f0b812b47a1a44a92",
        (0, None, None, None, None, 3),
        ("humorous",),
    ),
    HumanTraitReference(
        7670,
        "BioShock",
        "c3328a01e0ff9800306ff8dc3249a36dbfaf076fa2fbcc6bd7946e62a482abe7",
        (4, 4, 3, 3, 3, 3),
        ("dark", "tense"),
    ),
    HumanTraitReference(
        8930,
        "Sid Meier's Civilization V",
        "d2a0dfbeb91f1cd036919231ac37513e2ba973985cc795b02a24a98eb58b55d1",
        (1, 2, 3, 1, 1, 3),
        (),
    ),
    HumanTraitReference(
        105600,
        "Terraria",
        "3ca3d3b8b78ae22a99965ea7e074a94287f63e429822f0df7fc2d65515e51e1c",
        (1, 3, 3, 3, 3, 4),
        ("dark", "tense"),
    ),
    HumanTraitReference(
        268910,
        "Cuphead",
        "33b155d65476077cf29740c06e85919cbedb73ff411f0952dcdfe50e20d127c7",
        (1, 5, 4, 4, 4, 1),
        ("humorous", "tense"),
    ),
    HumanTraitReference(
        413150,
        "Stardew Valley",
        "2f40037ba21cab9ba00179bc1bf3b0a6e7cc9d97cde4ea4e28088c455ab59c95",
        (2, 1, 2, 1, 3, 3),
        ("emotional", "relaxing"),
    ),
    HumanTraitReference(
        632360,
        "Risk of Rain 2",
        "bfbbfca0e058f5a63d26de736ad3014a635c3a0879eccc53535b5a6beb909ff5",
        (1, 5, 4, 5, 4, 2),
        ("tense",),
    ),
    HumanTraitReference(
        782330,
        "DOOM Eternal",
        "0a024f4959f8212abf0e45510f202cb882071a4ba6a9d55205a13397dd020ad4",
        (2, 5, 4, 5, 3, 2),
        ("dark", "tense"),
    ),
    HumanTraitReference(
        960090,
        "Bloons TD 6",
        "7bac7ba3df4a22b87cdc4eaa9e3004b108f7018709b5be87a817f0ed1b5c0973",
        (1, 3, 3, 3, 4, 0),
        ("humorous",),
    ),
    HumanTraitReference(
        1086940,
        "Baldur's Gate 3",
        "5c31f53869bf04526e8d5bfe2a6eddca9b280ecafd843d64ff89fa0aa32a0ec4",
        (4, 3, 3, 2, 2, 4),
        ("dark", "emotional", "tense"),
    ),
    HumanTraitReference(
        1145360,
        "Hades",
        "3ca5912653c065ed1062f0ea4ef003a39b6e2aa1c1fb360c4c46fa440c852fd9",
        (4, 5, 4, 4, 4, 2),
        ("dark", "emotional", "tense"),
    ),
    HumanTraitReference(
        1174180,
        "Red Dead Redemption 2",
        "a0a6ce34ae018ae5ad2d707a60138eba346099bef52f9bd7207f34832bc87210",
        (5, 4, 3, 2, 2, 4),
        ("dark", "emotional", "tense"),
    ),
    HumanTraitReference(
        1190460,
        "DEATH STRANDING",
        "bff6deac5940bb240ea99f39f4e524d27bf38d6669ccf7691deb78fae4f957b9",
        (4, 2, 3, 1, 2, 5),
        ("dark", "emotional", "tense"),
    ),
    HumanTraitReference(
        1245620,
        "ELDEN RING",
        "20240792d5b6f6ec38040dcff16a1876278edaaf3adcd9ece0eb29775a47ae75",
        (3, 4, 5, 3, 3, 5),
        ("dark", "tense"),
    ),
    HumanTraitReference(
        1341820,
        "As Dusk Falls",
        "6f281f430d6d1fe5ffaef653dc480e100619a3db02116ea6fb877ccfbe32f0d6",
        (5, 1, 2, 3, 3, 1),
        ("dark", "emotional", "tense"),
    ),
    HumanTraitReference(
        2379780,
        "Balatro",
        "08714f886ffdf83f8f4210c7c606858e0c2cda3113197655e41bdeb31451c57e",
        (0, None, 4, 3, 4, 1),
        ("tense",),
    ),
    HumanTraitReference(
        2881650,
        "Content Warning",
        "7f249d88bc60a05bac8f936ca8d617c531f9091ef7a359ebeddff885748f96b0",
        (1, None, None, None, None, None),
        ("dark", "humorous", "tense"),
    ),
)


def load_trait_evaluation_games(
    session: Session,
) -> tuple[TraitEvaluationGame, ...]:
    """Load the fixed factual fixture and reject changed snapshots."""
    games = []
    for reference in TRAIT_EVALUATION_REFERENCES:
        plan = load_game_trait_generation_plan(
            session,
            reference.steam_app_id,
        )
        fingerprint = calculate_facts_fingerprint(plan.facts)
        if fingerprint != reference.facts_fingerprint:
            raise ValueError(
                "Trait evaluation facts changed; review the fixture first."
            )
        if plan.facts.name != reference.name:
            raise ValueError(
                "Trait evaluation game identity changed."
            )
        games.append(
            TraitEvaluationGame(
                reference=reference,
                request_item=GameTraitBatchRequestItem(
                    steam_app_id=reference.steam_app_id,
                    facts=plan.facts,
                ),
            )
        )
    return tuple(games)


def _classify_batch_with_metadata(
    client: GeminiClient,
    *,
    model_id: str,
    items: tuple[GameTraitBatchRequestItem, ...],
) -> tuple[GameTraitBatchClassification, GeminiStructuredContent]:
    metadata = client.generate_structured_content_with_metadata(
        model_id=model_id,
        system_instruction=GAME_TRAIT_SYSTEM_INSTRUCTION,
        user_prompt=build_game_trait_batch_user_prompt(items),
        response_schema=None,
        max_output_tokens=MAX_GAME_TRAIT_BATCH_OUTPUT_TOKENS,
    )
    classification = validate_game_trait_batch_response(
        metadata.content,
        items,
    )
    return classification, metadata


def _evaluate_response(
    game: TraitEvaluationGame,
    response: GameTraitResponse,
) -> TraitEvaluationGameResult:
    values = tuple(
        getattr(response, field).value
        for field in NUMERIC_TRAIT_FIELDS
    )
    reference = game.reference
    numeric_matches = 0
    numeric_reference_count = 0
    unsupported = 0
    reviewed_assertions = 0
    for target, actual in zip(reference.numeric_targets, values, strict=True):
        if target is None:
            continue
        numeric_reference_count += 1
        if actual is not None:
            reviewed_assertions += 1
            if abs(actual - target) <= 1:
                numeric_matches += 1
            else:
                unsupported += 1

    moods = tuple(sorted(mood.label for mood in response.moods))
    defensible = sum(
        mood in reference.defensible_moods
        for mood in moods
    )
    unsupported += len(moods) - defensible
    reviewed_assertions += len(moods)
    return TraitEvaluationGameResult(
        steam_app_id=reference.steam_app_id,
        name=reference.name,
        status="valid",
        numeric_values=values,
        moods=moods,
        numeric_matches=numeric_matches,
        numeric_reference_count=numeric_reference_count,
        unsupported_assertions=unsupported,
        reviewed_assertion_count=reviewed_assertions,
        defensible_moods=defensible,
        returned_moods=len(moods),
        error_code=None,
    )


def _failed_game(
    game: TraitEvaluationGame,
    error_code: str,
) -> TraitEvaluationGameResult:
    return TraitEvaluationGameResult(
        steam_app_id=game.reference.steam_app_id,
        name=game.reference.name,
        status="invalid",
        numeric_values=(None,) * len(NUMERIC_TRAIT_FIELDS),
        moods=(),
        numeric_matches=0,
        numeric_reference_count=sum(
            target is not None
            for target in game.reference.numeric_targets
        ),
        unsupported_assertions=0,
        reviewed_assertion_count=0,
        defensible_moods=0,
        returned_moods=0,
        error_code=error_code,
    )


def _evaluate_classification(
    games: tuple[TraitEvaluationGame, ...],
    classification: GameTraitBatchClassification,
) -> tuple[TraitEvaluationGameResult, ...]:
    success_by_id = {
        success.steam_app_id: success.response
        for success in classification.successes
    }
    failure_by_id = {
        failure.steam_app_id: failure.error_code
        for failure in classification.failures
    }
    return tuple(
        _evaluate_response(game, success_by_id[game.reference.steam_app_id])
        if game.reference.steam_app_id in success_by_id
        else _failed_game(
            game,
            failure_by_id.get(
                game.reference.steam_app_id,
                "missing_game",
            ),
        )
        for game in games
    )


def _repeat_equivalent(
    first: TraitEvaluationGameResult,
    second: TraitEvaluationGameResult,
) -> bool:
    if first.status != "valid" or second.status != "valid":
        return False
    for first_value, second_value in zip(
        first.numeric_values,
        second.numeric_values,
        strict=True,
    ):
        if first_value is None or second_value is None:
            if first_value != second_value:
                return False
        elif abs(first_value - second_value) > 1:
            return False
    return first.moods == second.moods


def run_trait_evaluation(
    client: GeminiClient,
    *,
    model_id: str,
    games: tuple[TraitEvaluationGame, ...],
    requests_per_minute: int,
    maximum_calls: int = TRAIT_EVALUATION_MAX_CALLS,
    clock: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
    classifier: Callable[..., tuple[
        GameTraitBatchClassification,
        GeminiStructuredContent,
    ]] = _classify_batch_with_metadata,
) -> TraitEvaluationReport:
    """Run nine fixed pairs plus one repeated pair within eleven calls."""
    if len(games) != len(TRAIT_EVALUATION_REFERENCES):
        raise ValueError("Trait evaluation requires exactly 18 games.")
    if not 1 <= requests_per_minute <= 15:
        raise ValueError("Evaluation RPM must be between 1 and 15.")
    if not 1 <= maximum_calls <= TRAIT_EVALUATION_MAX_CALLS:
        raise ValueError("Evaluation call budget must be between 1 and 11.")
    primary = tuple(
        games[start:start + TRAIT_EVALUATION_BATCH_SIZE]
        for start in range(0, len(games), TRAIT_EVALUATION_BATCH_SIZE)
    )
    batches = tuple(
        (f"t{index + 1:02d}", None, batch)
        for index, batch in enumerate(primary)
    ) + (("t01r", "t01", primary[0]),)
    started_at = datetime.now(UTC).isoformat()
    call_count = 0
    retry_used = False
    last_call_started: float | None = None
    results: list[TraitEvaluationBatchResult] = []
    stopped_early = False

    for batch_id, repeat_of, batch_games in batches:
        attempts = 0
        batch_started = clock()
        while True:
            if call_count >= maximum_calls:
                stopped_early = True
                break
            if last_call_started is not None:
                delay = 60 / requests_per_minute - (
                    clock() - last_call_started
                )
                if delay > 0:
                    sleeper(delay)
            last_call_started = clock()
            call_count += 1
            attempts += 1
            try:
                classification, metadata = classifier(
                    client,
                    model_id=model_id,
                    items=tuple(
                        game.request_item for game in batch_games
                    ),
                )
            except GeminiUnavailableError:
                if not retry_used:
                    retry_used = True
                    continue
                error_code = "unavailable"
                stopped_early = True
            except GeminiRateLimitError:
                error_code = "rate_limited"
                stopped_early = True
            except GeminiAPIError as error:
                parts = ["provider"]
                if error.status_code is not None:
                    parts.append(f"http_{error.status_code}")
                if error.reason_code is not None:
                    parts.append(error.reason_code)
                error_code = "_".join(parts)
                stopped_early = True
            except GameTraitBatchEnvelopeError:
                error_code = "invalid_envelope"
                stopped_early = True
            else:
                results.append(
                    TraitEvaluationBatchResult(
                        batch_id=batch_id,
                        repeat_of=repeat_of,
                        attempts=attempts,
                        latency_ms=round(
                            (clock() - batch_started) * 1000
                        ),
                        input_tokens=metadata.input_tokens,
                        output_tokens=metadata.output_tokens,
                        total_tokens=metadata.total_tokens,
                        unexpected_steam_app_ids=(
                            classification.unexpected_steam_app_ids
                        ),
                        games=_evaluate_classification(
                            batch_games,
                            classification,
                        ),
                        error_code=None,
                    )
                )
                break

            results.append(
                TraitEvaluationBatchResult(
                    batch_id=batch_id,
                    repeat_of=repeat_of,
                    attempts=attempts,
                    latency_ms=round((clock() - batch_started) * 1000),
                    input_tokens=None,
                    output_tokens=None,
                    total_tokens=None,
                    unexpected_steam_app_ids=(),
                    games=tuple(
                        _failed_game(game, error_code)
                        for game in batch_games
                    ),
                    error_code=error_code,
                )
            )
            break
        if stopped_early:
            break

    primary_results = tuple(
        game
        for batch in results
        if batch.repeat_of is None
        for game in batch.games
    )
    numeric_reference_count = sum(
        game.numeric_reference_count for game in primary_results
    )
    numeric_matches = sum(
        game.numeric_matches for game in primary_results
    )
    reviewed_assertions = sum(
        game.reviewed_assertion_count for game in primary_results
    )
    unsupported = sum(
        game.unsupported_assertions for game in primary_results
    )
    returned_moods = sum(game.returned_moods for game in primary_results)
    defensible_moods = sum(
        game.defensible_moods for game in primary_results
    )
    numeric_rate = (
        numeric_matches * 10_000 // numeric_reference_count
        if numeric_reference_count
        else 0
    )
    unsupported_rate = (
        unsupported * 10_000 // reviewed_assertions
        if reviewed_assertions
        else 0
    )
    mood_rate = (
        defensible_moods * 10_000 // returned_moods
        if returned_moods
        else 0
    )
    evidence_pass = (
        len(primary_results) == len(games)
        and all(game.status == "valid" for game in primary_results)
        and all(not batch.unexpected_steam_app_ids for batch in results)
    )
    by_batch = {batch.batch_id: batch for batch in results}
    repeat_pass = False
    if "t01" in by_batch and "t01r" in by_batch:
        original = by_batch["t01"].games
        repeated = by_batch["t01r"].games
        repeat_pass = len(original) == len(repeated) and all(
            _repeat_equivalent(first, second)
            for first, second in zip(original, repeated, strict=True)
        )
    overall = (
        not stopped_early
        and len(results) == len(batches)
        and numeric_rate >= 8_000
        and unsupported_rate <= 500
        and mood_rate >= 8_500
        and evidence_pass
        and repeat_pass
    )
    return TraitEvaluationReport(
        evaluation_version=TRAIT_EVALUATION_VERSION,
        model_id=model_id,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        call_budget=maximum_calls,
        call_count=call_count,
        stopped_early=stopped_early,
        numeric_agreement_basis_points=numeric_rate,
        unsupported_assertion_basis_points=unsupported_rate,
        mood_agreement_basis_points=mood_rate,
        evidence_verification_pass=evidence_pass,
        repeat_consistency_pass=repeat_pass,
        overall_pass=overall,
        batches=tuple(results),
    )
