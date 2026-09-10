from dataclasses import dataclass

from pydantic import ValidationError

from app.gemini.traits.prompt import (
    GAME_TRAIT_MODEL_ID,
    GAME_TRAIT_SYSTEM_INSTRUCTION,
    MAX_GAME_TRAIT_BATCH_OUTPUT_TOKENS,
    build_game_trait_batch_user_prompt,
    build_game_trait_user_prompt,
)
from app.gemini.traits.schema import (
    build_game_trait_batch_response_schema,
    build_game_trait_response_schema,
)
from app.gemini.traits.contracts import (
    GameTraitBatchRequestItem,
    GameTraitFacts,
    GameTraitResponse,
    TraitEvidenceError,
    validate_response_evidence,
)
from app.gemini.client import GeminiClient


class GameTraitInvalidResponseError(ValueError):
    """Indicate that Gemini returned an unusable trait interpretation."""


class GameTraitBatchEnvelopeError(ValueError):
    """Indicate that Gemini returned an unusable batch envelope."""


@dataclass(frozen=True)
class ClassifiedGameTrait:
    """Hold one independently validated game result."""

    steam_app_id: int
    response: GameTraitResponse


@dataclass(frozen=True)
class GameTraitClassificationFailure:
    """Describe one expected game whose response could not be used."""

    steam_app_id: int
    error_code: str


@dataclass(frozen=True)
class GameTraitBatchClassification:
    """Separate valid expected records from bounded response failures."""

    successes: tuple[ClassifiedGameTrait, ...]
    failures: tuple[GameTraitClassificationFailure, ...]
    unexpected_steam_app_ids: tuple[int, ...]


def classify_game_traits(
    client: GeminiClient,
    facts: GameTraitFacts,
    *,
    corrective_retry: bool = False,
) -> GameTraitResponse:
    """Classify one game's canonical facts into grounded Ludex traits.

    Args:
        client: Gemini transport used to request structured output.
        facts: Exact canonical factual metadata supplied for classification.
        corrective_retry: Whether to request a fresh correction after an
            invalid prior response.

    Returns:
        A structurally and factually validated game-trait response.

    Raises:
        GameTraitInvalidResponseError: If Gemini's decoded JSON violates the
            response contract or cites facts absent from the supplied input.
        GeminiAPIError: If the underlying Gemini request fails.
    """
    raw_response = client.generate_structured_content(
        model_id=GAME_TRAIT_MODEL_ID,
        system_instruction=GAME_TRAIT_SYSTEM_INSTRUCTION,
        user_prompt=build_game_trait_user_prompt(
            facts,
            corrective_retry=corrective_retry,
        ),
        response_schema=build_game_trait_response_schema(),
    )

    try:
        response = GameTraitResponse.model_validate(raw_response)
        return validate_response_evidence(response, facts)
    except (ValidationError, TraitEvidenceError):
        raise GameTraitInvalidResponseError(
            "Gemini returned an invalid game-trait response."
        ) from None


def _validate_batch_response(
    raw_response: dict[str, object],
    items: tuple[GameTraitBatchRequestItem, ...],
) -> GameTraitBatchClassification:
    """Validate batch records independently against their own facts."""
    if set(raw_response) != {"games"}:
        raise GameTraitBatchEnvelopeError(
            "Gemini returned an invalid game-trait batch envelope."
        )

    raw_games = raw_response["games"]
    if not isinstance(raw_games, list) or not raw_games:
        raise GameTraitBatchEnvelopeError(
            "Gemini returned an invalid game-trait batch envelope."
        )

    expected_order = tuple(item.steam_app_id for item in items)
    facts_by_id = {
        item.steam_app_id: item.facts
        for item in items
    }
    raw_by_id: dict[int, list[object]] = {}
    unexpected_ids: set[int] = set()

    for raw_game in raw_games:
        if not isinstance(raw_game, dict):
            continue

        raw_id = raw_game.get("steam_app_id")
        if (
            not isinstance(raw_id, int)
            or isinstance(raw_id, bool)
            or raw_id <= 0
        ):
            continue

        if raw_id not in facts_by_id:
            unexpected_ids.add(raw_id)
            continue

        raw_by_id.setdefault(raw_id, []).append(raw_game)

    successes: list[ClassifiedGameTrait] = []
    failures: list[GameTraitClassificationFailure] = []

    for steam_app_id in expected_order:
        records = raw_by_id.get(steam_app_id, [])

        if not records:
            failures.append(
                GameTraitClassificationFailure(
                    steam_app_id=steam_app_id,
                    error_code="missing_game",
                )
            )
            continue

        if len(records) != 1:
            failures.append(
                GameTraitClassificationFailure(
                    steam_app_id=steam_app_id,
                    error_code="duplicate_game",
                )
            )
            continue

        record = records[0]
        if set(record) != {"steam_app_id", "traits"}:
            failures.append(
                GameTraitClassificationFailure(
                    steam_app_id=steam_app_id,
                    error_code="invalid_record",
                )
            )
            continue

        try:
            response = GameTraitResponse.model_validate(record["traits"])
            validate_response_evidence(
                response,
                facts_by_id[steam_app_id],
            )
        except (ValidationError, TraitEvidenceError):
            failures.append(
                GameTraitClassificationFailure(
                    steam_app_id=steam_app_id,
                    error_code="domain_validation",
                )
            )
            continue

        successes.append(
            ClassifiedGameTrait(
                steam_app_id=steam_app_id,
                response=response,
            )
        )

    return GameTraitBatchClassification(
        successes=tuple(successes),
        failures=tuple(failures),
        unexpected_steam_app_ids=tuple(sorted(unexpected_ids)),
    )


def classify_game_trait_batch(
    client: GeminiClient,
    items: tuple[GameTraitBatchRequestItem, ...],
    *,
    corrective_retry: bool = False,
) -> GameTraitBatchClassification:
    """Classify one through five games in one provider request."""
    steam_app_ids = tuple(item.steam_app_id for item in items)
    user_prompt = build_game_trait_batch_user_prompt(
        items,
        corrective_retry=corrective_retry,
    )
    raw_response = client.generate_structured_content(
        model_id=GAME_TRAIT_MODEL_ID,
        system_instruction=GAME_TRAIT_SYSTEM_INSTRUCTION,
        user_prompt=user_prompt,
        response_schema=build_game_trait_batch_response_schema(
            steam_app_ids
        ),
        max_output_tokens=MAX_GAME_TRAIT_BATCH_OUTPUT_TOKENS,
    )

    return _validate_batch_response(raw_response, items)
