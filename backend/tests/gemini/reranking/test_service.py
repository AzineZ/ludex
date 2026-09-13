from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.gemini.client import (
    GeminiRateLimitError,
    GeminiStructuredContent,
    GeminiUnavailableError,
)
from app.gemini.prompt.quota import PromptQuotaPolicy
from app.gemini.reranking.contracts import RerankFilters, RerankResponse
from app.gemini.reranking.service import (
    GeminiRerankRuntime,
    RerankAssistantStatus,
    RerankSubmission,
    recommend_with_gemini,
)
from app.models import GeminiPromptReservation, GeminiPromptUsageEvent, Profile
from app.sessions.service import issue_access_session, resolve_access_session
from tests.gemini.reranking.test_candidate_pool import _add_game


NOW = datetime(2026, 9, 12, 17, tzinfo=UTC)


@pytest.fixture
def session_and_access() -> tuple[Session, int, int]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    profile = Profile(steam_id="76561198000000000", display_name="Player")
    session.add(profile)
    session.commit()
    issued = issue_access_session(
        session,
        profile.id,
        clock=lambda: NOW,
        token_generator=lambda: "assistant-session",
    )
    active = resolve_access_session(session, issued.token, clock=lambda: NOW)
    assert active is not None
    try:
        yield session, profile.id, active.id
    finally:
        session.close()
        engine.dispose()


def _runtime() -> GeminiRerankRuntime:
    return GeminiRerankRuntime(
        client=Mock(),
        model_id="gemini-3.6-flash",
        quota_policy=PromptQuotaPolicy(5, 20),
    )


def _submission() -> RerankSubmission:
    return RerankSubmission(
        prompt="Something calm after work",
        selected_genre_id=31,
        filters=RerankFilters(),
        rejected_steam_app_ids=(),
    )


def test_success_reserves_exactly_one_call_and_maps_snapshot_presentation(
    session_and_access: tuple[Session, int, int],
) -> None:
    session, profile_id, access_session_id = session_and_access
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
                    {"steam_app_id": 1, "reason": "A calm, focused fit."},
                ),
                no_match_reason=None,
            ),
            GeminiStructuredContent(
                content={}, input_tokens=400, output_tokens=40, total_tokens=440
            ),
        )
    )

    result = recommend_with_gemini(
        session,
        access_session_id=access_session_id,
        profile_id=profile_id,
        submission=_submission(),
        runtime=runtime,
        now=NOW,
        rerank=rerank,
    )

    assert result.status is RerankAssistantStatus.RANKED
    assert result.eligible_count == 1
    assert result.items[0].steam_app_id == 1
    assert result.items[0].cover_url.endswith("cover-1.jpg")
    assert result.items[0].reason == "A calm, focused fit."
    assert rerank.call_count == 1
    assert rerank.call_args.kwargs["request"].candidates[0].steam_app_id == 1
    assert session.scalar(select(GeminiPromptUsageEvent)) is not None
    reservation = session.scalar(select(GeminiPromptReservation))
    assert reservation is not None
    assert reservation.completed_at is not None


@pytest.mark.parametrize(
    ("game_count", "expected_status"),
    [
        (0, RerankAssistantStatus.EMPTY),
        (31, RerankAssistantStatus.NEEDS_REFINEMENT),
    ],
)
def test_stopped_pool_states_make_no_call_and_consume_no_quota(
    session_and_access: tuple[Session, int, int],
    game_count: int,
    expected_status: RerankAssistantStatus,
) -> None:
    session, profile_id, access_session_id = session_and_access
    if game_count == 0:
        _add_game(
            session,
            profile_id=profile_id,
            steam_app_id=1,
            playtime_minutes=10,
        )
        submission = _submission().model_copy(
            update={
                "filters": RerankFilters(play_status="unplayed"),
            }
        )
    else:
        for steam_app_id in range(1, game_count + 1):
            _add_game(
                session,
                profile_id=profile_id,
                steam_app_id=steam_app_id,
            )
        submission = _submission()
    rerank = Mock()

    result = recommend_with_gemini(
        session,
        access_session_id=access_session_id,
        profile_id=profile_id,
        submission=submission,
        runtime=_runtime(),
        now=NOW,
        rerank=rerank,
    )

    assert result.status is expected_status
    assert result.eligible_count == game_count
    rerank.assert_not_called()
    assert session.scalar(select(GeminiPromptUsageEvent)) is None


def test_missing_runtime_falls_back_before_quota_reservation(
    session_and_access: tuple[Session, int, int],
) -> None:
    session, profile_id, access_session_id = session_and_access
    _add_game(session, profile_id=profile_id, steam_app_id=1)

    result = recommend_with_gemini(
        session,
        access_session_id=access_session_id,
        profile_id=profile_id,
        submission=_submission(),
        runtime=None,
        now=NOW,
    )

    assert result.status is RerankAssistantStatus.UNAVAILABLE
    assert session.scalar(select(GeminiPromptReservation)) is None


def test_provider_failure_releases_reservation_and_returns_safe_fallback(
    session_and_access: tuple[Session, int, int],
) -> None:
    session, profile_id, access_session_id = session_and_access
    _add_game(session, profile_id=profile_id, steam_app_id=1)
    rerank = Mock(side_effect=GeminiUnavailableError("private provider detail"))

    result = recommend_with_gemini(
        session,
        access_session_id=access_session_id,
        profile_id=profile_id,
        submission=_submission(),
        runtime=_runtime(),
        now=NOW,
        rerank=rerank,
    )

    assert result.status is RerankAssistantStatus.UNAVAILABLE
    assert result.message == (
        "AI recommendations are temporarily unavailable. "
        "Try guided recommendations instead."
    )
    assert "private" not in result.message
    assert session.scalar(select(GeminiPromptUsageEvent)) is not None
    reservation = session.scalar(select(GeminiPromptReservation))
    assert reservation is not None
    assert reservation.completed_at is not None


def test_session_daily_limit_falls_back_without_an_extra_provider_call(
    session_and_access: tuple[Session, int, int],
) -> None:
    session, profile_id, access_session_id = session_and_access
    _add_game(session, profile_id=profile_id, steam_app_id=1)
    runtime = _runtime()
    successful_rerank = Mock(
        return_value=(
            RerankResponse(
                status="no_match",
                recommendations=(),
                no_match_reason="No supplied game fits.",
            ),
            GeminiStructuredContent(
                content={}, input_tokens=None, output_tokens=None, total_tokens=None
            ),
        )
    )
    for index in range(5):
        result = recommend_with_gemini(
            session,
            access_session_id=access_session_id,
            profile_id=profile_id,
            submission=_submission(),
            runtime=runtime,
            now=NOW + timedelta(minutes=index * 2),
            rerank=successful_rerank,
        )
        assert result.status is RerankAssistantStatus.NO_MATCH

    limited = recommend_with_gemini(
        session,
        access_session_id=access_session_id,
        profile_id=profile_id,
        submission=_submission(),
        runtime=runtime,
        now=NOW + timedelta(minutes=11),
        rerank=successful_rerank,
    )

    assert limited.status is RerankAssistantStatus.UNAVAILABLE
    assert successful_rerank.call_count == 5


def test_provider_rate_limit_opens_circuit_for_the_next_submission(
    session_and_access: tuple[Session, int, int],
) -> None:
    session, profile_id, access_session_id = session_and_access
    _add_game(session, profile_id=profile_id, steam_app_id=1)
    rerank = Mock(
        side_effect=GeminiRateLimitError(
            "limited", retry_after_seconds=120
        )
    )

    first = recommend_with_gemini(
        session,
        access_session_id=access_session_id,
        profile_id=profile_id,
        submission=_submission(),
        runtime=_runtime(),
        now=NOW,
        rerank=rerank,
    )
    second = recommend_with_gemini(
        session,
        access_session_id=access_session_id,
        profile_id=profile_id,
        submission=_submission(),
        runtime=_runtime(),
        now=NOW + timedelta(seconds=1),
        rerank=rerank,
    )

    assert first.status is RerankAssistantStatus.UNAVAILABLE
    assert second.status is RerankAssistantStatus.UNAVAILABLE
    assert rerank.call_count == 1
