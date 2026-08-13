from typing import Any

import pytest
from pydantic import ValidationError
from decimal import Decimal

from app.game_traits import (
    GameTraitFacts,
    GameTraitResponse,
    TraitEvidenceError,
    validate_response_evidence,
    calculate_facts_fingerprint,
)


def _evidence() -> dict[str, str]:
    """Return one valid factual evidence item."""
    return {
        "field": "summary",
        "value": "A story-driven adventure.",
        "reason": "Directly supports the derived value.",
    }


def _known_trait(value: int = 3) -> dict[str, Any]:
    """Return one valid known numeric trait."""
    return {
        "value": value,
        "confidence": 0.75,
        "evidence": [_evidence()],
    }


def _valid_response() -> dict[str, Any]:
    """Return one complete valid Gemini trait response."""
    return {
        "story_focus": _known_trait(4),
        "combat_intensity": _known_trait(2),
        "difficulty": {
            "value": None,
            "confidence": 0,
            "evidence": [],
        },
        "pacing": _known_trait(3),
        "session_friendliness": {
            "value": None,
            "confidence": 0,
            "evidence": [],
        },
        "exploration_focus": _known_trait(5),
        "moods": [
            {
                "label": "emotional",
                "confidence": 0.80,
                "evidence": [_evidence()],
            }
        ],
    }


def test_accepts_complete_trait_response() -> None:
    response = GameTraitResponse.model_validate(_valid_response())

    assert response.story_focus.value == 4
    assert response.difficulty.value is None
    assert response.moods[0].label == "emotional"


@pytest.mark.parametrize("missing_field", [
    "story_focus",
    "combat_intensity",
    "difficulty",
    "pacing",
    "session_friendliness",
    "exploration_focus",
    "moods",
])
def test_requires_every_response_field(missing_field: str) -> None:
    response = _valid_response()
    del response[missing_field]

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def test_rejects_extra_response_fields() -> None:
    response = _valid_response()
    response["unsupported_trait"] = _known_trait()

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


@pytest.mark.parametrize("invalid_value", [-1, 6, 2.5, True])
def test_rejects_invalid_trait_values(invalid_value: object) -> None:
    response = _valid_response()
    response["story_focus"]["value"] = invalid_value

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 0.301])
def test_rejects_invalid_confidence(confidence: float) -> None:
    response = _valid_response()
    response["story_focus"]["confidence"] = confidence

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def test_unknown_trait_requires_zero_confidence() -> None:
    response = _valid_response()
    response["difficulty"]["confidence"] = 0.30

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def test_unknown_trait_requires_empty_evidence() -> None:
    response = _valid_response()
    response["difficulty"]["evidence"] = [_evidence()]

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


@pytest.mark.parametrize("confidence", [0, 0.29])
def test_known_trait_requires_minimum_confidence(confidence: float) -> None:
    response = _valid_response()
    response["story_focus"]["confidence"] = confidence

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def test_known_trait_requires_evidence() -> None:
    response = _valid_response()
    response["story_focus"]["evidence"] = []

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def test_accepts_empty_mood_list() -> None:
    response = _valid_response()
    response["moods"] = []

    result = GameTraitResponse.model_validate(response)

    assert result.moods == ()


def test_accepts_minimum_known_confidence() -> None:
    response = _valid_response()
    response["story_focus"]["confidence"] = 0.30

    result = GameTraitResponse.model_validate(response)

    assert result.story_focus.confidence == Decimal("0.30")


def test_rejects_more_than_three_trait_evidence_items() -> None:
    response = _valid_response()
    response["story_focus"]["evidence"] = [_evidence()] * 4

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def test_rejects_more_than_three_mood_evidence_items() -> None:
    response = _valid_response()
    response["moods"][0]["evidence"] = [_evidence()] * 4

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


@pytest.mark.parametrize(
    "unsupported_field",
    ["cover", "steam_playtime", "developer"],
)
def test_rejects_unsupported_evidence_fields(
    unsupported_field: str,
) -> None:
    response = _valid_response()
    response["story_focus"]["evidence"][0]["field"] = unsupported_field

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


@pytest.mark.parametrize(
    ("field_name", "invalid_text"),
    [
        ("value", ""),
        ("value", " padded"),
        ("reason", ""),
        ("reason", "Two lines.\nSecond line."),
        ("reason", "x" * 201),
    ],
)
def test_rejects_invalid_evidence_text(
    field_name: str,
    invalid_text: str,
) -> None:
    response = _valid_response()
    response["story_focus"]["evidence"][0][field_name] = invalid_text

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


@pytest.mark.parametrize(
    "invalid_reason",
    [
        "This reason has no terminal punctuation",
        "This is one sentence. This is another sentence.",
    ],
)
def test_requires_one_sentence_evidence_reason(
    invalid_reason: str,
) -> None:
    response = _valid_response()
    response["story_focus"]["evidence"][0]["reason"] = invalid_reason

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


@pytest.mark.parametrize(
    "absence_reason",
    [
        "The summary has no mention of combat.",
        "Combat is not mentioned in the summary.",
        "The supplied facts do not mention combat.",
        "Combat information is absent from the metadata.",
        "The summary describes puzzles without any mention of combat.",
        "The summary contains no reference to combat.",
        "The supplied metadata lacks any mention of combat.",
    ],
)
def test_rejects_absence_based_evidence_reason(
    absence_reason: str,
) -> None:
    """Reject interpretations that treat missing facts as evidence."""
    response = _valid_response()
    response["combat_intensity"] = {
        "value": 0,
        "confidence": 0.80,
        "evidence": [
            {
                "field": "summary",
                "value": "A story-driven adventure.",
                "reason": absence_reason,
            }
        ],
    }

    with pytest.raises(
        ValidationError,
        match="Absence of information cannot support evidence",
    ):
        GameTraitResponse.model_validate(response)


@pytest.mark.parametrize(
    "invalid_label",
    ["cozy", "scary", "RELAXING"],
)
def test_rejects_non_allowlisted_moods(invalid_label: str) -> None:
    response = _valid_response()
    response["moods"][0]["label"] = invalid_label

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


@pytest.mark.parametrize("confidence", [0, 0.29])
def test_returned_mood_requires_minimum_confidence(
    confidence: float,
) -> None:
    response = _valid_response()
    response["moods"][0]["confidence"] = confidence

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def test_returned_mood_requires_evidence() -> None:
    response = _valid_response()
    response["moods"][0]["evidence"] = []

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def test_rejects_duplicate_mood_labels() -> None:
    response = _valid_response()
    response["moods"].append(
        {
            "label": "emotional",
            "confidence": 0.70,
            "evidence": [_evidence()],
        }
    )

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def test_rejects_extra_nested_fields() -> None:
    response = _valid_response()
    response["story_focus"]["explanation"] = "Unsupported field."

    with pytest.raises(ValidationError):
        GameTraitResponse.model_validate(response)


def _valid_facts() -> GameTraitFacts:
    """Return representative factual metadata supplied to Gemini."""
    return GameTraitFacts(
        name="Example Game",
        summary=(
            "A story-driven adventure. "
            "Travel through a dangerous wilderness."
        ),
        genres=("Adventure",),
        themes=("Survival",),
        keywords=("Story Rich",),
        game_modes=("Single player",),
        time_to_beat=("normally: 36000 seconds",),
        release_information=("first release: 2020-01-01",),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("summary", "story-driven adventure"),
        ("genre", "Adventure"),
        ("theme", "Survival"),
        ("keyword", "Story Rich"),
        ("game_mode", "Single player"),
        ("time_to_beat", "normally: 36000 seconds"),
        ("release_information", "first release: 2020-01-01"),
    ],
)
def test_accepts_evidence_present_in_supplied_facts(
    field: str,
    value: str,
) -> None:
    response_data = _valid_response()
    response_data["story_focus"]["evidence"][0] = {
        "field": field,
        "value": value,
        "reason": "Directly supports the derived value.",
    }
    response = GameTraitResponse.model_validate(response_data)

    result = validate_response_evidence(response, _valid_facts())

    assert result is response


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("summary", "A paraphrased description."),
        ("genre", "Role-playing"),
        ("theme", "Fantasy"),
        ("keyword", "Difficult"),
        ("game_mode", "Multiplayer"),
        ("time_to_beat", "normally: 72000 seconds"),
        ("release_information", "first release: 2021-01-01"),
    ],
)
def test_rejects_evidence_absent_from_supplied_facts(
    field: str,
    value: str,
) -> None:
    response_data = _valid_response()
    response_data["story_focus"]["evidence"][0] = {
        "field": field,
        "value": value,
        "reason": "Claims unsupported factual evidence.",
    }
    response = GameTraitResponse.model_validate(response_data)

    with pytest.raises(TraitEvidenceError):
        validate_response_evidence(response, _valid_facts())


def test_evidence_matching_is_case_sensitive() -> None:
    response_data = _valid_response()
    response_data["story_focus"]["evidence"][0] = {
        "field": "genre",
        "value": "adventure",
        "reason": "Uses different capitalization from the source.",
    }
    response = GameTraitResponse.model_validate(response_data)

    with pytest.raises(TraitEvidenceError):
        validate_response_evidence(response, _valid_facts())


def test_rejects_evidence_when_source_field_is_empty() -> None:
    response_data = _valid_response()
    response_data["story_focus"]["evidence"][0] = {
        "field": "summary",
        "value": "story-driven adventure",
        "reason": "References a summary that was not supplied.",
    }
    response = GameTraitResponse.model_validate(response_data)
    facts = _valid_facts().model_copy(update={"summary": None})

    with pytest.raises(TraitEvidenceError):
        validate_response_evidence(response, facts)


def test_validates_every_trait_evidence_item() -> None:
    response_data = _valid_response()
    response_data["story_focus"]["evidence"].append(
        {
            "field": "genre",
            "value": "Unsupported Genre",
            "reason": "The second citation is unsupported.",
        }
    )
    response = GameTraitResponse.model_validate(response_data)

    with pytest.raises(TraitEvidenceError):
        validate_response_evidence(response, _valid_facts())


def test_validates_mood_evidence() -> None:
    response_data = _valid_response()
    response_data["moods"][0]["evidence"][0] = {
        "field": "theme",
        "value": "Unsupported Theme",
        "reason": "The mood citation is unsupported.",
    }
    response = GameTraitResponse.model_validate(response_data)

    with pytest.raises(TraitEvidenceError):
        validate_response_evidence(response, _valid_facts())


def test_combat_zero_requires_explicit_noncombat_fact() -> None:
    """Reject a zero combat score inferred only from unrelated facts."""
    response_data = _valid_response()
    response_data["combat_intensity"] = {
        "value": 0,
        "confidence": 0.80,
        "evidence": [
            {
                "field": "summary",
                "value": "A story-driven adventure.",
                "reason": "Puzzles are the sole described activity.",
            }
        ],
    }
    response = GameTraitResponse.model_validate(response_data)

    with pytest.raises(
        TraitEvidenceError,
        match="Combat intensity zero requires explicit non-combat evidence",
    ):
        validate_response_evidence(response, _valid_facts())


@pytest.mark.parametrize(
    "explicit_description",
    [
        "A non-combat puzzle adventure.",
        "A combat-free puzzle adventure.",
        "An adventure with no combat.",
        "An adventure without combat.",
        "The game does not feature combat.",
    ],
)
def test_combat_zero_accepts_explicit_noncombat_fact(
    explicit_description: str,
) -> None:
    """Accept zero combat only when supplied facts explicitly support it."""
    response_data = _valid_response()
    response_data["combat_intensity"] = {
        "value": 0,
        "confidence": 0.80,
        "evidence": [
            {
                "field": "summary",
                "value": explicit_description,
                "reason": "The supplied description explicitly rules out combat.",
            }
        ],
    }
    response = GameTraitResponse.model_validate(response_data)
    original_facts = _valid_facts()
    facts = original_facts.model_copy(
        update={
            "summary": (
                f"{original_facts.summary} {explicit_description}"
            )
        }
    )

    result = validate_response_evidence(response, facts)

    assert result is response


def test_normalizes_canonical_game_trait_facts() -> None:
    facts = GameTraitFacts(
        name="  Example Game  ",
        summary="  A factual summary.  ",
        genres=("Role-playing", "Adventure", "Adventure"),
        themes=("Fantasy",),
        keywords=(),
        game_modes=("Single player",),
        time_to_beat=(),
        release_information=(),
    )

    assert facts.name == "Example Game"
    assert facts.summary == "A factual summary."
    assert facts.genres == ("Adventure", "Role-playing")


def test_normalizes_blank_summary_to_unknown() -> None:
    facts = _valid_facts().model_copy(
        update={"summary": "   "}
    )

    normalized = GameTraitFacts.model_validate(facts.model_dump())

    assert normalized.summary is None


def test_fact_fingerprint_is_stable_across_collection_order() -> None:
    first = GameTraitFacts(
        name="Example Game",
        summary="A factual summary.",
        genres=("Adventure", "Role-playing"),
        themes=("Fantasy", "Survival"),
        keywords=(),
        game_modes=("Single player",),
        time_to_beat=(),
        release_information=(),
    )
    second = GameTraitFacts(
        name="Example Game",
        summary="A factual summary.",
        genres=("Role-playing", "Adventure", "Adventure"),
        themes=("Survival", "Fantasy"),
        keywords=(),
        game_modes=("Single player",),
        time_to_beat=(),
        release_information=(),
    )

    assert (
        calculate_facts_fingerprint(first)
        == calculate_facts_fingerprint(second)
    )


def test_fact_fingerprint_changes_with_relevant_facts() -> None:
    original = _valid_facts()
    changed = GameTraitFacts.model_validate(
        {
            **original.model_dump(),
            "themes": ("Exploration",),
        }
    )

    assert (
        calculate_facts_fingerprint(original)
        != calculate_facts_fingerprint(changed)
    )


def test_fact_fingerprint_is_lowercase_sha256() -> None:
    fingerprint = calculate_facts_fingerprint(_valid_facts())

    assert len(fingerprint) == 64
    assert set(fingerprint) <= set("0123456789abcdef")
