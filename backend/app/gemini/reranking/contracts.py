from enum import StrEnum
from hashlib import sha256
from json import dumps
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.recommendations.contracts import CompletionMinutes, PlayStatus


MAX_RERANK_CANDIDATES = 200
MAX_RERANK_RESULTS = 6
MAX_RERANK_PROMPT_CHARACTERS = 500
MAX_RERANK_SUMMARY_CHARACTERS = 1200
MAX_RERANK_OUTPUT_SUMMARY_CHARACTERS = 240
MAX_RERANK_REASONING_CHARACTERS = 240
MAX_RERANK_NO_MATCH_CHARACTERS = 240
MAX_RERANK_SESSION_EXCLUSIONS = 30

PositiveID = Annotated[int, Field(strict=True, gt=0)]
NonnegativeMinutes = Annotated[int, Field(strict=True, ge=0)]


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _single_line(value: str) -> str:
    return " ".join(value.split())


class RerankFilters(FrozenContract):
    """Represent only explicit backend-enforced candidate filters."""

    play_status: PlayStatus = PlayStatus.EITHER
    maximum_completion_minutes: CompletionMinutes | None = None
    theme_ids: tuple[PositiveID, ...] = Field(default=(), max_length=8)
    game_mode_ids: tuple[PositiveID, ...] = Field(default=(), max_length=8)

    @field_validator("theme_ids", "game_mode_ids")
    @classmethod
    def reject_duplicate_ids(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if len(values) != len(set(values)):
            raise ValueError("Filter IDs must be unique.")
        return values


class RerankCandidate(FrozenContract):
    """Hold the bounded cached facts supplied for one allowed game."""

    steam_app_id: PositiveID
    title: str = Field(min_length=1, max_length=255)
    summary: str | None = Field(
        default=None,
        max_length=MAX_RERANK_SUMMARY_CHARACTERS,
    )
    genres: tuple[str, ...] = Field(max_length=8)
    themes: tuple[str, ...] = Field(max_length=8)
    keywords: tuple[str, ...] = Field(max_length=12)
    game_modes: tuple[str, ...] = Field(max_length=8)
    profile_playtime_minutes: NonnegativeMinutes
    normal_completion_minutes: NonnegativeMinutes | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = _single_line(value)
        if not normalized:
            raise ValueError("Candidate title must not be blank.")
        return normalized

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _single_line(value)
        return normalized or None

    @field_validator("genres", "themes", "keywords", "game_modes")
    @classmethod
    def normalize_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_single_line(value) for value in values)
        if any(not value or len(value) > 100 for value in normalized):
            raise ValueError("Candidate labels must be 1 to 100 characters.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Candidate labels must be unique.")
        return normalized


class RerankRequest(FrozenContract):
    """Freeze one prompt and its complete already-eligible candidate set."""

    prompt: str = Field(
        min_length=1,
        max_length=MAX_RERANK_PROMPT_CHARACTERS,
    )
    selected_genre_id: PositiveID
    selected_genre_name: str = Field(min_length=1, max_length=100)
    filters: RerankFilters
    candidates: tuple[RerankCandidate, ...] = Field(
        min_length=1,
        max_length=MAX_RERANK_CANDIDATES,
    )

    @field_validator("prompt", "selected_genre_name")
    @classmethod
    def normalize_request_text(cls, value: str) -> str:
        normalized = _single_line(value)
        if not normalized:
            raise ValueError("Reranking request text must not be blank.")
        return normalized

    @field_validator("candidates")
    @classmethod
    def reject_duplicate_candidates(
        cls,
        candidates: tuple[RerankCandidate, ...],
    ) -> tuple[RerankCandidate, ...]:
        identities = [candidate.steam_app_id for candidate in candidates]
        if len(identities) != len(set(identities)):
            raise ValueError("Reranking candidate IDs must be unique.")
        return candidates

    @model_validator(mode="after")
    def require_selected_genre_on_every_candidate(self) -> "RerankRequest":
        if any(
            self.selected_genre_name not in candidate.genres
            for candidate in self.candidates
        ):
            raise ValueError(
                "Every reranking candidate must match the selected genre."
            )
        return self

    @property
    def snapshot_fingerprint(self) -> str:
        """Identify the exact prompt, filters, and candidate snapshot."""
        serialized = dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(serialized.encode("utf-8")).hexdigest()


class RerankStatus(StrEnum):
    RANKED = "ranked"
    NO_MATCH = "no_match"


class RerankRecommendation(FrozenContract):
    steam_app_id: PositiveID
    summary: str = Field(
        min_length=1,
        max_length=MAX_RERANK_OUTPUT_SUMMARY_CHARACTERS,
    )
    reasoning: str = Field(
        min_length=1,
        max_length=MAX_RERANK_REASONING_CHARACTERS,
    )

    @field_validator("summary", "reasoning")
    @classmethod
    def normalize_recommendation_text(cls, value: str) -> str:
        normalized = _single_line(value)
        if not normalized:
            raise ValueError("Recommendation text must not be blank.")
        return normalized


class RerankResponse(FrozenContract):
    status: RerankStatus
    recommendations: tuple[RerankRecommendation, ...] = Field(
        max_length=MAX_RERANK_RESULTS
    )
    no_match_reason: str | None = Field(
        default=None,
        max_length=MAX_RERANK_NO_MATCH_CHARACTERS,
    )

    @field_validator("no_match_reason")
    @classmethod
    def normalize_no_match_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _single_line(value)
        return normalized or None

    @model_validator(mode="after")
    def validate_shape(self) -> "RerankResponse":
        identities = [item.steam_app_id for item in self.recommendations]
        if len(identities) != len(set(identities)):
            raise ValueError("Recommendation IDs must be unique.")
        if self.status is RerankStatus.RANKED:
            if not self.recommendations or self.no_match_reason is not None:
                raise ValueError("Ranked responses require only recommendations.")
        elif self.recommendations or self.no_match_reason is None:
            raise ValueError("No-match responses require only a reason.")
        return self
