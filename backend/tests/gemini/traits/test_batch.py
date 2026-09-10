from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

import app.gemini.traits.batch as batch
from app.gemini.client import GeminiClient, GeminiResponseError
from app.gemini.traits.classifier import (
    ClassifiedGameTrait,
    GameTraitBatchClassification,
    GameTraitBatchEnvelopeError,
    GameTraitClassificationFailure,
)
from app.gemini.traits.contracts import (
    GameTraitFacts,
    GameTraitResponse,
)
from app.gemini.traits.planning import GameTraitGenerationPlan


@contextmanager
def _session_scope() -> Generator[Session, None, None]:
    yield MagicMock(spec=Session)


def _facts(name: str = "Example Adventure") -> GameTraitFacts:
    return GameTraitFacts(
        name=name,
        summary="A story-driven adventure.",
        genres=("Adventure",),
        themes=(),
        keywords=(),
        game_modes=("Single player",),
        time_to_beat=(),
        release_information=(),
    )


def _response() -> GameTraitResponse:
    evidence = {
        "field": "summary",
        "value": "A story-driven adventure.",
        "reason": "Directly supports the derived value.",
    }
    unknown = {"value": None, "confidence": 0, "evidence": []}
    return GameTraitResponse.model_validate(
        {
            "story_focus": {
                "value": 4,
                "confidence": 0.8,
                "evidence": [evidence],
            },
            "combat_intensity": unknown,
            "difficulty": unknown,
            "pacing": unknown,
            "session_friendliness": unknown,
            "exploration_focus": unknown,
            "moods": [],
        }
    )


def _plan(steam_app_id: int, *, current: bool = False) -> GameTraitGenerationPlan:
    return GameTraitGenerationPlan(
        steam_app_id=steam_app_id,
        facts=_facts(f"Game {steam_app_id}"),
        current_derivation_id=12 if current else None,
        needs_generation=not current,
    )


def _classification(
    success_ids: tuple[int, ...],
    failure_ids: tuple[int, ...] = (),
    unexpected_ids: tuple[int, ...] = (),
) -> GameTraitBatchClassification:
    return GameTraitBatchClassification(
        successes=tuple(
            ClassifiedGameTrait(steam_app_id, _response())
            for steam_app_id in success_ids
        ),
        failures=tuple(
            GameTraitClassificationFailure(
                steam_app_id,
                "domain_validation",
            )
            for steam_app_id in failure_ids
        ),
        unexpected_steam_app_ids=unexpected_ids,
    )


def _clock(game_count: int = 20) -> MagicMock:
    base = datetime(2026, 9, 9, tzinfo=UTC)
    return MagicMock(
        side_effect=[
            base + timedelta(seconds=index)
            for index in range(game_count)
        ]
    )


def _install_storage_mocks(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock]:
    persistence = MagicMock()
    failure_recorder = MagicMock()
    monkeypatch.setattr(batch, "persist_successful_trait_derivation", persistence)
    monkeypatch.setattr(batch, "record_failed_trait_attempt", failure_recorder)
    return persistence, failure_recorder


def test_sends_five_stale_games_in_one_provider_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(spec=GeminiClient)
    monkeypatch.setattr(
        batch,
        "load_game_trait_generation_plan",
        lambda session, steam_app_id: _plan(steam_app_id),
    )
    persistence, failure_recorder = _install_storage_mocks(monkeypatch)
    classifier = MagicMock(
        return_value=_classification((1, 2, 3, 4, 5))
    )
    limiter = batch.GameTraitRequestLimiter(
        maximum_requests=4,
        requests_per_minute=10,
        monotonic_clock=MagicMock(return_value=0.0),
        sleeper=MagicMock(),
    )

    result = batch.generate_game_trait_batch(
        _session_scope,
        client,
        [1, 2, 3, 4, 5],
        limiter=limiter,
        classifier=classifier,
        clock=_clock(),
    )

    assert result.generated_steam_app_ids == (1, 2, 3, 4, 5)
    assert result.skipped_steam_app_ids == ()
    assert result.failures == ()
    assert result.request_count == 1
    assert classifier.call_count == 1
    assert tuple(
        item.steam_app_id
        for item in classifier.call_args.args[1]
    ) == (1, 2, 3, 4, 5)
    assert persistence.call_count == 5
    assert len(
        {
            call.kwargs["operation_id"]
            for call in persistence.call_args_list
        }
    ) == 5
    failure_recorder.assert_not_called()


def test_retries_only_invalid_games_in_groups_of_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(spec=GeminiClient)
    monkeypatch.setattr(
        batch,
        "load_game_trait_generation_plan",
        lambda session, steam_app_id: _plan(steam_app_id),
    )
    persistence, failure_recorder = _install_storage_mocks(monkeypatch)
    classifier = MagicMock(
        side_effect=[
            _classification((1, 2), (3, 4, 5)),
            _classification((3, 4)),
            _classification((5,)),
        ]
    )
    limiter = batch.GameTraitRequestLimiter(
        maximum_requests=4,
        requests_per_minute=10,
        monotonic_clock=MagicMock(
            side_effect=[0.0, 6.0, 12.0]
        ),
        sleeper=MagicMock(),
    )

    result = batch.generate_game_trait_batch(
        _session_scope,
        client,
        [1, 2, 3, 4, 5],
        limiter=limiter,
        classifier=classifier,
        clock=_clock(),
    )

    assert result.generated_steam_app_ids == (1, 2, 3, 4, 5)
    assert result.failures == ()
    assert result.request_count == 3
    assert [
        tuple(item.steam_app_id for item in call.args[1])
        for call in classifier.call_args_list
    ] == [(1, 2, 3, 4, 5), (3, 4), (5,)]
    assert persistence.call_count == 5
    assert failure_recorder.call_count == 3
    successful_operation_ids = {
        call.kwargs["steam_app_id"]: call.kwargs["operation_id"]
        for call in persistence.call_args_list
    }
    for call in failure_recorder.call_args_list:
        assert (
            call.kwargs["operation_id"]
            == successful_operation_ids[call.kwargs["steam_app_id"]]
        )


def test_retries_one_malformed_envelope_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(spec=GeminiClient)
    monkeypatch.setattr(
        batch,
        "load_game_trait_generation_plan",
        lambda session, steam_app_id: _plan(steam_app_id),
    )
    persistence, failure_recorder = _install_storage_mocks(monkeypatch)
    classifier = MagicMock(
        side_effect=[
            GameTraitBatchEnvelopeError("Invalid envelope."),
            _classification((1, 2)),
        ]
    )
    limiter = batch.GameTraitRequestLimiter(
        maximum_requests=2,
        requests_per_minute=10,
        monotonic_clock=MagicMock(side_effect=[0.0, 6.0]),
        sleeper=MagicMock(),
    )

    result = batch.generate_game_trait_batch(
        _session_scope,
        client,
        [1, 2],
        limiter=limiter,
        classifier=classifier,
        clock=_clock(),
    )

    assert result.generated_steam_app_ids == (1, 2)
    assert result.request_count == 2
    assert classifier.call_args_list[1].kwargs["corrective_retry"] is True
    assert persistence.call_count == 2
    assert failure_recorder.call_count == 2


def test_current_games_are_skipped_without_provider_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(spec=GeminiClient)
    monkeypatch.setattr(
        batch,
        "load_game_trait_generation_plan",
        lambda session, steam_app_id: _plan(steam_app_id, current=True),
    )
    persistence, failure_recorder = _install_storage_mocks(monkeypatch)
    classifier = MagicMock()
    limiter = MagicMock(spec=batch.GameTraitRequestLimiter)
    limiter.request_count = 0

    result = batch.generate_game_trait_batch(
        _session_scope,
        client,
        [2, 1, 2],
        limiter=limiter,
        classifier=classifier,
    )

    assert result.generated_steam_app_ids == ()
    assert result.skipped_steam_app_ids == (2, 1)
    assert result.request_count == 0
    classifier.assert_not_called()
    persistence.assert_not_called()
    failure_recorder.assert_not_called()


def test_rejects_oversized_serialized_input_before_reserving_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(spec=GeminiClient)
    monkeypatch.setattr(
        batch,
        "load_game_trait_generation_plan",
        lambda session, steam_app_id: _plan(steam_app_id),
    )
    monkeypatch.setattr(
        batch,
        "build_game_trait_batch_user_prompt",
        MagicMock(side_effect=ValueError("Trait batch exceeds 60 KB.")),
    )
    classifier = MagicMock()
    limiter = MagicMock(spec=batch.GameTraitRequestLimiter)
    limiter.request_count = 0

    with pytest.raises(ValueError, match="60 KB"):
        batch.generate_game_trait_batch(
            _session_scope,
            client,
            [1],
            limiter=limiter,
            classifier=classifier,
        )

    limiter.before_request.assert_not_called()
    classifier.assert_not_called()


def test_limiter_paces_and_stops_before_an_unreserved_request() -> None:
    monotonic_clock = MagicMock(side_effect=[0.0, 1.0, 6.0])
    sleeper = MagicMock()
    limiter = batch.GameTraitRequestLimiter(
        maximum_requests=2,
        requests_per_minute=10,
        monotonic_clock=monotonic_clock,
        sleeper=sleeper,
    )

    limiter.before_request()
    limiter.before_request()

    assert limiter.request_count == 2
    sleeper.assert_called_once_with(5.0)
    with pytest.raises(batch.GameTraitRequestBudgetExhausted):
        limiter.before_request()
    assert limiter.request_count == 2


def test_second_malformed_envelope_stops_the_resumable_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(spec=GeminiClient)
    monkeypatch.setattr(
        batch,
        "load_game_trait_generation_plan",
        lambda session, steam_app_id: _plan(steam_app_id),
    )
    _install_storage_mocks(monkeypatch)
    classifier = MagicMock(
        side_effect=GameTraitBatchEnvelopeError("Invalid envelope.")
    )
    limiter = batch.GameTraitRequestLimiter(
        maximum_requests=2,
        requests_per_minute=10,
        monotonic_clock=MagicMock(side_effect=[0.0, 6.0]),
        sleeper=MagicMock(),
    )

    result = batch.run_game_trait_batches(
        _session_scope,
        client,
        [1, 2, 3, 4, 5, 6],
        limiter=limiter,
        classifier=classifier,
        clock=_clock(),
    )

    assert result.generated_steam_app_ids == ()
    assert result.request_count == 2
    assert isinstance(result.terminal_error, GameTraitBatchEnvelopeError)


def test_budget_stop_preserves_successes_from_partial_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(spec=GeminiClient)
    monkeypatch.setattr(
        batch,
        "load_game_trait_generation_plan",
        lambda session, steam_app_id: _plan(steam_app_id),
    )
    _install_storage_mocks(monkeypatch)
    classifier = MagicMock(
        return_value=_classification((1, 2), (3, 4, 5))
    )
    limiter = batch.GameTraitRequestLimiter(
        maximum_requests=1,
        requests_per_minute=10,
        monotonic_clock=MagicMock(return_value=0.0),
        sleeper=MagicMock(),
    )

    result = batch.run_game_trait_batches(
        _session_scope,
        client,
        [1, 2, 3, 4, 5, 6],
        limiter=limiter,
        classifier=classifier,
        clock=_clock(),
    )

    assert result.generated_steam_app_ids == (1, 2)
    assert result.request_count == 1
    assert isinstance(
        result.terminal_error,
        batch.GameTraitRequestBudgetExhausted,
    )


@pytest.mark.parametrize("invalid_id", [0, -1, True, "440"])
def test_rejects_invalid_game_ids_before_work(invalid_id: object) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        batch.generate_game_trait_batch(
            MagicMock(),
            MagicMock(spec=GeminiClient),
            [invalid_id],
        )


def test_rejects_more_than_five_games() -> None:
    with pytest.raises(ValueError, match="at most five"):
        batch.generate_game_trait_batch(
            MagicMock(),
            MagicMock(spec=GeminiClient),
            [1, 2, 3, 4, 5, 6],
        )


def test_empty_batch_spends_no_work() -> None:
    result = batch.generate_game_trait_batch(
        MagicMock(),
        MagicMock(spec=GeminiClient),
        [],
    )
    assert result == batch.GameTraitBatchResult((), (), (), 0)
