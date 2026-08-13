from decimal import Decimal
from hashlib import sha256
from json import dumps
import re
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


MIN_KNOWN_CONFIDENCE = Decimal("0.30")

_ABSENCE_BASED_EVIDENCE_PATTERNS = (
    re.compile(r"\bno (?:explicit )?mention of\b", re.IGNORECASE),
    re.compile(
        r"\b(?:is|are|was|were) not mentioned\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:do|does|did) not mention\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:don't|doesn't|didn't) mention\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:information|details?|facts?|metadata) "
        r"(?:is|are|was|were) absent\b",
        re.IGNORECASE,
    ),
)

TraitScore = Annotated[
    int,
    Field(strict=True, ge=0, le=5),
]

Confidence = Annotated[
    Decimal,
    Field(
        ge=Decimal("0"),
        le=Decimal("1"),
        multiple_of=Decimal("0.01"),
    ),
]

KnownConfidence = Annotated[
    Decimal,
    Field(
        ge=MIN_KNOWN_CONFIDENCE,
        le=Decimal("1"),
        multiple_of=Decimal("0.01"),
    ),
]

FactText = Annotated[
    str,
    Field(min_length=1, max_length=255),
]

NUMERIC_TRAIT_FIELDS = (
    "story_focus",
    "combat_intensity",
    "difficulty",
    "pacing",
    "session_friendliness",
    "exploration_focus",
)

EvidenceField = Literal[
    "summary",
    "genre",
    "theme",
    "keyword",
    "game_mode",
    "time_to_beat",
    "release_information",
]

MoodLabel = Literal[
    "relaxing",
    "tense",
    "emotional",
    "humorous",
    "dark",
]


class TraitEvidenceError(ValueError):
    """Indicate that derived evidence is absent from the supplied facts."""


class EvidenceCitation(BaseModel):
    """Represent one factual citation supporting a derived interpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: EvidenceField
    value: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=200)

    @field_validator("value", "reason")
    @classmethod
    def validate_bounded_text(cls, value: str) -> str:
        """Reject surrounding whitespace and multiline evidence text.

        Args:
            value: Citation value or explanatory reason.

        Returns:
            The validated text without modifying it.

        Raises:
            ValueError: If the text contains surrounding whitespace or
                multiple lines.
        """
        if value != value.strip():
            raise ValueError(
                "Evidence text must not contain surrounding whitespace."
            )

        if "\n" in value or "\r" in value:
            raise ValueError("Evidence text must use one line.")

        return value

    @field_validator("reason")
    @classmethod
    def validate_single_sentence(cls, value: str) -> str:
        """Require one simply punctuated evidence sentence.

        Args:
            value: The already validated evidence reason.

        Returns:
            The validated single sentence.

        Raises:
            ValueError: If the reason lacks terminal punctuation or contains
                more than one sentence.
        """
        sentence_marks = (".", "!", "?")

        if not value.endswith(sentence_marks):
            raise ValueError(
                "Evidence reasons must end with sentence punctuation."
            )

        if any(mark in value[:-1] for mark in sentence_marks):
            raise ValueError(
                "Evidence reasons must contain exactly one sentence."
            )

        return value

    @field_validator("reason")
    @classmethod
    def reject_absence_based_reason(cls, value: str) -> str:
        """Reject evidence reasoning based only on missing information.

        Args:
            value: The structurally valid evidence reason.

        Returns:
            The reason when it makes a positive evidence claim.

        Raises:
            ValueError: If the reason treats an unmentioned or absent fact as
                support for a derived interpretation.
        """
        if any(
            pattern.search(value)
            for pattern in _ABSENCE_BASED_EVIDENCE_PATTERNS
        ):
            raise ValueError(
                "Absence of information cannot support evidence."
            )

        return value


class GameTraitFacts(BaseModel):
    """Represent the canonical factual payload supplied to Gemini."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: FactText
    summary: str | None
    genres: tuple[FactText, ...]
    themes: tuple[FactText, ...]
    keywords: tuple[FactText, ...]
    game_modes: tuple[FactText, ...]
    time_to_beat: tuple[FactText, ...]
    release_information: tuple[FactText, ...]

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Normalize the factual game name.

        Args:
            value: Game name loaded from trusted metadata.

        Returns:
            The name without surrounding whitespace.

        Raises:
            ValueError: If normalization leaves an empty name.
        """
        normalized = value.strip()

        if not normalized:
            raise ValueError("Game names must not be blank.")

        return normalized

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        """Normalize an optional factual summary.

        Args:
            value: Summary loaded from trusted metadata, when available.

        Returns:
            A trimmed summary, or None when the summary is absent or blank.
        """
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator(
        "genres",
        "themes",
        "keywords",
        "game_modes",
        "time_to_beat",
        "release_information",
    )
    @classmethod
    def normalize_fact_collection(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Normalize one repeatable factual metadata collection.

        Args:
            values: Metadata values belonging to one factual field.

        Returns:
            Unique trimmed values in deterministic alphabetical order.

        Raises:
            ValueError: If any supplied value becomes blank after trimming.
        """
        normalized_values: set[str] = set()

        for value in values:
            normalized = value.strip()

            if not normalized:
                raise ValueError("Factual metadata values must not be blank.")

            normalized_values.add(normalized)

        return tuple(
            sorted(
                normalized_values,
                key=lambda item: (item.casefold(), item),
            )
        )

    def supports_evidence(self, citation: EvidenceCitation) -> bool:
        """Check whether one citation appears in the factual payload.

        Args:
            citation: Validated evidence proposed by Gemini.

        Returns:
            True when the citation exactly matches supplied facts; otherwise,
            False.
        """
        if citation.field == "summary":
            return (
                self.summary is not None
                and citation.value in self.summary
            )

        source_values = {
            "genre": self.genres,
            "theme": self.themes,
            "keyword": self.keywords,
            "game_mode": self.game_modes,
            "time_to_beat": self.time_to_beat,
            "release_information": self.release_information,
        }

        return citation.value in source_values[citation.field]


def calculate_facts_fingerprint(facts: GameTraitFacts) -> str:
    """Calculate a deterministic fingerprint for factual Gemini input.

    Args:
        facts: Canonical game facts that will be supplied to Gemini.

    Returns:
        A lowercase SHA-256 hexadecimal digest of the canonical JSON payload.
    """
    canonical_json = dumps(
        facts.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    return sha256(canonical_json.encode("utf-8")).hexdigest()


class DerivedNumericTrait(BaseModel):
    """Represent one nullable numeric Ludex trait interpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: TraitScore | None
    confidence: Confidence
    evidence: tuple[EvidenceCitation, ...] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_known_or_unknown_state(self) -> Self:
        """Validate the relationship between value, confidence, and evidence.

        Returns:
            The completely validated trait.

        Raises:
            ValueError: If an unknown trait contains confidence or evidence,
                or a known trait lacks sufficient confidence or evidence.
        """
        if self.value is None:
            if self.confidence != Decimal("0") or self.evidence:
                raise ValueError(
                    "Unknown traits require zero confidence and no evidence."
                )

            return self

        if self.confidence < MIN_KNOWN_CONFIDENCE:
            raise ValueError(
                "Known traits require confidence of at least 0.30."
            )

        if not self.evidence:
            raise ValueError("Known traits require supporting evidence.")

        return self


class DerivedMood(BaseModel):
    """Represent one supported allowlisted mood interpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: MoodLabel
    confidence: KnownConfidence
    evidence: tuple[EvidenceCitation, ...] = Field(
        min_length=1,
        max_length=3,
    )


class GameTraitResponse(BaseModel):
    """Represent one complete validated Gemini game-trait response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    story_focus: DerivedNumericTrait
    combat_intensity: DerivedNumericTrait
    difficulty: DerivedNumericTrait
    pacing: DerivedNumericTrait
    session_friendliness: DerivedNumericTrait
    exploration_focus: DerivedNumericTrait
    moods: tuple[DerivedMood, ...]

    @model_validator(mode="after")
    def validate_unique_moods(self) -> Self:
        """Ensure every mood label occurs at most once.

        Returns:
            The response when all mood labels are unique.

        Raises:
            ValueError: If Gemini returned a duplicate mood label.
        """
        labels = [mood.label for mood in self.moods]

        if len(labels) != len(set(labels)):
            raise ValueError("Mood labels must be unique.")

        return self


def validate_response_evidence(
    response: GameTraitResponse,
    facts: GameTraitFacts,
) -> GameTraitResponse:
    """Verify every derived citation against trusted factual input.

    Args:
        response: Structurally valid Gemini trait response.
        facts: Exact factual payload supplied to Gemini.

    Returns:
        The original response after all citations have been verified.

    Raises:
        TraitEvidenceError: If any trait or mood citation is absent from the
            supplied facts.
    """
    for trait_field in NUMERIC_TRAIT_FIELDS:
        trait = getattr(response, trait_field)

        for citation in trait.evidence:
            if not facts.supports_evidence(citation):
                raise TraitEvidenceError(
                    "Trait evidence was absent from the supplied facts."
                )

    for mood in response.moods:
        for citation in mood.evidence:
            if not facts.supports_evidence(citation):
                raise TraitEvidenceError(
                    "Mood evidence was absent from the supplied facts."
                )

    return response
