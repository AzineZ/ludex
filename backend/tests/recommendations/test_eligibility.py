from dataclasses import FrozenInstanceError

import pytest

from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.contracts import PlayStatus
from app.recommendations.eligibility import (
    EligibilityExclusionReason,
    evaluate_candidate_eligibility,
)


def _candidate(
    *,
    steam_app_id: int = 500,
    owned_by_selected_profile: bool = True,
    total_playtime_minutes: int = 0,
    normal_completion_seconds: int | None = 3_600,
) -> CandidateFacts:
    return CandidateFacts(
        steam_app_id=steam_app_id,
        owned_by_selected_profile=owned_by_selected_profile,
        total_playtime_minutes=total_playtime_minutes,
        normal_completion_seconds=normal_completion_seconds,
        genre_ids=(10,),
        theme_ids=(20,),
        keyword_ids=(30,),
        game_mode_ids=(40,),
    )


def test_candidate_facts_are_immutable() -> None:
    candidate = _candidate()

    with pytest.raises(FrozenInstanceError):
        candidate.steam_app_id = 999  # type: ignore[misc]


def test_identity_rules_accept_an_owned_nonexcluded_candidate() -> None:
    decision = evaluate_candidate_eligibility(
        _candidate(),
        reference_steam_app_ids=frozenset({101, 202}),
        session_excluded_steam_app_ids=frozenset({909}),
        play_status=PlayStatus.EITHER,
        maximum_completion_minutes=None,
    )

    assert decision.eligible is True
    assert decision.exclusion_reasons == ()


@pytest.mark.parametrize(
    ("candidate", "references", "session_exclusions", "reason"),
    [
        (
            _candidate(owned_by_selected_profile=False),
            frozenset(),
            frozenset(),
            EligibilityExclusionReason.NOT_OWNED,
        ),
        (
            _candidate(steam_app_id=101),
            frozenset({101, 202}),
            frozenset(),
            EligibilityExclusionReason.SELECTED_REFERENCE,
        ),
        (
            _candidate(steam_app_id=909),
            frozenset(),
            frozenset({909}),
            EligibilityExclusionReason.SESSION_EXCLUDED,
        ),
    ],
)
def test_each_identity_rule_returns_an_inspectable_reason(
    candidate: CandidateFacts,
    references: frozenset[int],
    session_exclusions: frozenset[int],
    reason: EligibilityExclusionReason,
) -> None:
    decision = evaluate_candidate_eligibility(
        candidate,
        reference_steam_app_ids=references,
        session_excluded_steam_app_ids=session_exclusions,
        play_status=PlayStatus.EITHER,
        maximum_completion_minutes=None,
    )

    assert decision.eligible is False
    assert decision.exclusion_reasons == (reason,)


def test_identity_rules_return_all_reasons_in_canonical_order() -> None:
    candidate = _candidate(
        steam_app_id=101,
        owned_by_selected_profile=False,
    )

    decision = evaluate_candidate_eligibility(
        candidate,
        reference_steam_app_ids=frozenset({101}),
        session_excluded_steam_app_ids=frozenset({101}),
        play_status=PlayStatus.EITHER,
        maximum_completion_minutes=None,
    )

    assert decision.eligible is False
    assert decision.exclusion_reasons == (
        EligibilityExclusionReason.NOT_OWNED,
        EligibilityExclusionReason.SELECTED_REFERENCE,
        EligibilityExclusionReason.SESSION_EXCLUDED,
    )


@pytest.mark.parametrize(
    ("play_status", "playtime_minutes"),
    [
        (PlayStatus.UNPLAYED, 0),
        (PlayStatus.PREVIOUSLY_PLAYED, 1),
        (PlayStatus.EITHER, 0),
        (PlayStatus.EITHER, 1),
    ],
)
def test_play_status_accepts_exact_matching_boundaries(
    play_status: PlayStatus,
    playtime_minutes: int,
) -> None:
    decision = evaluate_candidate_eligibility(
        _candidate(total_playtime_minutes=playtime_minutes),
        reference_steam_app_ids=frozenset(),
        session_excluded_steam_app_ids=frozenset(),
        play_status=play_status,
        maximum_completion_minutes=None,
    )

    assert decision.eligible is True
    assert decision.exclusion_reasons == ()


@pytest.mark.parametrize(
    ("play_status", "playtime_minutes"),
    [
        (PlayStatus.UNPLAYED, 1),
        (PlayStatus.PREVIOUSLY_PLAYED, 0),
    ],
)
def test_play_status_rejects_the_opposite_playtime_state(
    play_status: PlayStatus,
    playtime_minutes: int,
) -> None:
    decision = evaluate_candidate_eligibility(
        _candidate(total_playtime_minutes=playtime_minutes),
        reference_steam_app_ids=frozenset(),
        session_excluded_steam_app_ids=frozenset(),
        play_status=play_status,
        maximum_completion_minutes=None,
    )

    assert decision.eligible is False
    assert decision.exclusion_reasons == (
        EligibilityExclusionReason.PLAY_STATUS_MISMATCH,
    )


def test_play_status_reason_follows_identity_reasons() -> None:
    decision = evaluate_candidate_eligibility(
        _candidate(
            steam_app_id=101,
            owned_by_selected_profile=False,
            total_playtime_minutes=1,
        ),
        reference_steam_app_ids=frozenset({101}),
        session_excluded_steam_app_ids=frozenset({101}),
        play_status=PlayStatus.UNPLAYED,
        maximum_completion_minutes=None,
    )

    assert decision.exclusion_reasons == (
        EligibilityExclusionReason.NOT_OWNED,
        EligibilityExclusionReason.SELECTED_REFERENCE,
        EligibilityExclusionReason.SESSION_EXCLUDED,
        EligibilityExclusionReason.PLAY_STATUS_MISMATCH,
    )


@pytest.mark.parametrize(
    "normal_completion_seconds",
    [None, 0, 3_600, 100_000],
)
def test_completion_time_is_not_a_constraint_without_a_maximum(
    normal_completion_seconds: int | None,
) -> None:
    decision = evaluate_candidate_eligibility(
        _candidate(
            normal_completion_seconds=normal_completion_seconds,
        ),
        reference_steam_app_ids=frozenset(),
        session_excluded_steam_app_ids=frozenset(),
        play_status=PlayStatus.EITHER,
        maximum_completion_minutes=None,
    )

    assert decision.eligible is True
    assert decision.exclusion_reasons == ()


def test_missing_optional_facets_do_not_make_candidate_ineligible() -> None:
    candidate = CandidateFacts(
        steam_app_id=505,
        owned_by_selected_profile=True,
        total_playtime_minutes=0,
        normal_completion_seconds=3_600,
        genre_ids=None,
        theme_ids=None,
        keyword_ids=None,
        game_mode_ids=None,
    )

    decision = evaluate_candidate_eligibility(
        candidate,
        reference_steam_app_ids=frozenset(),
        session_excluded_steam_app_ids=frozenset(),
        play_status=PlayStatus.EITHER,
        maximum_completion_minutes=None,
    )

    assert decision.eligible is True
    assert decision.exclusion_reasons == ()


def test_completion_time_equal_to_the_maximum_is_eligible() -> None:
    decision = evaluate_candidate_eligibility(
        _candidate(normal_completion_seconds=3_600),
        reference_steam_app_ids=frozenset(),
        session_excluded_steam_app_ids=frozenset(),
        play_status=PlayStatus.EITHER,
        maximum_completion_minutes=60,
    )

    assert decision.eligible is True
    assert decision.exclusion_reasons == ()


def test_completion_time_one_second_over_the_maximum_is_excluded() -> None:
    decision = evaluate_candidate_eligibility(
        _candidate(normal_completion_seconds=3_601),
        reference_steam_app_ids=frozenset(),
        session_excluded_steam_app_ids=frozenset(),
        play_status=PlayStatus.EITHER,
        maximum_completion_minutes=60,
    )

    assert decision.eligible is False
    assert decision.exclusion_reasons == (
        EligibilityExclusionReason.COMPLETION_TIME_EXCEEDS_MAXIMUM,
    )


def test_unknown_completion_time_is_excluded_when_maximum_exists() -> None:
    decision = evaluate_candidate_eligibility(
        _candidate(normal_completion_seconds=None),
        reference_steam_app_ids=frozenset(),
        session_excluded_steam_app_ids=frozenset(),
        play_status=PlayStatus.EITHER,
        maximum_completion_minutes=60,
    )

    assert decision.eligible is False
    assert decision.exclusion_reasons == (
        EligibilityExclusionReason.COMPLETION_TIME_UNKNOWN,
    )


def test_conflicting_constraints_return_every_reason_in_order() -> None:
    decision = evaluate_candidate_eligibility(
        _candidate(
            steam_app_id=101,
            total_playtime_minutes=1,
            normal_completion_seconds=None,
        ),
        reference_steam_app_ids=frozenset({101, 202}),
        session_excluded_steam_app_ids=frozenset({101, 909}),
        play_status=PlayStatus.UNPLAYED,
        maximum_completion_minutes=60,
    )

    assert decision.eligible is False
    assert decision.exclusion_reasons == (
        EligibilityExclusionReason.SELECTED_REFERENCE,
        EligibilityExclusionReason.SESSION_EXCLUDED,
        EligibilityExclusionReason.PLAY_STATUS_MISMATCH,
        EligibilityExclusionReason.COMPLETION_TIME_UNKNOWN,
    )
