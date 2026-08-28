from dataclasses import dataclass
from enum import StrEnum

from app.recommendations.candidate_facts import CandidateFacts
from app.recommendations.contracts import PlayStatus


class EligibilityExclusionReason(StrEnum):
    """Identify one hard candidate-eligibility failure."""

    NOT_OWNED = "not_owned"
    SELECTED_REFERENCE = "selected_reference"
    SESSION_EXCLUDED = "session_excluded"
    PLAY_STATUS_MISMATCH = "play_status_mismatch"
    COMPLETION_TIME_EXCEEDS_MAXIMUM = (
        "completion_time_exceeds_maximum"
    )
    COMPLETION_TIME_UNKNOWN = "completion_time_unknown"


@dataclass(frozen=True)
class EligibilityDecision:
    """Report whether a candidate passed every hard rule."""

    eligible: bool
    exclusion_reasons: tuple[EligibilityExclusionReason, ...]


def evaluate_candidate_eligibility(
    candidate: CandidateFacts,
    *,
    reference_steam_app_ids: frozenset[int],
    session_excluded_steam_app_ids: frozenset[int],
    play_status: PlayStatus,
    maximum_completion_minutes: int | None,
) -> EligibilityDecision:
    """Evaluate hard rules without database or provider access."""
    reasons: list[EligibilityExclusionReason] = []

    if not candidate.owned_by_selected_profile:
        reasons.append(EligibilityExclusionReason.NOT_OWNED)

    if candidate.steam_app_id in reference_steam_app_ids:
        reasons.append(
            EligibilityExclusionReason.SELECTED_REFERENCE
        )

    if candidate.steam_app_id in session_excluded_steam_app_ids:
        reasons.append(EligibilityExclusionReason.SESSION_EXCLUDED)

    play_status_mismatch = (
        play_status is PlayStatus.UNPLAYED
        and candidate.total_playtime_minutes != 0
    ) or (
        play_status is PlayStatus.PREVIOUSLY_PLAYED
        and candidate.total_playtime_minutes == 0
    )
    if play_status_mismatch:
        reasons.append(
            EligibilityExclusionReason.PLAY_STATUS_MISMATCH
        )

    if maximum_completion_minutes is not None:
        maximum_completion_seconds = (
            maximum_completion_minutes * 60
        )
        if candidate.normal_completion_seconds is None:
            reasons.append(
                EligibilityExclusionReason.COMPLETION_TIME_UNKNOWN
            )
        elif (
            candidate.normal_completion_seconds
            > maximum_completion_seconds
        ):
            reasons.append(
                EligibilityExclusionReason
                .COMPLETION_TIME_EXCEEDS_MAXIMUM
            )

    exclusion_reasons = tuple(reasons)
    return EligibilityDecision(
        eligible=not exclusion_reasons,
        exclusion_reasons=exclusion_reasons,
    )
