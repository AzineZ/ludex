from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
PositiveIdentifier = Annotated[int, Field(strict=True, gt=0)]
CompletionMinutes = Annotated[
    int,
    Field(strict=True, ge=30, le=60_000),
]


class FrozenContract(BaseModel):
    """Provide strict immutable behavior shared by preference contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


class PlayStatus(StrEnum):
    """Identify the requested Steam playtime state."""

    UNPLAYED = "unplayed"
    PREVIOUSLY_PLAYED = "previously_played"
    EITHER = "either"


class SelectedFacets(FrozenContract):
    """Store selected IGDB facet identities for one reference game."""

    genre_ids: tuple[PositiveIdentifier, ...]
    theme_ids: tuple[PositiveIdentifier, ...]
    keyword_ids: tuple[PositiveIdentifier, ...]
    game_mode_ids: tuple[PositiveIdentifier, ...]

    @field_validator(
        "genre_ids",
        "theme_ids",
        "keyword_ids",
        "game_mode_ids",
    )
    @classmethod
    def validate_and_sort_facet_ids(
        cls,
        facet_ids: tuple[int, ...],
    ) -> tuple[int, ...]:
        """Reject duplicate facet IDs and return canonical ordering."""
        if len(set(facet_ids)) != len(facet_ids):
            raise ValueError(
                "Facet IDs must be unique within their category."
            )

        return tuple(sorted(facet_ids))

    @field_validator("keyword_ids")
    @classmethod
    def limit_keywords(
        cls,
        keyword_ids: tuple[int, ...],
    ) -> tuple[int, ...]:
        """Limit one reference to three selected keywords."""
        if len(keyword_ids) > 3:
            raise ValueError(
                "Select no more than three keywords per reference game."
            )

        return keyword_ids

    @model_validator(mode="after")
    def require_selected_facet(self) -> "SelectedFacets":
        """Require at least one facet from this reference game."""
        if not any(
            (
                self.genre_ids,
                self.theme_ids,
                self.keyword_ids,
                self.game_mode_ids,
            )
        ):
            raise ValueError(
                "Select at least one facet from this reference game."
            )

        return self


class ReferencePreference(FrozenContract):
    """Store one reference game and the facets it contributes."""

    steam_app_id: PositiveIdentifier
    facets: SelectedFacets


class PreferenceConstraints(FrozenContract):
    """Store hard candidate-eligibility constraints."""

    maximum_completion_minutes: CompletionMinutes | None
    play_status: PlayStatus


class RecommendationPreference(FrozenContract):
    """Store one complete structurally validated preference."""

    references: tuple[ReferencePreference, ...]
    constraints: PreferenceConstraints

    @field_validator("references")
    @classmethod
    def validate_references(
        cls,
        references: tuple[ReferencePreference, ...],
    ) -> tuple[ReferencePreference, ...]:
        """Enforce reference count and identity uniqueness."""
        if not 1 <= len(references) <= 3:
            raise ValueError(
                "Select between one and three reference games."
            )

        steam_app_ids = [
            reference.steam_app_id for reference in references
        ]
        if len(set(steam_app_ids)) != len(steam_app_ids):
            raise ValueError("Reference games must be unique.")

        return references
