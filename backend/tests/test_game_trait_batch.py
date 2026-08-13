import pytest
from collections.abc import Generator
from contextlib import contextmanager
from threading import Barrier, Lock
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

import app.game_trait_batch as batch
from app.game_traits import GameTraitResponse
from app.gemini_client import (
    GeminiClient,
    GeminiUnavailableError,
)


@contextmanager
def _session_scope() -> Generator[Session, None, None]:
    """Provide an isolated fake session context for one worker."""
    yield MagicMock(spec=Session)


def test_batch_deduplicates_and_reports_each_outcome(
    monkeypatch,
) -> None:
    """Continue across generated, current, and failed games."""
    client = MagicMock(spec=GeminiClient)
    generated_response = MagicMock(spec=GameTraitResponse)
    failure = GeminiUnavailableError(
        "Gemini is currently unavailable."
    )
    operation_ids = iter(
        [
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
            "33333333-3333-3333-3333-333333333333",
        ]
    )

    def generate(
        session: Session,
        generation_client: GeminiClient,
        *,
        steam_app_id: int,
        operation_id: str,
    ) -> GameTraitResponse | None:
        """Return one controlled per-game batch outcome."""
        assert generation_client is client
        assert operation_id

        if steam_app_id == 1:
            return generated_response

        if steam_app_id == 2:
            return None

        raise failure

    generation_mock = MagicMock(side_effect=generate)

    monkeypatch.setattr(
        batch,
        "generate_saved_game_traits",
        generation_mock,
    )

    result = batch.generate_game_trait_batch(
        _session_scope,
        client,
        [1, 2, 1, 3],
        operation_id_factory=lambda: next(operation_ids),
    )

    assert result.generated_steam_app_ids == (1,)
    assert result.skipped_steam_app_ids == (2,)
    assert len(result.failures) == 1
    assert result.failures[0].steam_app_id == 3
    assert result.failures[0].error is failure

    assert generation_mock.call_count == 3
    assert {
        item.kwargs["steam_app_id"]
        for item in generation_mock.call_args_list
    } == {1, 2, 3}
    assert len(
        {
            item.kwargs["operation_id"]
            for item in generation_mock.call_args_list
        }
    ) == 3


def test_batch_never_exceeds_two_simultaneous_workers(
    monkeypatch,
) -> None:
    """Bound concurrent classification to the confirmed worker limit."""
    client = MagicMock(spec=GeminiClient)
    response = MagicMock(spec=GameTraitResponse)
    pair_barrier = Barrier(2)
    state_lock = Lock()
    active_workers = 0
    maximum_active_workers = 0

    def generate(
        session: Session,
        generation_client: GeminiClient,
        *,
        steam_app_id: int,
        operation_id: str,
    ) -> GameTraitResponse:
        """Measure active calls while synchronizing workers in pairs."""
        nonlocal active_workers
        nonlocal maximum_active_workers

        with state_lock:
            active_workers += 1
            maximum_active_workers = max(
                maximum_active_workers,
                active_workers,
            )

        try:
            pair_barrier.wait(timeout=2)
            return response
        finally:
            with state_lock:
                active_workers -= 1

    monkeypatch.setattr(
        batch,
        "generate_saved_game_traits",
        generate,
    )

    operation_ids = iter(
        [
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
            "33333333-3333-3333-3333-333333333333",
            "44444444-4444-4444-4444-444444444444",
        ]
    )

    result = batch.generate_game_trait_batch(
        _session_scope,
        client,
        [1, 2, 3, 4],
        operation_id_factory=lambda: next(operation_ids),
    )

    assert maximum_active_workers == 2
    assert result.generated_steam_app_ids == (1, 2, 3, 4)
    assert result.skipped_steam_app_ids == ()
    assert result.failures == ()


def test_empty_batch_creates_no_sessions_or_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return an empty result without creating worker resources."""
    client = MagicMock(spec=GeminiClient)
    session_factory = MagicMock()
    operation_id_factory = MagicMock()
    generation_mock = MagicMock()

    monkeypatch.setattr(
        batch,
        "generate_saved_game_traits",
        generation_mock,
    )

    result = batch.generate_game_trait_batch(
        session_factory,
        client,
        [],
        operation_id_factory=operation_id_factory,
    )

    assert result.generated_steam_app_ids == ()
    assert result.skipped_steam_app_ids == ()
    assert result.failures == ()
    session_factory.assert_not_called()
    operation_id_factory.assert_not_called()
    generation_mock.assert_not_called()


@pytest.mark.parametrize(
    "invalid_steam_app_id",
    [
        0,
        -1,
        True,
        "440",
    ],
)
def test_rejects_invalid_batch_game_id_before_work(
    monkeypatch: pytest.MonkeyPatch,
    invalid_steam_app_id: object,
) -> None:
    """Reject invalid game identity before creating operations."""
    client = MagicMock(spec=GeminiClient)
    session_factory = MagicMock()
    operation_id_factory = MagicMock()
    generation_mock = MagicMock()

    monkeypatch.setattr(
        batch,
        "generate_saved_game_traits",
        generation_mock,
    )

    with pytest.raises(
        ValueError,
        match="positive integers",
    ):
        batch.generate_game_trait_batch(
            session_factory,
            client,
            [invalid_steam_app_id],
            operation_id_factory=operation_id_factory,
        )

    session_factory.assert_not_called()
    operation_id_factory.assert_not_called()
    generation_mock.assert_not_called()


@pytest.mark.parametrize(
    ("operation_id", "expected_message"),
    [
        ("", "non-empty strings"),
        (" padded ", "surrounding whitespace"),
        ("x" * 37, "at most 36 characters"),
    ],
)
def test_rejects_invalid_operation_id_before_workers_start(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    expected_message: str,
) -> None:
    """Reject invalid attempt identity before creating a session."""
    client = MagicMock(spec=GeminiClient)
    session_factory = MagicMock()
    generation_mock = MagicMock()

    monkeypatch.setattr(
        batch,
        "generate_saved_game_traits",
        generation_mock,
    )

    with pytest.raises(ValueError, match=expected_message):
        batch.generate_game_trait_batch(
            session_factory,
            client,
            [440],
            operation_id_factory=lambda: operation_id,
        )

    session_factory.assert_not_called()
    generation_mock.assert_not_called()
