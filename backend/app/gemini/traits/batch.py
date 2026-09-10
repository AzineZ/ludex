from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app.gemini.client import (
    GeminiAPIError,
    GeminiAuthenticationError,
    GeminiClient,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiUnavailableError,
)
from app.gemini.traits.classifier import (
    GameTraitBatchClassification,
    GameTraitBatchEnvelopeError,
    classify_game_trait_batch,
)
from app.gemini.traits.contracts import (
    MAX_GAMES_PER_TRAIT_REQUEST,
    GameTraitBatchRequestItem,
)
from app.gemini.traits.persistence import (
    persist_successful_trait_derivation,
    record_failed_trait_attempt,
)
from app.gemini.traits.planning import load_game_trait_generation_plan
from app.gemini.traits.prompt import (
    GAME_TRAIT_DERIVATION_VERSION,
    GAME_TRAIT_MODEL_ID,
    GAME_TRAIT_SCHEMA_VERSION,
    build_game_trait_batch_user_prompt,
)


RETRY_GAME_TRAIT_BATCH_SIZE = 2

SessionFactory = Callable[[], AbstractContextManager[Session]]


class GameTraitRequestBudgetExhausted(RuntimeError):
    """Indicate that an operator run spent its request budget."""


@dataclass(frozen=True)
class GameTraitBatchFailure:
    """Represent one game that could not complete trait generation."""

    steam_app_id: int
    error: Exception


@dataclass(frozen=True)
class GameTraitBatchResult:
    """Summarize one provider batch in request order."""

    generated_steam_app_ids: tuple[int, ...]
    skipped_steam_app_ids: tuple[int, ...]
    failures: tuple[GameTraitBatchFailure, ...]
    request_count: int
    unexpected_response_steam_app_ids: tuple[int, ...] = ()
    terminal_error: Exception | None = None


@dataclass(frozen=True)
class GameTraitRunResult:
    """Summarize a resumable sequence of five-game batches."""

    generated_steam_app_ids: tuple[int, ...]
    skipped_steam_app_ids: tuple[int, ...]
    failures: tuple[GameTraitBatchFailure, ...]
    request_count: int
    terminal_error: Exception | None


class GameTraitRequestLimiter:
    """Enforce one process-local request cap and minimum start interval."""

    def __init__(
        self,
        *,
        maximum_requests: int,
        requests_per_minute: int,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            not isinstance(maximum_requests, int)
            or isinstance(maximum_requests, bool)
            or maximum_requests <= 0
        ):
            raise ValueError("Maximum requests must be a positive integer.")

        if (
            not isinstance(requests_per_minute, int)
            or isinstance(requests_per_minute, bool)
            or requests_per_minute <= 0
        ):
            raise ValueError(
                "Requests per minute must be a positive integer."
            )

        self._maximum_requests = maximum_requests
        self._minimum_interval = 60.0 / requests_per_minute
        self._monotonic_clock = monotonic_clock
        self._sleeper = sleeper
        self._request_count = 0
        self._last_request_started_at: float | None = None

    @property
    def request_count(self) -> int:
        """Return provider attempts reserved by this run."""
        return self._request_count

    def before_request(self) -> None:
        """Reserve and pace one request before provider I/O begins."""
        if self._request_count >= self._maximum_requests:
            raise GameTraitRequestBudgetExhausted(
                "The game-trait request budget is exhausted."
            )

        now = self._monotonic_clock()
        if self._last_request_started_at is not None:
            remaining = (
                self._minimum_interval
                - (now - self._last_request_started_at)
            )
            if remaining > 0:
                self._sleeper(remaining)
                now = self._monotonic_clock()

        self._request_count += 1
        self._last_request_started_at = now


def _new_operation_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _unique_steam_app_ids(steam_app_ids: Sequence[int]) -> list[int]:
    unique_ids = list(dict.fromkeys(steam_app_ids))

    for steam_app_id in unique_ids:
        if (
            not isinstance(steam_app_id, int)
            or isinstance(steam_app_id, bool)
            or steam_app_id <= 0
        ):
            raise ValueError("Steam App IDs must be positive integers.")

    return unique_ids


def _validate_operation_id(operation_id: str) -> None:
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError("Operation IDs must be non-empty strings.")
    if operation_id != operation_id.strip():
        raise ValueError(
            "Operation IDs must not contain surrounding whitespace."
        )
    if len(operation_id) > 36:
        raise ValueError(
            "Operation IDs must contain at most 36 characters."
        )


def _read_attempt_time(clock: Callable[[], datetime]) -> datetime:
    timestamp = clock()
    if timestamp.utcoffset() is None:
        raise ValueError(
            "The game-trait batch clock must be timezone-aware."
        )
    return timestamp


def _record_failure(
    session_factory: SessionFactory,
    *,
    item: GameTraitBatchRequestItem,
    operation_id: str,
    attempt_number: int,
    started_at: datetime,
    completed_at: datetime,
    outcome: str,
    error_code: str,
    error_message: str,
) -> None:
    with session_factory() as session:
        record_failed_trait_attempt(
            session,
            steam_app_id=item.steam_app_id,
            facts=item.facts,
            schema_version=GAME_TRAIT_SCHEMA_VERSION,
            derivation_version=GAME_TRAIT_DERIVATION_VERSION,
            model_id=GAME_TRAIT_MODEL_ID,
            operation_id=operation_id,
            attempt_number=attempt_number,
            started_at=started_at,
            completed_at=completed_at,
            outcome=outcome,
            error_code=error_code,
            error_message=error_message,
        )


def _record_provider_failure(
    session_factory: SessionFactory,
    items: tuple[GameTraitBatchRequestItem, ...],
    *,
    error: Exception,
    operation_ids_by_game: dict[int, str],
    attempt_number: int,
    started_at: datetime,
    completed_at: datetime,
) -> None:
    if isinstance(error, GeminiRateLimitError):
        outcome = "transient_failure"
        error_code = "gemini_rate_limited"
    elif isinstance(error, GeminiUnavailableError):
        outcome = "transient_failure"
        error_code = "gemini_unavailable"
    elif isinstance(error, GeminiAuthenticationError):
        outcome = "authentication_failure"
        error_code = "gemini_authentication"
    elif isinstance(error, (GeminiResponseError, GameTraitBatchEnvelopeError)):
        outcome = "invalid_response"
        error_code = "malformed_response"
    elif isinstance(error, GeminiAPIError):
        outcome = "configuration_failure"
        error_code = "gemini_request_rejected"
    else:
        outcome = "unexpected_failure"
        error_code = "unexpected_error"

    safe_message = str(error) or "Unexpected game-trait batch failure."
    for item in items:
        _record_failure(
            session_factory,
            item=item,
            operation_id=operation_ids_by_game[item.steam_app_id],
            attempt_number=attempt_number,
            started_at=started_at,
            completed_at=completed_at,
            outcome=outcome,
            error_code=error_code,
            error_message=safe_message,
        )


def _persist_successes(
    session_factory: SessionFactory,
    classification: GameTraitBatchClassification,
    items_by_id: dict[int, GameTraitBatchRequestItem],
    *,
    operation_ids_by_game: dict[int, str],
    attempt_number: int,
    started_at: datetime,
    completed_at: datetime,
) -> tuple[list[int], list[GameTraitBatchFailure]]:
    generated: list[int] = []
    failures: list[GameTraitBatchFailure] = []

    for success in classification.successes:
        item = items_by_id[success.steam_app_id]
        try:
            with session_factory() as session:
                persist_successful_trait_derivation(
                    session,
                    steam_app_id=success.steam_app_id,
                    response=success.response,
                    facts=item.facts,
                    schema_version=GAME_TRAIT_SCHEMA_VERSION,
                    derivation_version=GAME_TRAIT_DERIVATION_VERSION,
                    model_id=GAME_TRAIT_MODEL_ID,
                    operation_id=operation_ids_by_game[
                        success.steam_app_id
                    ],
                    attempt_number=attempt_number,
                    started_at=started_at,
                    completed_at=completed_at,
                )
        except Exception as error:
            failures.append(
                GameTraitBatchFailure(success.steam_app_id, error)
            )
        else:
            generated.append(success.steam_app_id)

    return generated, failures


def _classify_once(
    session_factory: SessionFactory,
    client: GeminiClient,
    items: tuple[GameTraitBatchRequestItem, ...],
    *,
    classifier: Callable[..., GameTraitBatchClassification],
    limiter: GameTraitRequestLimiter,
    operation_ids_by_game: dict[int, str],
    attempt_number: int,
    clock: Callable[[], datetime],
    corrective_retry: bool,
) -> tuple[GameTraitBatchClassification, datetime, datetime]:
    limiter.before_request()
    started_at = _read_attempt_time(clock)

    try:
        classification = classifier(
            client,
            items,
            corrective_retry=corrective_retry,
        )
    except Exception as error:
        completed_at = _read_attempt_time(clock)
        _record_provider_failure(
            session_factory,
            items,
            error=error,
            operation_ids_by_game=operation_ids_by_game,
            attempt_number=attempt_number,
            started_at=started_at,
            completed_at=completed_at,
        )
        raise

    completed_at = _read_attempt_time(clock)
    return classification, started_at, completed_at


def _process_classification(
    session_factory: SessionFactory,
    classification: GameTraitBatchClassification,
    items: tuple[GameTraitBatchRequestItem, ...],
    *,
    operation_ids_by_game: dict[int, str],
    attempt_number: int,
    started_at: datetime,
    completed_at: datetime,
) -> tuple[list[int], list[GameTraitBatchFailure]]:
    items_by_id = {item.steam_app_id: item for item in items}
    generated, failures = _persist_successes(
        session_factory,
        classification,
        items_by_id,
        operation_ids_by_game=operation_ids_by_game,
        attempt_number=attempt_number,
        started_at=started_at,
        completed_at=completed_at,
    )

    for item_failure in classification.failures:
        item = items_by_id[item_failure.steam_app_id]
        error = ValueError(
            "Gemini returned an invalid result for one requested game."
        )
        _record_failure(
            session_factory,
            item=item,
            operation_id=operation_ids_by_game[item.steam_app_id],
            attempt_number=attempt_number,
            started_at=started_at,
            completed_at=completed_at,
            outcome="invalid_response",
            error_code=item_failure.error_code,
            error_message=str(error),
        )
        failures.append(
            GameTraitBatchFailure(item_failure.steam_app_id, error)
        )

    return generated, failures


def generate_game_trait_batch(
    session_factory: SessionFactory,
    client: GeminiClient,
    steam_app_ids: Sequence[int],
    operation_id_factory: Callable[[], str] = _new_operation_id,
    *,
    limiter: GameTraitRequestLimiter | None = None,
    classifier: Callable[..., GameTraitBatchClassification] = (
        classify_game_trait_batch
    ),
    clock: Callable[[], datetime] = _utc_now,
) -> GameTraitBatchResult:
    """Classify at most five stale games in one request plus bounded retry."""
    requested_ids = _unique_steam_app_ids(steam_app_ids)
    if len(requested_ids) > MAX_GAMES_PER_TRAIT_REQUEST:
        raise ValueError("Trait batches must contain at most five games.")

    if not requested_ids:
        return GameTraitBatchResult((), (), (), 0)

    plans = []
    for steam_app_id in requested_ids:
        with session_factory() as session:
            plans.append(
                load_game_trait_generation_plan(session, steam_app_id)
            )

    skipped = tuple(
        plan.steam_app_id
        for plan in plans
        if not plan.needs_generation
    )
    pending_items = tuple(
        GameTraitBatchRequestItem(
            steam_app_id=plan.steam_app_id,
            facts=plan.facts,
        )
        for plan in plans
        if plan.needs_generation
    )
    if not pending_items:
        return GameTraitBatchResult((), skipped, (), 0)

    # Validate the complete serialized input before reserving provider quota.
    build_game_trait_batch_user_prompt(pending_items)

    operation_ids_by_game = {
        item.steam_app_id: operation_id_factory()
        for item in pending_items
    }
    for operation_id in operation_ids_by_game.values():
        _validate_operation_id(operation_id)
    if len(set(operation_ids_by_game.values())) != len(pending_items):
        raise ValueError("Operation IDs must be unique per game.")
    request_limiter = limiter or GameTraitRequestLimiter(
        maximum_requests=4,
        requests_per_minute=10,
    )
    initial_request_count = request_limiter.request_count
    generated: list[int] = []
    final_failures: dict[int, GameTraitBatchFailure] = {}
    unexpected_ids: set[int] = set()
    terminal_error: Exception | None = None

    try:
        classification, started_at, completed_at = _classify_once(
            session_factory,
            client,
            pending_items,
            classifier=classifier,
            limiter=request_limiter,
            operation_ids_by_game=operation_ids_by_game,
            attempt_number=1,
            clock=clock,
            corrective_retry=False,
        )
    except (GeminiResponseError, GameTraitBatchEnvelopeError):
        classification, started_at, completed_at = _classify_once(
            session_factory,
            client,
            pending_items,
            classifier=classifier,
            limiter=request_limiter,
            operation_ids_by_game=operation_ids_by_game,
            attempt_number=2,
            clock=clock,
            corrective_retry=True,
        )
        response_attempt_number = 2
        allow_item_retry = False
    else:
        response_attempt_number = 1
        allow_item_retry = True

    unexpected_ids.update(classification.unexpected_steam_app_ids)
    first_generated, first_failures = _process_classification(
        session_factory,
        classification,
        pending_items,
        operation_ids_by_game=operation_ids_by_game,
        attempt_number=response_attempt_number,
        started_at=started_at,
        completed_at=completed_at,
    )
    generated.extend(first_generated)
    final_failures.update(
        {failure.steam_app_id: failure for failure in first_failures}
    )

    if allow_item_retry and classification.failures:
        failed_ids = {
            failure.steam_app_id
            for failure in classification.failures
        }
        retry_items = tuple(
            item
            for item in pending_items
            if item.steam_app_id in failed_ids
        )

        for start in range(0, len(retry_items), RETRY_GAME_TRAIT_BATCH_SIZE):
            retry_group = retry_items[
                start:start + RETRY_GAME_TRAIT_BATCH_SIZE
            ]
            try:
                retry_classification, retry_started, retry_completed = (
                    _classify_once(
                        session_factory,
                        client,
                        retry_group,
                        classifier=classifier,
                        limiter=request_limiter,
                        operation_ids_by_game=operation_ids_by_game,
                        attempt_number=2,
                        clock=clock,
                        corrective_retry=True,
                    )
                )
            except (
                GameTraitRequestBudgetExhausted,
                GeminiAPIError,
                GameTraitBatchEnvelopeError,
                ValueError,
            ) as error:
                terminal_error = error
                break
            unexpected_ids.update(
                retry_classification.unexpected_steam_app_ids
            )
            retry_generated, retry_failures = _process_classification(
                session_factory,
                retry_classification,
                retry_group,
                operation_ids_by_game=operation_ids_by_game,
                attempt_number=2,
                started_at=retry_started,
                completed_at=retry_completed,
            )
            generated.extend(retry_generated)
            for steam_app_id in retry_generated:
                final_failures.pop(steam_app_id, None)
            final_failures.update(
                {
                    failure.steam_app_id: failure
                    for failure in retry_failures
                }
            )

    generated_set = set(generated)
    return GameTraitBatchResult(
        generated_steam_app_ids=tuple(
            steam_app_id
            for steam_app_id in requested_ids
            if steam_app_id in generated_set
        ),
        skipped_steam_app_ids=skipped,
        failures=tuple(
            final_failures[steam_app_id]
            for steam_app_id in requested_ids
            if steam_app_id in final_failures
        ),
        request_count=(
            request_limiter.request_count - initial_request_count
        ),
        unexpected_response_steam_app_ids=tuple(sorted(unexpected_ids)),
        terminal_error=terminal_error,
    )


def run_game_trait_batches(
    session_factory: SessionFactory,
    client: GeminiClient,
    steam_app_ids: Sequence[int],
    *,
    limiter: GameTraitRequestLimiter,
    classifier: Callable[..., GameTraitBatchClassification] = (
        classify_game_trait_batch
    ),
    clock: Callable[[], datetime] = _utc_now,
) -> GameTraitRunResult:
    """Run deterministic five-game groups until complete or safely stopped."""
    requested_ids = _unique_steam_app_ids(steam_app_ids)
    generated: list[int] = []
    skipped: list[int] = []
    failures: list[GameTraitBatchFailure] = []
    terminal_error: Exception | None = None
    initial_request_count = limiter.request_count

    for start in range(0, len(requested_ids), MAX_GAMES_PER_TRAIT_REQUEST):
        group = requested_ids[start:start + MAX_GAMES_PER_TRAIT_REQUEST]
        try:
            result = generate_game_trait_batch(
                session_factory,
                client,
                group,
                limiter=limiter,
                classifier=classifier,
                clock=clock,
            )
        except (
            GameTraitRequestBudgetExhausted,
            GeminiAPIError,
            GameTraitBatchEnvelopeError,
            ValueError,
        ) as error:
            terminal_error = error
            break

        generated.extend(result.generated_steam_app_ids)
        skipped.extend(result.skipped_steam_app_ids)
        failures.extend(result.failures)
        if result.terminal_error is not None:
            terminal_error = result.terminal_error
            break

    return GameTraitRunResult(
        generated_steam_app_ids=tuple(generated),
        skipped_steam_app_ids=tuple(skipped),
        failures=tuple(failures),
        request_count=limiter.request_count - initial_request_count,
        terminal_error=terminal_error,
    )
