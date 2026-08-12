from datetime import datetime

from sqlalchemy.orm import Session

from app.game_traits import (
    NUMERIC_TRAIT_FIELDS,
    GameTraitFacts,
    GameTraitResponse,
    calculate_facts_fingerprint,
    validate_response_evidence,
)
from app.models import (
    Game,
    GameCurrentTraitDerivation,
    GameTraitAttempt,
    GameTraitDerivation,
    GameTraitEvidence,
    GameTraitMood,
)

FAILED_TRAIT_ATTEMPT_OUTCOMES = frozenset(
    {
        "transient_failure",
        "invalid_response",
        "authentication_failure",
        "configuration_failure",
        "unexpected_failure",
    }
)


def _validate_bounded_text(
    value: str,
    field_name: str,
    maximum_length: int,
) -> None:
    """Validate one required persistence metadata value.

    Args:
        value: Metadata text supplied by trusted backend code.
        field_name: Human-readable field name used in errors.
        maximum_length: Database column length limit.

    Raises:
        ValueError: If the value is blank, padded, or too long.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string.")

    if value != value.strip():
        raise ValueError(
            f"{field_name} must not contain surrounding whitespace."
        )

    if len(value) > maximum_length:
        raise ValueError(
            f"{field_name} must contain at most "
            f"{maximum_length} characters."
        )


def _build_evidence_rows(
    derivation_id: int,
    response: GameTraitResponse,
) -> list[GameTraitEvidence]:
    """Map verified trait and mood citations to persistence rows.

    Args:
        derivation_id: Database identity of the owning derivation.
        response: Complete response whose evidence has been verified.

    Returns:
        Ordered evidence rows for every known trait and returned mood.
    """
    rows: list[GameTraitEvidence] = []

    for trait_name in NUMERIC_TRAIT_FIELDS:
        trait = getattr(response, trait_name)

        for position, citation in enumerate(trait.evidence):
            rows.append(
                GameTraitEvidence(
                    derivation_id=derivation_id,
                    target_kind="trait",
                    target_name=trait_name,
                    position=position,
                    source_field=citation.field,
                    source_value=citation.value,
                    reason=citation.reason,
                )
            )

    for mood in response.moods:
        for position, citation in enumerate(mood.evidence):
            rows.append(
                GameTraitEvidence(
                    derivation_id=derivation_id,
                    target_kind="mood",
                    target_name=mood.label,
                    position=position,
                    source_field=citation.field,
                    source_value=citation.value,
                    reason=citation.reason,
                )
            )

    return rows


def persist_successful_trait_derivation(
    session: Session,
    *,
    steam_app_id: int,
    response: GameTraitResponse,
    facts: GameTraitFacts,
    schema_version: str,
    derivation_version: str,
    model_id: str,
    operation_id: str,
    attempt_number: int,
    started_at: datetime,
    completed_at: datetime,
) -> None:
    """Persist one validated successful trait-classification attempt.

    The immutable derivation, moods, verified evidence, successful attempt, and
    current pointer are committed in one transaction.

    Args:
        session: Database session that owns the transaction.
        steam_app_id: Shared Steam game receiving the derivation.
        response: Structurally valid derived-trait response.
        facts: Exact canonical facts supplied during classification.
        schema_version: Backend-controlled structured-contract version.
        derivation_version: Backend-controlled rubric and prompt version.
        model_id: Exact configured classifier model identifier.
        operation_id: Identifier grouping attempts for one classification.
        attempt_number: One-based attempt number within the operation.
        started_at: Time at which the model attempt began.
        completed_at: Time at which the validated attempt completed.

    Raises:
        ValueError: If identifiers, provenance, timestamps, or the saved game
            are invalid.
        TraitEvidenceError: If any citation is absent from the supplied facts.
    """
    if (
        not isinstance(steam_app_id, int)
        or isinstance(steam_app_id, bool)
        or steam_app_id <= 0
    ):
        raise ValueError("The Steam App ID must be a positive integer.")

    if (
        not isinstance(attempt_number, int)
        or isinstance(attempt_number, bool)
        or attempt_number < 1
    ):
        raise ValueError("The attempt number must be a positive integer.")

    _validate_bounded_text(schema_version, "Schema version", 50)
    _validate_bounded_text(
        derivation_version,
        "Derivation version",
        50,
    )
    _validate_bounded_text(model_id, "Model ID", 100)
    _validate_bounded_text(operation_id, "Operation ID", 36)

    if started_at.utcoffset() is None:
        raise ValueError("The attempt start time must be timezone-aware.")

    if completed_at.utcoffset() is None:
        raise ValueError("The attempt completion time must be timezone-aware.")

    if completed_at < started_at:
        raise ValueError(
            "The attempt completion time cannot precede its start time."
        )

    validate_response_evidence(response, facts)
    facts_fingerprint = calculate_facts_fingerprint(facts)

    trait_columns: dict[str, object] = {}

    for trait_name in NUMERIC_TRAIT_FIELDS:
        trait = getattr(response, trait_name)
        trait_columns[f"{trait_name}_value"] = trait.value
        trait_columns[f"{trait_name}_confidence"] = trait.confidence

    with session.begin():
        game = session.get(Game, steam_app_id)

        if game is None:
            raise ValueError(
                "The trait derivation must reference a saved Steam game."
            )

        derivation = GameTraitDerivation(
            steam_app_id=steam_app_id,
            schema_version=schema_version,
            derivation_version=derivation_version,
            model_id=model_id,
            facts_fingerprint=facts_fingerprint,
            derived_at=completed_at,
            **trait_columns,
        )
        session.add(derivation)
        session.flush()

        session.add_all(
            [
                GameTraitMood(
                    derivation_id=derivation.id,
                    label=mood.label,
                    confidence=mood.confidence,
                )
                for mood in response.moods
            ]
        )
        session.add_all(
            _build_evidence_rows(derivation.id, response)
        )

        current = session.get(
            GameCurrentTraitDerivation,
            steam_app_id,
        )

        if current is None:
            session.add(
                GameCurrentTraitDerivation(
                    steam_app_id=steam_app_id,
                    derivation_id=derivation.id,
                )
            )
        else:
            current.derivation_id = derivation.id

        session.add(
            GameTraitAttempt(
                steam_app_id=steam_app_id,
                operation_id=operation_id,
                attempt_number=attempt_number,
                schema_version=schema_version,
                derivation_version=derivation_version,
                model_id=model_id,
                facts_fingerprint=facts_fingerprint,
                started_at=started_at,
                completed_at=completed_at,
                outcome="succeeded",
                error_code=None,
                error_message=None,
                derivation_id=derivation.id,
            )
        )


def record_failed_trait_attempt(
    session: Session,
    *,
    steam_app_id: int,
    facts: GameTraitFacts,
    schema_version: str,
    derivation_version: str,
    model_id: str,
    operation_id: str,
    attempt_number: int,
    started_at: datetime,
    completed_at: datetime,
    outcome: str,
    error_code: str | None,
    error_message: str,
) -> None:
    """Record one failed classification without replacing usable traits.

    Args:
        session: Database session that owns the transaction.
        steam_app_id: Shared Steam game affected by the failed call.
        facts: Exact canonical facts supplied during classification.
        schema_version: Backend-controlled structured-contract version.
        derivation_version: Backend-controlled rubric and prompt version.
        model_id: Exact configured classifier model identifier.
        operation_id: Identifier grouping attempts for one classification.
        attempt_number: One-based attempt number within the operation.
        started_at: Time at which the model attempt began.
        completed_at: Time at which the failed attempt completed.
        outcome: Allowlisted category describing the failure.
        error_code: Optional bounded machine-readable diagnostic code.
        error_message: Safe human-readable diagnostic message.

    Raises:
        ValueError: If identifiers, provenance, timestamps, outcome, error
            information, or the saved game are invalid.
    """
    if (
        not isinstance(steam_app_id, int)
        or isinstance(steam_app_id, bool)
        or steam_app_id <= 0
    ):
        raise ValueError("The Steam App ID must be a positive integer.")

    if (
        not isinstance(attempt_number, int)
        or isinstance(attempt_number, bool)
        or attempt_number < 1
    ):
        raise ValueError("The attempt number must be a positive integer.")

    _validate_bounded_text(schema_version, "Schema version", 50)
    _validate_bounded_text(
        derivation_version,
        "Derivation version",
        50,
    )
    _validate_bounded_text(model_id, "Model ID", 100)
    _validate_bounded_text(operation_id, "Operation ID", 36)

    if outcome not in FAILED_TRAIT_ATTEMPT_OUTCOMES:
        raise ValueError("The failed attempt outcome is unsupported.")

    if error_code is not None:
        _validate_bounded_text(error_code, "Error code", 100)

    if (
        not isinstance(error_message, str)
        or not error_message.strip()
    ):
        raise ValueError(
            "The error message must be a non-empty string."
        )

    if started_at.utcoffset() is None:
        raise ValueError("The attempt start time must be timezone-aware.")

    if completed_at.utcoffset() is None:
        raise ValueError("The attempt completion time must be timezone-aware.")

    if completed_at < started_at:
        raise ValueError(
            "The attempt completion time cannot precede its start time."
        )

    stored_error_message = error_message.strip()[:500]
    facts_fingerprint = calculate_facts_fingerprint(facts)

    with session.begin():
        game = session.get(Game, steam_app_id)

        if game is None:
            raise ValueError(
                "The failed attempt must reference a saved Steam game."
            )

        session.add(
            GameTraitAttempt(
                steam_app_id=steam_app_id,
                operation_id=operation_id,
                attempt_number=attempt_number,
                schema_version=schema_version,
                derivation_version=derivation_version,
                model_id=model_id,
                facts_fingerprint=facts_fingerprint,
                started_at=started_at,
                completed_at=completed_at,
                outcome=outcome,
                error_code=error_code,
                error_message=stored_error_message,
                derivation_id=None,
            )
        )
