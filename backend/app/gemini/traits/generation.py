from collections.abc import Callable
from datetime import UTC, datetime
import time

from sqlalchemy.orm import Session

from app.gemini.traits.classifier import (
    GameTraitInvalidResponseError,
    classify_game_traits,
)
from app.gemini.traits.persistence import (
    persist_successful_trait_derivation,
    record_failed_trait_attempt,
)
from app.gemini.traits.prompt import (
    GAME_TRAIT_DERIVATION_VERSION,
    GAME_TRAIT_MODEL_ID,
    GAME_TRAIT_SCHEMA_VERSION,
)
from app.gemini.traits.contracts import GameTraitFacts, GameTraitResponse
from app.gemini.client import (
    GeminiAPIError,
    GeminiAuthenticationError,
    GeminiClient,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiUnavailableError,
)

TRANSIENT_RETRY_DELAYS_SECONDS = (1.0, 2.0)


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


def _read_attempt_time(
    clock: Callable[[], datetime],
) -> datetime:
    """Read and validate one attempt timestamp.

    Args:
        clock: Injectable clock returning the current time.

    Returns:
        A timezone-aware timestamp.

    Raises:
        ValueError: If the clock returns a timezone-naive timestamp.
    """
    timestamp = clock()

    if timestamp.utcoffset() is None:
        raise ValueError(
            "The game-trait generation clock must be timezone-aware."
        )

    return timestamp


def _transient_error_code(
    error: GeminiUnavailableError | GeminiRateLimitError,
) -> str:
    """Return a bounded diagnostic code for a transient Gemini failure.

    Args:
        error: Retryable Gemini transport failure.

    Returns:
        A stable machine-readable diagnostic code.
    """
    if isinstance(error, GeminiRateLimitError):
        return "gemini_rate_limited"

    return "gemini_unavailable"


def _invalid_response_error_code(
    error: GameTraitInvalidResponseError | GeminiResponseError,
) -> str:
    """Return a stable code for one invalid Gemini response.

    Args:
        error: Structurally, semantically, or factually invalid output.

    Returns:
        A bounded machine-readable diagnostic code.
    """
    if isinstance(error, GeminiResponseError):
        return "malformed_response"

    return "domain_validation"


def generate_game_traits(
    session: Session,
    client: GeminiClient,
    *,
    steam_app_id: int,
    facts: GameTraitFacts,
    operation_id: str,
    clock: Callable[[], datetime] = _utc_now,
    sleeper: Callable[[float], None] = time.sleep,
) -> GameTraitResponse:
    """Generate and persist one grounded game-trait derivation.

    Canonical facts must be built before this function is called. Gemini
    requests therefore occur without requiring a database read transaction.
    Retryable transport failures are recorded individually. Invalid output
    receives one corrective retry. Only a complete validated response creates
    a derivation and changes the current pointer.

    Args:
        session: Database session used by the persistence boundary.
        client: Configured backend-only Gemini transport.
        steam_app_id: Shared Steam game receiving the derivation.
        facts: Exact canonical facts supplied to the classifier.
        operation_id: Identifier shared by every attempt in this operation.
        clock: Injectable timezone-aware clock used for attempt timestamps.
        sleeper: Injectable delay function used between transient retries.

    Returns:
        The validated response that was persisted successfully.

    Raises:
        ValueError: If the clock returns a timezone-naive timestamp.
        GameTraitInvalidResponseError: If corrective validation also fails.
        GeminiResponseError: If corrective provider output is also malformed.
        GeminiRateLimitError: If all rate-limit retries are exhausted.
        GeminiUnavailableError: If all availability retries are exhausted.
        GeminiAuthenticationError: If the configured credential is rejected.
        GeminiAPIError: If Gemini rejects the configured request.
        Exception: If an unexpected classifier failure occurs after its safe
        diagnostic is recorded.
    """
    maximum_attempts = len(TRANSIENT_RETRY_DELAYS_SECONDS) + 1
    corrective_retry = False

    for attempt_number in range(1, maximum_attempts + 1):
        started_at = _read_attempt_time(clock)

        try:
            if corrective_retry:
                response = classify_game_traits(
                    client,
                    facts,
                    corrective_retry=True,
                )
            else:
                response = classify_game_traits(client, facts)
        except (
            GameTraitInvalidResponseError,
            GeminiResponseError,
        ) as error:
            completed_at = _read_attempt_time(clock)

            record_failed_trait_attempt(
                session,
                steam_app_id=steam_app_id,
                facts=facts,
                schema_version=GAME_TRAIT_SCHEMA_VERSION,
                derivation_version=GAME_TRAIT_DERIVATION_VERSION,
                model_id=GAME_TRAIT_MODEL_ID,
                operation_id=operation_id,
                attempt_number=attempt_number,
                started_at=started_at,
                completed_at=completed_at,
                outcome="invalid_response",
                error_code=_invalid_response_error_code(error),
                error_message=str(error),
            )

            if corrective_retry or attempt_number == maximum_attempts:
                raise

            corrective_retry = True
            continue
        except (
            GeminiUnavailableError,
            GeminiRateLimitError,
        ) as error:
            completed_at = _read_attempt_time(clock)

            record_failed_trait_attempt(
                session,
                steam_app_id=steam_app_id,
                facts=facts,
                schema_version=GAME_TRAIT_SCHEMA_VERSION,
                derivation_version=GAME_TRAIT_DERIVATION_VERSION,
                model_id=GAME_TRAIT_MODEL_ID,
                operation_id=operation_id,
                attempt_number=attempt_number,
                started_at=started_at,
                completed_at=completed_at,
                outcome="transient_failure",
                error_code=_transient_error_code(error),
                error_message=str(error),
            )

            if attempt_number == maximum_attempts:
                raise

            sleeper(
                TRANSIENT_RETRY_DELAYS_SECONDS[
                    attempt_number - 1
                ]
            )
            continue

        except GeminiAuthenticationError as error:
            completed_at = _read_attempt_time(clock)

            record_failed_trait_attempt(
                session,
                steam_app_id=steam_app_id,
                facts=facts,
                schema_version=GAME_TRAIT_SCHEMA_VERSION,
                derivation_version=GAME_TRAIT_DERIVATION_VERSION,
                model_id=GAME_TRAIT_MODEL_ID,
                operation_id=operation_id,
                attempt_number=attempt_number,
                started_at=started_at,
                completed_at=completed_at,
                outcome="authentication_failure",
                error_code="gemini_authentication",
                error_message=str(error),
            )
            raise
        except GeminiAPIError as error:
            completed_at = _read_attempt_time(clock)

            record_failed_trait_attempt(
                session,
                steam_app_id=steam_app_id,
                facts=facts,
                schema_version=GAME_TRAIT_SCHEMA_VERSION,
                derivation_version=GAME_TRAIT_DERIVATION_VERSION,
                model_id=GAME_TRAIT_MODEL_ID,
                operation_id=operation_id,
                attempt_number=attempt_number,
                started_at=started_at,
                completed_at=completed_at,
                outcome="configuration_failure",
                error_code="gemini_request_rejected",
                error_message=str(error),
            )
            raise
        except Exception:
            completed_at = _read_attempt_time(clock)

            record_failed_trait_attempt(
                session,
                steam_app_id=steam_app_id,
                facts=facts,
                schema_version=GAME_TRAIT_SCHEMA_VERSION,
                derivation_version=GAME_TRAIT_DERIVATION_VERSION,
                model_id=GAME_TRAIT_MODEL_ID,
                operation_id=operation_id,
                attempt_number=attempt_number,
                started_at=started_at,
                completed_at=completed_at,
                outcome="unexpected_failure",
                error_code="unexpected_error",
                error_message=(
                    "Unexpected game-trait generation failure."
                ),
            )
            raise

        completed_at = _read_attempt_time(clock)

        persist_successful_trait_derivation(
            session,
            steam_app_id=steam_app_id,
            response=response,
            facts=facts,
            schema_version=GAME_TRAIT_SCHEMA_VERSION,
            derivation_version=GAME_TRAIT_DERIVATION_VERSION,
            model_id=GAME_TRAIT_MODEL_ID,
            operation_id=operation_id,
            attempt_number=attempt_number,
            started_at=started_at,
            completed_at=completed_at,
        )

        return response

    raise RuntimeError("Game-trait generation exhausted unexpectedly.")
