import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, call

from sqlalchemy.orm import Session

from app.game_trait_classifier import (
    GameTraitInvalidResponseError,
)
import app.game_trait_generation as generation
from app.game_trait_prompt import (
    GAME_TRAIT_DERIVATION_VERSION,
    GAME_TRAIT_MODEL_ID,
    GAME_TRAIT_SCHEMA_VERSION,
    build_game_trait_user_prompt,
)
from app.game_traits import GameTraitFacts, GameTraitResponse
from app.gemini_client import (
    GeminiAPIError,
    GeminiAuthenticationError,
    GeminiClient,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiUnavailableError,
)


def _facts() -> GameTraitFacts:
    """Return canonical facts for generation tests."""
    return GameTraitFacts(
        name="Example Adventure",
        summary="A story-driven adventure.",
        genres=("Adventure",),
        themes=(),
        keywords=(),
        game_modes=("Single player",),
        time_to_beat=(),
        release_information=(),
    )


def _valid_response() -> GameTraitResponse:
    """Return one completely validated trait response."""
    evidence = {
        "field": "summary",
        "value": "A story-driven adventure.",
        "reason": "Directly supports the derived value.",
    }
    unknown_trait = {
        "value": None,
        "confidence": 0,
        "evidence": [],
    }

    return GameTraitResponse.model_validate(
        {
            "story_focus": {
                "value": 4,
                "confidence": 0.80,
                "evidence": [evidence],
            },
            "combat_intensity": unknown_trait,
            "difficulty": unknown_trait,
            "pacing": unknown_trait,
            "session_friendliness": unknown_trait,
            "exploration_focus": unknown_trait,
            "moods": [
                {
                    "label": "emotional",
                    "confidence": 0.80,
                    "evidence": [evidence],
                }
            ],
        }
    )


def test_persists_first_successful_classification(
    monkeypatch,
) -> None:
    """Persist one successful call with trusted attempt provenance."""
    session = MagicMock(spec=Session)
    client = MagicMock(spec=GeminiClient)
    facts = _facts()
    response = _valid_response()

    started_at = datetime(2026, 8, 12, 17, 0, tzinfo=UTC)
    completed_at = datetime(
        2026,
        8,
        12,
        17,
        0,
        2,
        tzinfo=UTC,
    )
    clock = MagicMock(side_effect=[started_at, completed_at])
    classifier = MagicMock(return_value=response)
    persistence = MagicMock()
    failure_recorder = MagicMock()
    sleeper = MagicMock()

    monkeypatch.setattr(
        generation,
        "classify_game_traits",
        classifier,
    )
    monkeypatch.setattr(
        generation,
        "persist_successful_trait_derivation",
        persistence,
    )
    monkeypatch.setattr(
        generation,
        "record_failed_trait_attempt",
        failure_recorder,
    )

    result = generation.generate_game_traits(
        session,
        client,
        steam_app_id=440,
        facts=facts,
        operation_id="11111111-1111-1111-1111-111111111111",
        clock=clock,
        sleeper=sleeper,
    )

    assert result is response
    classifier.assert_called_once_with(client, facts)
    persistence.assert_called_once_with(
        session,
        steam_app_id=440,
        response=response,
        facts=facts,
        schema_version=GAME_TRAIT_SCHEMA_VERSION,
        derivation_version=GAME_TRAIT_DERIVATION_VERSION,
        model_id=GAME_TRAIT_MODEL_ID,
        operation_id="11111111-1111-1111-1111-111111111111",
        attempt_number=1,
        started_at=started_at,
        completed_at=completed_at,
    )
    failure_recorder.assert_not_called()
    sleeper.assert_not_called()


def test_retries_transient_failure_and_records_every_attempt(
    monkeypatch,
) -> None:
    """Record one outage, delay, and persist the successful retry."""
    session = MagicMock(spec=Session)
    client = MagicMock(spec=GeminiClient)
    facts = _facts()
    response = _valid_response()

    first_started_at = datetime(
        2026,
        8,
        12,
        17,
        0,
        tzinfo=UTC,
    )
    first_completed_at = datetime(
        2026,
        8,
        12,
        17,
        0,
        1,
        tzinfo=UTC,
    )
    second_started_at = datetime(
        2026,
        8,
        12,
        17,
        0,
        2,
        tzinfo=UTC,
    )
    second_completed_at = datetime(
        2026,
        8,
        12,
        17,
        0,
        4,
        tzinfo=UTC,
    )
    clock = MagicMock(
        side_effect=[
            first_started_at,
            first_completed_at,
            second_started_at,
            second_completed_at,
        ]
    )
    upstream_error = GeminiUnavailableError(
        "Gemini is currently unavailable."
    )
    classifier = MagicMock(
        side_effect=[upstream_error, response]
    )
    persistence = MagicMock()
    failure_recorder = MagicMock()
    sleeper = MagicMock()

    monkeypatch.setattr(
        generation,
        "classify_game_traits",
        classifier,
    )
    monkeypatch.setattr(
        generation,
        "persist_successful_trait_derivation",
        persistence,
    )
    monkeypatch.setattr(
        generation,
        "record_failed_trait_attempt",
        failure_recorder,
    )

    result = generation.generate_game_traits(
        session,
        client,
        steam_app_id=440,
        facts=facts,
        operation_id="11111111-1111-1111-1111-111111111111",
        clock=clock,
        sleeper=sleeper,
    )

    assert result is response
    assert classifier.call_count == 2

    failure_recorder.assert_called_once_with(
        session,
        steam_app_id=440,
        facts=facts,
        schema_version=GAME_TRAIT_SCHEMA_VERSION,
        derivation_version=GAME_TRAIT_DERIVATION_VERSION,
        model_id=GAME_TRAIT_MODEL_ID,
        operation_id="11111111-1111-1111-1111-111111111111",
        attempt_number=1,
        started_at=first_started_at,
        completed_at=first_completed_at,
        outcome="transient_failure",
        error_code="gemini_unavailable",
        error_message="Gemini is currently unavailable.",
    )
    persistence.assert_called_once_with(
        session,
        steam_app_id=440,
        response=response,
        facts=facts,
        schema_version=GAME_TRAIT_SCHEMA_VERSION,
        derivation_version=GAME_TRAIT_DERIVATION_VERSION,
        model_id=GAME_TRAIT_MODEL_ID,
        operation_id="11111111-1111-1111-1111-111111111111",
        attempt_number=2,
        started_at=second_started_at,
        completed_at=second_completed_at,
    )
    sleeper.assert_called_once_with(1.0)


def test_records_rate_limit_with_stable_diagnostic_code(
    monkeypatch,
) -> None:
    """Retry rate limiting while storing a provider-safe code."""
    session = MagicMock(spec=Session)
    client = MagicMock(spec=GeminiClient)
    facts = _facts()
    response = _valid_response()

    base_time = datetime(2026, 8, 12, 17, 0, tzinfo=UTC)
    clock = MagicMock(
        side_effect=[
            base_time,
            base_time + timedelta(seconds=1),
            base_time + timedelta(seconds=2),
            base_time + timedelta(seconds=3),
        ]
    )
    classifier = MagicMock(
        side_effect=[
            GeminiRateLimitError(
                "Gemini rate-limited the API request."
            ),
            response,
        ]
    )
    persistence = MagicMock()
    failure_recorder = MagicMock()
    sleeper = MagicMock()

    monkeypatch.setattr(
        generation,
        "classify_game_traits",
        classifier,
    )
    monkeypatch.setattr(
        generation,
        "persist_successful_trait_derivation",
        persistence,
    )
    monkeypatch.setattr(
        generation,
        "record_failed_trait_attempt",
        failure_recorder,
    )

    result = generation.generate_game_traits(
        session,
        client,
        steam_app_id=440,
        facts=facts,
        operation_id="11111111-1111-1111-1111-111111111111",
        clock=clock,
        sleeper=sleeper,
    )

    assert result is response
    assert (
        failure_recorder.call_args.kwargs["error_code"]
        == "gemini_rate_limited"
    )
    assert (
        failure_recorder.call_args.kwargs["outcome"]
        == "transient_failure"
    )
    sleeper.assert_called_once_with(1.0)
    assert persistence.call_args.kwargs["attempt_number"] == 2


def test_stops_after_three_transient_failures(
    monkeypatch,
) -> None:
    """Record three outages and re-raise after bounded delays."""
    session = MagicMock(spec=Session)
    client = MagicMock(spec=GeminiClient)
    facts = _facts()

    base_time = datetime(2026, 8, 12, 17, 0, tzinfo=UTC)
    clock = MagicMock(
        side_effect=[
            base_time + timedelta(seconds=offset)
            for offset in range(6)
        ]
    )
    upstream_error = GeminiUnavailableError(
        "Gemini is currently unavailable."
    )
    classifier = MagicMock(side_effect=upstream_error)
    persistence = MagicMock()
    failure_recorder = MagicMock()
    sleeper = MagicMock()

    monkeypatch.setattr(
        generation,
        "classify_game_traits",
        classifier,
    )
    monkeypatch.setattr(
        generation,
        "persist_successful_trait_derivation",
        persistence,
    )
    monkeypatch.setattr(
        generation,
        "record_failed_trait_attempt",
        failure_recorder,
    )

    with pytest.raises(GeminiUnavailableError) as caught:
        generation.generate_game_traits(
            session,
            client,
            steam_app_id=440,
            facts=facts,
            operation_id=(
                "11111111-1111-1111-1111-111111111111"
            ),
            clock=clock,
            sleeper=sleeper,
        )

    assert caught.value is upstream_error
    assert classifier.call_count == 3
    assert failure_recorder.call_count == 3
    assert [
        item.kwargs["attempt_number"]
        for item in failure_recorder.call_args_list
    ] == [1, 2, 3]
    assert [
        item.args[0]
        for item in sleeper.call_args_list
    ] == [1.0, 2.0]
    persistence.assert_not_called()


def test_corrective_prompt_uses_static_instruction_only() -> None:
    """Request a fresh correction without echoing invalid model output."""
    facts = _facts()

    prompt = build_game_trait_user_prompt(
        facts,
        corrective_retry=True,
    )

    assert prompt.startswith(
        "The previous model response was invalid.\n"
        "Return a completely new response that follows every schema, "
        "grounding, confidence, and evidence rule.\n"
        "Do not repeat or discuss the previous response.\n\n"
    )
    assert "<game_facts>" in prompt
    assert "</game_facts>" in prompt


@pytest.mark.parametrize(
    ("invalid_error", "expected_code"),
    [
        (
            GameTraitInvalidResponseError(
                "Gemini returned an invalid game-trait response."
            ),
            "domain_validation",
        ),
        (
            GeminiResponseError(
                "Gemini returned invalid response data."
            ),
            "malformed_response",
        ),
    ],
)
def test_corrects_one_invalid_response(
    monkeypatch,
    invalid_error: Exception,
    expected_code: str,
) -> None:
    """Record invalid output and persist one corrective retry."""
    session = MagicMock(spec=Session)
    client = MagicMock(spec=GeminiClient)
    facts = _facts()
    response = _valid_response()

    base_time = datetime(2026, 8, 12, 17, 0, tzinfo=UTC)
    clock = MagicMock(
        side_effect=[
            base_time,
            base_time + timedelta(seconds=1),
            base_time + timedelta(seconds=2),
            base_time + timedelta(seconds=3),
        ]
    )
    classifier = MagicMock(
        side_effect=[invalid_error, response]
    )
    persistence = MagicMock()
    failure_recorder = MagicMock()
    sleeper = MagicMock()

    monkeypatch.setattr(
        generation,
        "classify_game_traits",
        classifier,
    )
    monkeypatch.setattr(
        generation,
        "persist_successful_trait_derivation",
        persistence,
    )
    monkeypatch.setattr(
        generation,
        "record_failed_trait_attempt",
        failure_recorder,
    )

    result = generation.generate_game_traits(
        session,
        client,
        steam_app_id=440,
        facts=facts,
        operation_id="11111111-1111-1111-1111-111111111111",
        clock=clock,
        sleeper=sleeper,
    )

    assert result is response
    assert classifier.call_args_list == [
        call(client, facts),
        call(
            client,
            facts,
            corrective_retry=True,
        ),
    ]
    assert (
        failure_recorder.call_args.kwargs["outcome"]
        == "invalid_response"
    )
    assert (
        failure_recorder.call_args.kwargs["error_code"]
        == expected_code
    )
    assert (
        failure_recorder.call_args.kwargs["attempt_number"]
        == 1
    )
    assert persistence.call_args.kwargs["attempt_number"] == 2
    sleeper.assert_not_called()


def test_stops_after_second_invalid_response(
    monkeypatch,
) -> None:
    """Record two invalid calls and reject the complete operation."""
    session = MagicMock(spec=Session)
    client = MagicMock(spec=GeminiClient)
    facts = _facts()

    base_time = datetime(2026, 8, 12, 17, 0, tzinfo=UTC)
    clock = MagicMock(
        side_effect=[
            base_time,
            base_time + timedelta(seconds=1),
            base_time + timedelta(seconds=2),
            base_time + timedelta(seconds=3),
        ]
    )
    invalid_error = GameTraitInvalidResponseError(
        "Gemini returned an invalid game-trait response."
    )
    classifier = MagicMock(side_effect=invalid_error)
    persistence = MagicMock()
    failure_recorder = MagicMock()
    sleeper = MagicMock()

    monkeypatch.setattr(
        generation,
        "classify_game_traits",
        classifier,
    )
    monkeypatch.setattr(
        generation,
        "persist_successful_trait_derivation",
        persistence,
    )
    monkeypatch.setattr(
        generation,
        "record_failed_trait_attempt",
        failure_recorder,
    )

    with pytest.raises(GameTraitInvalidResponseError) as caught:
        generation.generate_game_traits(
            session,
            client,
            steam_app_id=440,
            facts=facts,
            operation_id=(
                "11111111-1111-1111-1111-111111111111"
            ),
            clock=clock,
            sleeper=sleeper,
        )

    assert caught.value is invalid_error
    assert classifier.call_args_list == [
        call(client, facts),
        call(
            client,
            facts,
            corrective_retry=True,
        ),
    ]
    assert failure_recorder.call_count == 2
    assert [
        item.kwargs["attempt_number"]
        for item in failure_recorder.call_args_list
    ] == [1, 2]
    assert all(
        item.kwargs["outcome"] == "invalid_response"
        for item in failure_recorder.call_args_list
    )
    persistence.assert_not_called()
    sleeper.assert_not_called()


@pytest.mark.parametrize(
    (
        "upstream_error",
        "expected_outcome",
        "expected_code",
        "expected_message",
    ),
    [
        (
            GeminiAuthenticationError(
                "Gemini authentication was rejected."
            ),
            "authentication_failure",
            "gemini_authentication",
            "Gemini authentication was rejected.",
        ),
        (
            GeminiAPIError(
                "Gemini rejected the API request."
            ),
            "configuration_failure",
            "gemini_request_rejected",
            "Gemini rejected the API request.",
        ),
        (
            RuntimeError("Sensitive unexpected detail."),
            "unexpected_failure",
            "unexpected_error",
            "Unexpected game-trait generation failure.",
        ),
    ],
)
def test_records_nonretryable_failure_once(
    monkeypatch,
    upstream_error: Exception,
    expected_outcome: str,
    expected_code: str,
    expected_message: str,
) -> None:
    """Record a safe diagnostic and avoid retrying permanent failures."""
    session = MagicMock(spec=Session)
    client = MagicMock(spec=GeminiClient)
    facts = _facts()

    started_at = datetime(2026, 8, 12, 17, 0, tzinfo=UTC)
    completed_at = started_at + timedelta(seconds=1)
    clock = MagicMock(side_effect=[started_at, completed_at])
    classifier = MagicMock(side_effect=upstream_error)
    persistence = MagicMock()
    failure_recorder = MagicMock()
    sleeper = MagicMock()

    monkeypatch.setattr(
        generation,
        "classify_game_traits",
        classifier,
    )
    monkeypatch.setattr(
        generation,
        "persist_successful_trait_derivation",
        persistence,
    )
    monkeypatch.setattr(
        generation,
        "record_failed_trait_attempt",
        failure_recorder,
    )

    with pytest.raises(type(upstream_error)) as caught:
        generation.generate_game_traits(
            session,
            client,
            steam_app_id=440,
            facts=facts,
            operation_id=(
                "11111111-1111-1111-1111-111111111111"
            ),
            clock=clock,
            sleeper=sleeper,
        )

    assert caught.value is upstream_error
    classifier.assert_called_once_with(client, facts)
    failure_recorder.assert_called_once_with(
        session,
        steam_app_id=440,
        facts=facts,
        schema_version=GAME_TRAIT_SCHEMA_VERSION,
        derivation_version=GAME_TRAIT_DERIVATION_VERSION,
        model_id=GAME_TRAIT_MODEL_ID,
        operation_id="11111111-1111-1111-1111-111111111111",
        attempt_number=1,
        started_at=started_at,
        completed_at=completed_at,
        outcome=expected_outcome,
        error_code=expected_code,
        error_message=expected_message,
    )
    persistence.assert_not_called()
    sleeper.assert_not_called()
