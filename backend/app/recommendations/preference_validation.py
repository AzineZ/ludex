from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
)
from app.recommendations.contracts import RecommendationPreference


class PreferenceValidationCode(StrEnum):
    """Identify one database-backed preference validation failure."""

    TOO_MANY_KEYWORDS = "too_many_keywords"
    PROFILE_NOT_FOUND = "profile_not_found"
    REFERENCE_NOT_OWNED = "reference_not_owned"
    REFERENCE_METADATA_UNAVAILABLE = (
        "reference_metadata_unavailable"
    )
    FACET_NOT_ON_REFERENCE = "facet_not_on_reference"


@dataclass(frozen=True)
class PreferenceValidationIssue:
    """Describe one deterministic preference validation failure."""

    code: PreferenceValidationCode
    field: str
    message: str


class PreferenceValidationError(ValueError):
    """Report a database-backed preference validation failure."""

    def __init__(
        self,
        issue: PreferenceValidationIssue,
    ) -> None:
        """Store the structured issue and expose its message."""
        self.issue = issue
        super().__init__(issue.message)


@dataclass(frozen=True)
class ValidatedRecommendationPreference:
    """Mark an immutable preference as database validated."""

    preference: RecommendationPreference


def _raise_issue(
    code: PreferenceValidationCode,
    field: str,
    message: str,
) -> NoReturn:
    """Raise one structured validation issue."""
    raise PreferenceValidationError(
        PreferenceValidationIssue(
            code=code,
            field=field,
            message=message,
        )
    )


def _recheck_keyword_limits(
    preference: RecommendationPreference,
) -> None:
    """Defend against contracts constructed without validation."""
    for reference_index, reference in enumerate(
        preference.references
    ):
        if len(reference.facets.keyword_ids) > 3:
            _raise_issue(
                PreferenceValidationCode.TOO_MANY_KEYWORDS,
                (
                    f"references[{reference_index}]"
                    ".facets.keyword_ids"
                ),
                (
                    "Select no more than three keywords "
                    "per reference game."
                ),
            )


def _require_valid_profile_identity(profile_id: object) -> None:
    """Reject identities that cannot denote a stored profile."""
    if (
        not isinstance(profile_id, int)
        or isinstance(profile_id, bool)
        or profile_id <= 0
    ):
        _raise_issue(
            PreferenceValidationCode.PROFILE_NOT_FOUND,
            "profile_id",
            "The selected profile does not exist.",
        )


def validate_preference(
    session: Session,
    profile_id: int,
    preference: RecommendationPreference,
) -> ValidatedRecommendationPreference:
    """Validate stored identities in one immutable preference.

    Validation uses one cache-only database statement. Failures follow
    deterministic precedence: keyword limit, profile, ownership,
    metadata readiness, then exact facet membership.

    Args:
        session: Database session used only for cached reads.
        profile_id: Selected local profile identity.
        preference: Structurally validated recommendation preference.

    Returns:
        A frozen wrapper marking the preference as database validated.

    Raises:
        PreferenceValidationError: If any stored identity or
            relationship fails validation.
    """
    _recheck_keyword_limits(preference)
    _require_valid_profile_identity(profile_id)

    requested_steam_app_ids = tuple(
        reference.steam_app_id
        for reference in preference.references
    )

    statement = (
        select(
            Profile.id.label("profile_id"),
            Game.steam_app_id.label("steam_app_id"),
            Game.igdb_status.label("metadata_status"),
            IGDBMetadataTerm.kind.label("facet_kind"),
            IGDBMetadataTerm.igdb_id.label("facet_igdb_id"),
        )
        .select_from(Profile)
        .outerjoin(
            ProfileGame,
            and_(
                ProfileGame.profile_id == Profile.id,
                ProfileGame.steam_app_id.in_(
                    requested_steam_app_ids
                ),
            ),
        )
        .outerjoin(
            Game,
            Game.steam_app_id == ProfileGame.steam_app_id,
        )
        .outerjoin(
            GameIGDBMetadataTerm,
            (
                GameIGDBMetadataTerm.steam_app_id
                == Game.steam_app_id
            ),
        )
        .outerjoin(
            IGDBMetadataTerm,
            (
                IGDBMetadataTerm.id
                == GameIGDBMetadataTerm.term_id
            ),
        )
        .where(Profile.id == profile_id)
        .execution_options(autoflush=False)
    )

    rows = session.execute(statement).all()

    if not rows:
        _raise_issue(
            PreferenceValidationCode.PROFILE_NOT_FOUND,
            "profile_id",
            "The selected profile does not exist.",
        )

    metadata_statuses: dict[int, str] = {}
    memberships: dict[int, set[tuple[str, int]]] = {
        steam_app_id: set()
        for steam_app_id in requested_steam_app_ids
    }

    for row in rows:
        if row.steam_app_id is None:
            continue

        metadata_statuses[row.steam_app_id] = (
            row.metadata_status
        )

        if (
            row.facet_kind is not None
            and row.facet_igdb_id is not None
        ):
            memberships[row.steam_app_id].add(
                (
                    row.facet_kind,
                    row.facet_igdb_id,
                )
            )

    for reference_index, reference in enumerate(
        preference.references
    ):
        if reference.steam_app_id not in metadata_statuses:
            _raise_issue(
                PreferenceValidationCode.REFERENCE_NOT_OWNED,
                (
                    f"references[{reference_index}]"
                    ".steam_app_id"
                ),
                (
                    "The selected reference game is not owned "
                    "by this profile."
                ),
            )

    for reference_index, reference in enumerate(
        preference.references
    ):
        if (
            metadata_statuses[reference.steam_app_id]
            != "ready"
        ):
            _raise_issue(
                (
                    PreferenceValidationCode
                    .REFERENCE_METADATA_UNAVAILABLE
                ),
                (
                    f"references[{reference_index}]"
                    ".steam_app_id"
                ),
                (
                    "Factual metadata is unavailable for this "
                    "reference game."
                ),
            )

    for reference_index, reference in enumerate(
        preference.references
    ):
        facet_categories = (
            (
                "genre",
                "genre_ids",
                reference.facets.genre_ids,
            ),
            (
                "theme",
                "theme_ids",
                reference.facets.theme_ids,
            ),
            (
                "keyword",
                "keyword_ids",
                reference.facets.keyword_ids,
            ),
            (
                "game_mode",
                "game_mode_ids",
                reference.facets.game_mode_ids,
            ),
        )
        stored_memberships = memberships[
            reference.steam_app_id
        ]

        for (
            facet_kind,
            field_name,
            selected_ids,
        ) in facet_categories:
            for facet_index, facet_id in enumerate(
                selected_ids
            ):
                if (
                    facet_kind,
                    facet_id,
                ) not in stored_memberships:
                    _raise_issue(
                        (
                            PreferenceValidationCode
                            .FACET_NOT_ON_REFERENCE
                        ),
                        (
                            f"references[{reference_index}]"
                            f".facets.{field_name}"
                            f"[{facet_index}]"
                        ),
                        (
                            "The selected facet does not belong "
                            "to this reference game."
                        ),
                    )

    return ValidatedRecommendationPreference(
        preference=preference
    )
