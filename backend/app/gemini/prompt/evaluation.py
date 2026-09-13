from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import monotonic, sleep
from typing import Any, Callable

from app.gemini.client import (
    GeminiAPIError,
    GeminiClient,
    GeminiRateLimitError,
    GeminiUnavailableError,
)
from app.gemini.prompt.contracts import (
    PromptConceptKind,
    PromptConstraints,
    PromptText,
    PromptVocabulary,
    PromptVocabularyEntry,
)
from app.gemini.prompt.interpreter import (
    PromptInterpretationError,
    interpret_prompt_with_metadata,
)
from app.gemini.prompt.validation import ValidatedPromptInterpretation
from app.recommendations.contracts import PlayStatus


PROMPT_EVALUATION_VERSION = "prompt-evaluation-v1"
PROMPT_EVALUATION_MAX_CALLS = 20


@dataclass(frozen=True)
class ExpectedPreference:
    concept_id: str
    direction: str = "desired"
    minimum_target: int | None = None
    maximum_target: int | None = None


@dataclass(frozen=True)
class PromptEvaluationCase:
    case_id: str
    prompt: str
    required: tuple[ExpectedPreference, ...]
    allowed: tuple[ExpectedPreference, ...]
    constraints: PromptConstraints
    requires_unmatched: bool = False
    repeat_of: str | None = None


@dataclass(frozen=True)
class PromptEvaluationCaseResult:
    case_id: str
    status: str
    attempts: int
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    preferences: tuple[tuple[str, str, int | None], ...]
    maximum_completion_minutes: int | None
    play_status: str | None
    unmatched_count: int
    captured_required: int
    required_count: int
    unsupported_count: int
    constraint_match: bool
    unmatched_match: bool
    error_code: str | None


@dataclass(frozen=True)
class PromptEvaluationReport:
    evaluation_version: str
    model_id: str
    started_at: str
    completed_at: str
    call_count: int
    stopped_early: bool
    capture_basis_points: int
    unsupported_basis_points: int
    valid_output_basis_points: int
    hard_constraints_pass: bool
    ambiguous_unmatched_pass: bool
    repeats_pass: bool
    overall_pass: bool
    results: tuple[PromptEvaluationCaseResult, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PromptEvaluationReport":
        """Restore a report written by this evaluator for a bounded resume."""
        try:
            raw_results = value["results"]
            if not isinstance(raw_results, list):
                raise TypeError
            results = tuple(
                PromptEvaluationCaseResult(
                    **{
                        **result,
                        "preferences": tuple(
                            tuple(preference)
                            for preference in result["preferences"]
                        ),
                    }
                )
                for result in raw_results
            )
            return cls(
                **{
                    **value,
                    "results": results,
                }
            )
        except (KeyError, TypeError, ValueError):
            raise ValueError("Prompt evaluation report is invalid.") from None


def build_prompt_evaluation_vocabulary() -> PromptVocabulary:
    """Return the fixed, synthetic Phase D vocabulary."""
    factual = (
        ("genre:9", PromptConceptKind.GENRE, "Puzzle", 9),
        ("genre:12", PromptConceptKind.GENRE, "Role-playing (RPG)", 12),
        ("genre:15", PromptConceptKind.GENRE, "Strategy", 15),
        ("genre:31", PromptConceptKind.GENRE, "Adventure", 31),
        ("theme:17", PromptConceptKind.THEME, "Fantasy", 17),
        ("theme:18", PromptConceptKind.THEME, "Science fiction", 18),
        ("theme:19", PromptConceptKind.THEME, "Horror", 19),
        ("game_mode:1", PromptConceptKind.GAME_MODE, "Single player", 1),
        ("game_mode:2", PromptConceptKind.GAME_MODE, "Multiplayer", 2),
        ("game_mode:3", PromptConceptKind.GAME_MODE, "Co-operative", 3),
        ("keyword:101", PromptConceptKind.KEYWORD, "Farming", 101),
        ("keyword:102", PromptConceptKind.KEYWORD, "Space", 102),
        ("keyword:103", PromptConceptKind.KEYWORD, "Exploration", 103),
        ("keyword:104", PromptConceptKind.KEYWORD, "Detective", 104),
        ("keyword:105", PromptConceptKind.KEYWORD, "Mystery", 105),
        ("keyword:106", PromptConceptKind.KEYWORD, "Crafting", 106),
        ("keyword:107", PromptConceptKind.KEYWORD, "Open world", 107),
        ("keyword:108", PromptConceptKind.KEYWORD, "Turn-based", 108),
    )
    entries = [
        PromptVocabularyEntry(
            concept_id=concept_id,
            kind=kind,
            label=label,
            igdb_id=igdb_id,
        )
        for concept_id, kind, label, igdb_id in factual
    ]
    for name, label in (
        ("story_focus", "Story focused"),
        ("combat_intensity", "Combat intensity"),
        ("difficulty", "Difficulty"),
        ("pacing", "Pacing"),
        ("session_friendliness", "Short-session friendly"),
        ("exploration_focus", "Exploration focused"),
    ):
        entries.append(
            PromptVocabularyEntry(
                concept_id=f"trait:{name}",
                kind=PromptConceptKind.NUMERIC_TRAIT,
                label=label,
            )
        )
    for mood in ("relaxing", "tense", "emotional", "humorous", "dark"):
        entries.append(
            PromptVocabularyEntry(
                concept_id=f"mood:{mood}",
                kind=PromptConceptKind.MOOD,
                label=mood.title(),
            )
        )
    return PromptVocabulary(
        version=PROMPT_EVALUATION_VERSION,
        entries=tuple(entries),
    )


def _constraints(
    maximum: int | None = None,
    status: PlayStatus = PlayStatus.EITHER,
) -> PromptConstraints:
    return PromptConstraints(
        maximum_completion_minutes=maximum,
        play_status=status,
    )


def build_prompt_evaluation_cases() -> tuple[PromptEvaluationCase, ...]:
    """Return 15 primary cases and three preselected repeats."""
    desired = ExpectedPreference
    cases = (
        PromptEvaluationCase(
            "p01",
            "I want a cozy, relaxing game where I can farm.",
            (desired("mood:relaxing"), desired("keyword:101")),
            (desired("mood:relaxing"), desired("keyword:101")),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p02",
            "Give me something tense and frightening, like horror.",
            (desired("mood:tense"), desired("theme:19")),
            (desired("mood:tense"), desired("theme:19")),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p03",
            "I want an easy game that works in sessions under 15 minutes.",
            (
                desired("trait:difficulty", minimum_target=0, maximum_target=2),
                desired(
                    "trait:session_friendliness",
                    minimum_target=5,
                    maximum_target=5,
                ),
            ),
            (
                desired("trait:difficulty", minimum_target=0, maximum_target=2),
                desired(
                    "trait:session_friendliness",
                    minimum_target=5,
                    maximum_target=5,
                ),
            ),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p04",
            "A story-focused, emotional RPG sounds perfect.",
            (
                desired("trait:story_focus", minimum_target=4, maximum_target=5),
                desired("mood:emotional"),
                desired("genre:12"),
            ),
            (
                desired("trait:story_focus", minimum_target=4, maximum_target=5),
                desired("mood:emotional"),
                desired("genre:12"),
            ),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p05",
            "Fast-paced combat is great, but I do not want anything dark.",
            (
                desired("trait:pacing", minimum_target=4, maximum_target=5),
                desired(
                    "trait:combat_intensity",
                    minimum_target=4,
                    maximum_target=5,
                ),
                desired("mood:dark", direction="avoided"),
            ),
            (
                desired("trait:pacing", minimum_target=4, maximum_target=5),
                desired(
                    "trait:combat_intensity",
                    minimum_target=4,
                    maximum_target=5,
                ),
                desired("mood:dark", direction="avoided"),
            ),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p06",
            "Find an unplayed single-player game I can finish in at most 10 hours.",
            (desired("game_mode:1"),),
            (desired("game_mode:1"),),
            _constraints(600, PlayStatus.UNPLAYED),
        ),
        PromptEvaluationCase(
            "p07",
            "Show me a puzzle game I have previously played.",
            (desired("genre:9"),),
            (desired("genre:9"),),
            _constraints(status=PlayStatus.PREVIOUSLY_PLAYED),
        ),
        PromptEvaluationCase(
            "p08",
            "I want space exploration, but avoid multiplayer games.",
            (
                desired("keyword:102"),
                desired("keyword:103"),
                desired("game_mode:2", direction="avoided"),
            ),
            (
                desired("keyword:102"),
                desired("keyword:103"),
                desired("game_mode:2", direction="avoided"),
                desired(
                    "trait:exploration_focus",
                    minimum_target=4,
                    maximum_target=5,
                ),
                desired("theme:18"),
            ),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p09",
            "Something funny involving a detective and a mystery.",
            (
                desired("mood:humorous"),
                desired("keyword:104"),
                desired("keyword:105"),
            ),
            (
                desired("mood:humorous"),
                desired("keyword:104"),
                desired("keyword:105"),
            ),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p10",
            "I feel like a slow, deliberate game with very little combat.",
            (
                desired("trait:pacing", minimum_target=0, maximum_target=2),
                desired(
                    "trait:combat_intensity",
                    minimum_target=0,
                    maximum_target=2,
                ),
            ),
            (
                desired("trait:pacing", minimum_target=0, maximum_target=2),
                desired(
                    "trait:combat_intensity",
                    minimum_target=0,
                    maximum_target=2,
                ),
            ),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p11",
            "I want a co-op game with crafting.",
            (desired("game_mode:3"), desired("keyword:106")),
            (desired("game_mode:3"), desired("keyword:106")),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p12",
            "An open-world fantasy game, but not horror.",
            (
                desired("keyword:107"),
                desired("theme:17"),
                desired("theme:19", direction="avoided"),
            ),
            (
                desired("keyword:107"),
                desired("theme:17"),
                desired("theme:19", direction="avoided"),
                desired(
                    "trait:exploration_focus",
                    minimum_target=3,
                    maximum_target=5,
                ),
            ),
            _constraints(),
        ),
        PromptEvaluationCase(
            "p13",
            "Surprise me.",
            (),
            (),
            _constraints(),
            requires_unmatched=True,
        ),
        PromptEvaluationCase(
            "p14",
            "I want something good.",
            (),
            (),
            _constraints(),
            requires_unmatched=True,
        ),
        PromptEvaluationCase(
            "p15",
            "A turn-based strategy game I can finish within 30 hours.",
            (desired("keyword:108"), desired("genre:15")),
            (desired("keyword:108"), desired("genre:15")),
            _constraints(1800),
        ),
    )
    repeats = tuple(
        PromptEvaluationCase(
            case_id=f"{case.case_id}r",
            prompt=case.prompt,
            required=case.required,
            allowed=case.allowed,
            constraints=case.constraints,
            requires_unmatched=case.requires_unmatched,
            repeat_of=case.case_id,
        )
        for case in (cases[0], cases[5], cases[12])
    )
    return cases + repeats


def _preference_matches(
    actual: tuple[str, str, int | None],
    expected: ExpectedPreference,
) -> bool:
    concept_id, direction, target = actual
    if concept_id != expected.concept_id or direction != expected.direction:
        return False
    if expected.minimum_target is None:
        return target is None
    return (
        target is not None
        and expected.minimum_target <= target <= expected.maximum_target
    )


def _evaluate_valid_result(
    case: PromptEvaluationCase,
    validated: ValidatedPromptInterpretation,
    *,
    attempts: int,
    latency_ms: int,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
) -> PromptEvaluationCaseResult:
    interpretation = validated.interpretation
    actual = tuple(
        (
            concept.preference.concept_id,
            concept.preference.direction.value,
            concept.preference.target,
        )
        for concept in validated.concepts
    )
    captured = sum(
        any(_preference_matches(item, expected) for item in actual)
        for expected in case.required
    )
    unsupported = sum(
        not any(_preference_matches(item, expected) for expected in case.allowed)
        for item in actual
    )
    constraint_match = interpretation.constraints == case.constraints
    unmatched_match = (
        bool(interpretation.unmatched_phrases)
        if case.requires_unmatched
        else True
    )
    return PromptEvaluationCaseResult(
        case_id=case.case_id,
        status="valid",
        attempts=attempts,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        preferences=actual,
        maximum_completion_minutes=(
            interpretation.constraints.maximum_completion_minutes
        ),
        play_status=interpretation.constraints.play_status.value,
        unmatched_count=len(interpretation.unmatched_phrases),
        captured_required=captured,
        required_count=len(case.required),
        unsupported_count=unsupported,
        constraint_match=constraint_match,
        unmatched_match=unmatched_match,
        error_code=None,
    )


def _failed_result(
    case: PromptEvaluationCase,
    *,
    status: str,
    attempts: int,
    latency_ms: int,
    error_code: str,
) -> PromptEvaluationCaseResult:
    return PromptEvaluationCaseResult(
        case_id=case.case_id,
        status=status,
        attempts=attempts,
        latency_ms=latency_ms,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        preferences=(),
        maximum_completion_minutes=None,
        play_status=None,
        unmatched_count=0,
        captured_required=0,
        required_count=len(case.required),
        unsupported_count=0,
        constraint_match=False,
        unmatched_match=False,
        error_code=error_code,
    )


def _materially_equivalent(
    first: PromptEvaluationCaseResult,
    second: PromptEvaluationCaseResult,
    *,
    requires_unmatched: bool,
) -> bool:
    if first.status != "valid" or second.status != "valid":
        return False
    if (
        first.maximum_completion_minutes != second.maximum_completion_minutes
        or first.play_status != second.play_status
    ):
        return False
    first_by_key = {(item[0], item[1]): item[2] for item in first.preferences}
    second_by_key = {(item[0], item[1]): item[2] for item in second.preferences}
    if set(first_by_key) != set(second_by_key):
        return False
    for key, first_target in first_by_key.items():
        second_target = second_by_key[key]
        if first_target is None or second_target is None:
            if first_target != second_target:
                return False
        elif abs(first_target - second_target) > 1:
            return False
    return (
        (first.unmatched_count > 0) == (second.unmatched_count > 0)
        if requires_unmatched
        else True
    )


def run_prompt_evaluation(
    client: GeminiClient,
    *,
    model_id: str,
    requests_per_minute: int,
    prior_report: PromptEvaluationReport | None = None,
    clock: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
) -> PromptEvaluationReport:
    """Run the fixed evaluation within strict call and pacing ceilings."""
    if not 1 <= requests_per_minute <= 15:
        raise ValueError("Evaluation RPM must be between 1 and 15.")
    cases = build_prompt_evaluation_cases()
    vocabulary = build_prompt_evaluation_vocabulary()
    started_at = datetime.now(UTC).isoformat()
    call_count = 0
    transport_retry_used = False
    results: list[PromptEvaluationCaseResult] = []
    if prior_report is not None:
        expected_ids = [case.case_id for case in cases]
        actual_ids = [result.case_id for result in prior_report.results]
        if (
            prior_report.evaluation_version != PROMPT_EVALUATION_VERSION
            or prior_report.model_id != model_id
            or actual_ids != expected_ids[: len(actual_ids)]
            or prior_report.call_count < len(actual_ids)
            or prior_report.call_count >= PROMPT_EVALUATION_MAX_CALLS
        ):
            raise ValueError("Prompt evaluation report cannot be resumed.")
        started_at = prior_report.started_at
        call_count = prior_report.call_count
        results = list(prior_report.results)
        transport_retry_used = call_count > len(results)
    last_call_started: float | None = None
    stopped_early = False

    for case in cases[len(results) :]:
        attempts = 0
        case_started = clock()
        while True:
            if call_count >= PROMPT_EVALUATION_MAX_CALLS:
                stopped_early = True
                break
            if last_call_started is not None:
                delay = 60 / requests_per_minute - (clock() - last_call_started)
                if delay > 0:
                    sleeper(delay)
            last_call_started = clock()
            call_count += 1
            attempts += 1
            try:
                validated, metadata = interpret_prompt_with_metadata(
                    client,
                    model_id=model_id,
                    prompt=PromptText(text=case.prompt),
                    vocabulary=vocabulary,
                )
                results.append(
                    _evaluate_valid_result(
                        case,
                        validated,
                        attempts=attempts,
                        latency_ms=round((clock() - case_started) * 1000),
                        input_tokens=metadata.input_tokens,
                        output_tokens=metadata.output_tokens,
                        total_tokens=metadata.total_tokens,
                    )
                )
                break
            except GeminiUnavailableError:
                if not transport_retry_used:
                    transport_retry_used = True
                    continue
                results.append(
                    _failed_result(
                        case,
                        status="provider_error",
                        attempts=attempts,
                        latency_ms=round((clock() - case_started) * 1000),
                        error_code="unavailable",
                    )
                )
                stopped_early = True
                break
            except GeminiRateLimitError:
                results.append(
                    _failed_result(
                        case,
                        status="provider_error",
                        attempts=attempts,
                        latency_ms=round((clock() - case_started) * 1000),
                        error_code="rate_limited",
                    )
                )
                stopped_early = True
                break
            except GeminiAPIError:
                results.append(
                    _failed_result(
                        case,
                        status="provider_error",
                        attempts=attempts,
                        latency_ms=round((clock() - case_started) * 1000),
                        error_code="provider_rejected",
                    )
                )
                stopped_early = True
                break
            except PromptInterpretationError:
                results.append(
                    _failed_result(
                        case,
                        status="invalid",
                        attempts=attempts,
                        latency_ms=round((clock() - case_started) * 1000),
                        error_code="domain_validation",
                    )
                )
                break
        if stopped_early:
            break

    total_required = sum(result.required_count for result in results)
    total_captured = sum(result.captured_required for result in results)
    returned_count = sum(len(result.preferences) for result in results)
    unsupported_count = sum(result.unsupported_count for result in results)
    capture = (total_captured * 10_000 // total_required) if total_required else 0
    unsupported = (
        unsupported_count * 10_000 // returned_count if returned_count else 0
    )
    valid = sum(result.status == "valid" for result in results)
    valid_rate = valid * 10_000 // len(cases)
    by_id = {result.case_id: result for result in results}
    repeat_checks = [
        _materially_equivalent(
            by_id[case.repeat_of],
            by_id[case.case_id],
            requires_unmatched=case.requires_unmatched,
        )
        for case in cases
        if case.repeat_of is not None
        and case.case_id in by_id
        and case.repeat_of in by_id
    ]
    constraints_pass = (
        len(results) == len(cases)
        and all(result.constraint_match for result in results)
    )
    ambiguous_pass = all(
        by_id[case.case_id].unmatched_match
        for case in cases
        if case.requires_unmatched and case.case_id in by_id
    ) and len(results) == len(cases)
    repeats_pass = len(repeat_checks) == 3 and all(repeat_checks)
    overall = (
        not stopped_early
        and valid_rate == 10_000
        and constraints_pass
        and capture >= 9_000
        and unsupported <= 500
        and ambiguous_pass
        and repeats_pass
    )
    return PromptEvaluationReport(
        evaluation_version=PROMPT_EVALUATION_VERSION,
        model_id=model_id,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        call_count=call_count,
        stopped_early=stopped_early,
        capture_basis_points=capture,
        unsupported_basis_points=unsupported,
        valid_output_basis_points=valid_rate,
        hard_constraints_pass=constraints_pass,
        ambiguous_unmatched_pass=ambiguous_pass,
        repeats_pass=repeats_pass,
        overall_pass=overall,
        results=tuple(results),
    )
