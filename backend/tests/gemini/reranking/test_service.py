import logging
import re
from io import StringIO
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.gemini.client import (
    GeminiAPIError,
    GeminiAuthenticationError,
    GeminiConnectionError,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiStructuredContent,
    GeminiTimeoutError,
    GeminiUnavailableError,
)
from app.gemini.reranking.contracts import RerankFilters, RerankResponse
from app.gemini.reranking.diagnostics import (
    GEMINI_DIAGNOSTIC_LOGGER,
    log_rerank_success,
)
from app.gemini.reranking.service import (
    GeminiRerankRuntime,
    RerankAssistantStatus,
    RerankSubmission,
    recommend_with_gemini,
)
from app.models import Profile
from tests.gemini.reranking.test_candidate_pool import _add_game


@pytest.fixture
def session_and_profile() -> tuple[Session, int]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    profile = Profile(steam_id="76561198000000000", display_name="Player")
    session.add(profile)
    session.commit()
    try:
        yield session, profile.id
    finally:
        session.close()
        engine.dispose()


def _runtime() -> GeminiRerankRuntime:
    return GeminiRerankRuntime(client=Mock(), model_id="gemini-3.6-flash")


def _submission() -> RerankSubmission:
    return RerankSubmission(
        prompt="Something calm after work",
        selected_genre_id=31,
        filters=RerankFilters(),
        rejected_steam_app_ids=(),
    )


def _no_match_response() -> tuple[RerankResponse, GeminiStructuredContent]:
    return (
        RerankResponse(
            status="no_match",
            recommendations=(),
            no_match_reason="No supplied game fits.",
        ),
        GeminiStructuredContent(
            content={}, input_tokens=None, output_tokens=None, total_tokens=None
        ),
    )


def test_success_uses_one_call_and_maps_snapshot_presentation(
    session_and_profile: tuple[Session, int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    session, profile_id = session_and_profile
    _add_game(
        session,
        profile_id=profile_id,
        steam_app_id=1,
        completion_seconds=3_600,
    )
    runtime = _runtime()
    rerank = Mock(
        return_value=(
            RerankResponse(
                status="ranked",
                recommendations=(
                    {
                        "steam_app_id": 1,
                        "summary": "A focused, low-pressure adventure.",
                        "reasoning": (
                            "Its calm pace fits your request for something "
                            "calm after work."
                        ),
                    },
                ),
                no_match_reason=None,
            ),
            GeminiStructuredContent(
                content={}, input_tokens=400, output_tokens=40, total_tokens=440
            ),
        )
    )

    with caplog.at_level(logging.INFO, logger=GEMINI_DIAGNOSTIC_LOGGER):
        result = recommend_with_gemini(
            session,
            profile_id=profile_id,
            submission=_submission(),
            runtime=runtime,
            rerank=rerank,
        )

    assert result.status is RerankAssistantStatus.RANKED
    assert result.eligible_count == 1
    assert result.items[0].steam_app_id == 1
    assert result.items[0].cover_url.endswith("cover-1.jpg")
    assert result.items[0].summary == "A focused, low-pressure adventure."
    assert result.items[0].reasoning == (
        "Its calm pace fits your request for something calm after work."
    )
    assert rerank.call_count == 1
    assert rerank.call_args.kwargs["request"].candidates[0].steam_app_id == 1
    record = caplog.records[-1]
    assert record.event == "gemini_rerank_succeeded"
    assert record.model_id == "gemini-3.6-flash"
    assert record.candidate_count == 1
    assert record.input_tokens == 400
    assert record.output_tokens == 40
    assert record.total_tokens == 440
    assert "Something calm after work" not in record.getMessage()


def test_gemini_success_diagnostics_use_uvicorn_output_handler() -> None:
    """Route successful hosted calls through Uvicorn's configured handler."""
    logger = logging.getLogger(GEMINI_DIAGNOSTIC_LOGGER)
    uvicorn_logger = logging.getLogger("uvicorn.error")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    original_handlers = uvicorn_logger.handlers[:]
    original_level = uvicorn_logger.level
    original_propagate = uvicorn_logger.propagate
    try:
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.setLevel(logging.INFO)
        uvicorn_logger.propagate = False

        log_rerank_success(
            model_id="gemini-test-model",
            candidate_count=2,
            request_bytes=100,
            duration_ms=25,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )
    finally:
        uvicorn_logger.handlers = original_handlers
        uvicorn_logger.setLevel(original_level)
        uvicorn_logger.propagate = original_propagate

    assert logger.parent is uvicorn_logger
    assert logger.getEffectiveLevel() == logging.INFO
    assert "event=gemini_rerank_succeeded" in stream.getvalue()


def test_four_hundred_game_pool_still_uses_exactly_one_provider_call(
    session_and_profile: tuple[Session, int],
) -> None:
    session, profile_id = session_and_profile
    for steam_app_id in range(1, 401):
        _add_game(
            session,
            profile_id=profile_id,
            steam_app_id=steam_app_id,
            summary="A" * 1_200,
        )
    rerank = Mock(
        return_value=(
            RerankResponse(
                status="ranked",
                recommendations=(
                    {
                        "steam_app_id": 100,
                        "summary": "A focused, low-pressure adventure.",
                        "reasoning": (
                            "Its calm pace fits your request for something "
                            "calm after work."
                        ),
                    },
                ),
                no_match_reason=None,
            ),
            GeminiStructuredContent(
                content={}, input_tokens=8_000, output_tokens=40, total_tokens=8_040
            ),
        )
    )

    result = recommend_with_gemini(
        session,
        profile_id=profile_id,
        submission=_submission(),
        runtime=_runtime(),
        rerank=rerank,
    )

    assert result.status is RerankAssistantStatus.RANKED
    assert result.eligible_count == 400
    assert rerank.call_count == 1
    request = rerank.call_args.kwargs["request"]
    assert len(request.candidates) == 400
    assert all(len(candidate.summary or "") == 240 for candidate in request.candidates)


def test_oversized_payload_falls_back_before_provider_call(
    session_and_profile: tuple[Session, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, profile_id = session_and_profile
    _add_game(session, profile_id=profile_id, steam_app_id=1)
    monkeypatch.setattr(
        "app.gemini.reranking.service.rerank_user_prompt_size_bytes",
        lambda _request: 240_001,
    )
    rerank = Mock()

    result = recommend_with_gemini(
        session,
        profile_id=profile_id,
        submission=_submission(),
        runtime=_runtime(),
        rerank=rerank,
    )

    assert result.status is RerankAssistantStatus.UNAVAILABLE
    assert result.eligible_count == 1
    rerank.assert_not_called()


@pytest.mark.parametrize(
    ("game_count", "expected_status"),
    [
        (0, RerankAssistantStatus.EMPTY),
        (401, RerankAssistantStatus.NEEDS_REFINEMENT),
    ],
)
def test_stopped_pool_states_make_no_provider_call(
    session_and_profile: tuple[Session, int],
    game_count: int,
    expected_status: RerankAssistantStatus,
) -> None:
    session, profile_id = session_and_profile
    if game_count == 0:
        _add_game(
            session,
            profile_id=profile_id,
            steam_app_id=1,
            playtime_minutes=10,
        )
        submission = _submission().model_copy(
            update={"filters": RerankFilters(play_status="unplayed")}
        )
    else:
        for steam_app_id in range(1, game_count + 1):
            _add_game(session, profile_id=profile_id, steam_app_id=steam_app_id)
        submission = _submission()
    rerank = Mock()

    result = recommend_with_gemini(
        session,
        profile_id=profile_id,
        submission=submission,
        runtime=_runtime(),
        rerank=rerank,
    )

    assert result.status is expected_status
    assert result.eligible_count == game_count
    rerank.assert_not_called()


def test_missing_runtime_falls_back_before_provider_call(
    session_and_profile: tuple[Session, int],
) -> None:
    session, profile_id = session_and_profile
    _add_game(session, profile_id=profile_id, steam_app_id=1)

    result = recommend_with_gemini(
        session,
        profile_id=profile_id,
        submission=_submission(),
        runtime=None,
    )

    assert result.status is RerankAssistantStatus.UNAVAILABLE


def test_provider_failure_returns_safe_fallback(
    session_and_profile: tuple[Session, int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    session, profile_id = session_and_profile
    _add_game(session, profile_id=profile_id, steam_app_id=1)
    rerank = Mock(side_effect=GeminiUnavailableError("private provider detail"))

    with caplog.at_level(logging.ERROR, logger=GEMINI_DIAGNOSTIC_LOGGER):
        result = recommend_with_gemini(
            session,
            profile_id=profile_id,
            submission=_submission(),
            runtime=_runtime(),
            rerank=rerank,
        )

    assert result.status is RerankAssistantStatus.UNAVAILABLE
    assert result.message == (
        "AI recommendations are temporarily unavailable. "
        "Try guided recommendations instead."
    )
    assert "private" not in result.message
    assert result.diagnostic_reference is not None
    assert re.fullmatch(
        r"GEM-[A-F0-9]{12}", result.diagnostic_reference
    )
    assert rerank.call_count == 1
    record = caplog.records[-1]
    assert record.event == "gemini_rerank_failed"
    assert record.reference == result.diagnostic_reference
    assert record.failure_category == "provider_unavailable"
    assert record.candidate_count == 1
    assert record.request_bytes > 0
    assert "private provider detail" not in record.getMessage()


@pytest.mark.parametrize(
    ("error", "expected_category"),
    [
        (
            GeminiTimeoutError("late", reason_code="timeout"),
            "timeout",
        ),
        (
            GeminiConnectionError(
                "offline", reason_code="connection_error"
            ),
            "connection_error",
        ),
        (
            GeminiAuthenticationError("bad key", status_code=403),
            "authentication_rejected",
        ),
        (
            GeminiResponseError(
                "bad response", reason_code="invalid_output_json"
            ),
            "invalid_response",
        ),
        (
            GeminiAPIError("bad request", status_code=400),
            "provider_rejected",
        ),
    ],
)
def test_provider_failures_keep_distinct_safe_categories(
    session_and_profile: tuple[Session, int],
    caplog: pytest.LogCaptureFixture,
    error: GeminiAPIError,
    expected_category: str,
) -> None:
    session, profile_id = session_and_profile
    _add_game(session, profile_id=profile_id, steam_app_id=1)

    with caplog.at_level(logging.ERROR, logger=GEMINI_DIAGNOSTIC_LOGGER):
        result = recommend_with_gemini(
            session,
            profile_id=profile_id,
            submission=_submission(),
            runtime=_runtime(),
            rerank=Mock(side_effect=error),
        )

    assert result.status is RerankAssistantStatus.UNAVAILABLE
    assert result.diagnostic_reference is not None
    assert caplog.records[-1].failure_category == expected_category


def test_repeated_submissions_are_not_counted_or_blocked_locally(
    session_and_profile: tuple[Session, int],
) -> None:
    session, profile_id = session_and_profile
    _add_game(session, profile_id=profile_id, steam_app_id=1)
    rerank = Mock(return_value=_no_match_response())

    for _ in range(6):
        result = recommend_with_gemini(
            session,
            profile_id=profile_id,
            submission=_submission(),
            runtime=_runtime(),
            rerank=rerank,
        )
        assert result.status is RerankAssistantStatus.NO_MATCH

    assert rerank.call_count == 6


def test_provider_rate_limit_tells_user_to_try_again_tomorrow(
    session_and_profile: tuple[Session, int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    session, profile_id = session_and_profile
    _add_game(session, profile_id=profile_id, steam_app_id=1)
    rerank = Mock(
        side_effect=GeminiRateLimitError("limited", retry_after_seconds=120)
    )

    with caplog.at_level(logging.ERROR, logger=GEMINI_DIAGNOSTIC_LOGGER):
        result = recommend_with_gemini(
            session,
            profile_id=profile_id,
            submission=_submission(),
            runtime=_runtime(),
            rerank=rerank,
        )

    assert result.status is RerankAssistantStatus.UNAVAILABLE
    assert result.message == (
        "Ludex AI has reached Gemini's current usage limit. "
        "Please try again tomorrow, or use guided recommendations now."
    )
    assert result.diagnostic_reference is not None
    assert rerank.call_count == 1
    record = caplog.records[-1]
    assert record.failure_category == "rate_limited"
    assert record.retry_after_seconds == 120
