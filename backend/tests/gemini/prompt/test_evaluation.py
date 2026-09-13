from json import dumps, loads

from app.gemini.client import (
    GeminiRateLimitError,
    GeminiStructuredContent,
)
from app.gemini.prompt.contracts import (
    PROMPT_INTERPRETATION_VERSION,
    PromptConceptPreference,
    PromptInterpretation,
)
from app.gemini.prompt.evaluation import (
    PROMPT_EVALUATION_MAX_CALLS,
    PromptEvaluationReport,
    build_prompt_evaluation_cases,
    build_prompt_evaluation_vocabulary,
    run_prompt_evaluation,
)
from app.gemini.prompt.validation import validate_prompt_interpretation


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0

    def clock(self) -> float:
        self.value += 0.01
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_fixture_has_fifteen_cases_and_three_fixed_repeats() -> None:
    cases = build_prompt_evaluation_cases()

    assert len(cases) == 18
    assert [case.repeat_of for case in cases[-3:]] == ["p01", "p06", "p13"]
    assert PROMPT_EVALUATION_MAX_CALLS == 20
    assert len(build_prompt_evaluation_vocabulary().entries) <= 256


def test_perfect_fixed_outputs_pass_every_quality_gate(monkeypatch) -> None:
    cases = build_prompt_evaluation_cases()
    vocabulary = build_prompt_evaluation_vocabulary()
    calls = iter(cases)

    def interpret(client, *, model_id, prompt, vocabulary):
        case = next(calls)
        preferences = tuple(
            PromptConceptPreference(
                concept_id=expected.concept_id,
                direction=expected.direction,
                importance=2,
                target=expected.minimum_target,
            )
            for expected in case.required
        )
        unmatched_phrases: tuple[str, ...] = ()
        if case.requires_unmatched:
            unmatched_phrases = ("ambiguous",)
        elif case.case_id == "p01":
            unmatched_phrases = ("cozy",)

        interpretation = PromptInterpretation(
            version=PROMPT_INTERPRETATION_VERSION,
            preferences=preferences,
            constraints=case.constraints,
            unmatched_phrases=unmatched_phrases,
        )
        return (
            validate_prompt_interpretation(interpretation, vocabulary),
            GeminiStructuredContent(
                content=interpretation.model_dump(mode="json"),
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
            ),
        )

    monkeypatch.setattr(
        "app.gemini.prompt.evaluation.interpret_prompt_with_metadata",
        interpret,
    )
    fake_time = FakeTime()
    report = run_prompt_evaluation(
        object(),
        model_id="test-model",
        requests_per_minute=15,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )

    assert report.call_count == 18
    assert report.capture_basis_points == 10_000
    assert report.unsupported_basis_points == 0
    assert report.valid_output_basis_points == 10_000
    assert report.hard_constraints_pass is True
    assert report.ambiguous_unmatched_pass is True
    assert report.repeats_pass is True
    assert report.overall_pass is True


def test_rate_limit_stops_without_spending_remaining_calls(monkeypatch) -> None:
    def rate_limited(*args, **kwargs):
        raise GeminiRateLimitError("limited", retry_after_seconds=60)

    monkeypatch.setattr(
        "app.gemini.prompt.evaluation.interpret_prompt_with_metadata",
        rate_limited,
    )
    fake_time = FakeTime()
    report = run_prompt_evaluation(
        object(),
        model_id="test-model",
        requests_per_minute=4,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )

    assert report.call_count == 1
    assert report.stopped_early is True
    assert report.results[0].error_code == "rate_limited"
    assert report.overall_pass is False


def test_stopped_report_resumes_after_existing_case_prefix(monkeypatch) -> None:
    cases = build_prompt_evaluation_cases()
    first_run_calls = iter(cases)

    def stop_after_eight(client, *, model_id, prompt, vocabulary):
        case = next(first_run_calls)
        if case.case_id == "p08":
            raise GeminiRateLimitError("limited")
        interpretation = PromptInterpretation(
            version=PROMPT_INTERPRETATION_VERSION,
            preferences=tuple(
                PromptConceptPreference(
                    concept_id=expected.concept_id,
                    direction=expected.direction,
                    importance=2,
                    target=expected.minimum_target,
                )
                for expected in case.required
            ),
            constraints=case.constraints,
            unmatched_phrases=(),
        )
        return (
            validate_prompt_interpretation(interpretation, vocabulary),
            GeminiStructuredContent(
                content=interpretation.model_dump(mode="json"),
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
            ),
        )

    monkeypatch.setattr(
        "app.gemini.prompt.evaluation.interpret_prompt_with_metadata",
        stop_after_eight,
    )
    fake_time = FakeTime()
    stopped = run_prompt_evaluation(
        object(),
        model_id="test-model",
        requests_per_minute=15,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )
    restored = PromptEvaluationReport.from_dict(
        loads(dumps(stopped.to_dict()))
    )
    remaining_calls = iter(cases[8:])

    def complete_remaining(client, *, model_id, prompt, vocabulary):
        case = next(remaining_calls)
        interpretation = PromptInterpretation(
            version=PROMPT_INTERPRETATION_VERSION,
            preferences=tuple(
                PromptConceptPreference(
                    concept_id=expected.concept_id,
                    direction=expected.direction,
                    importance=2,
                    target=expected.minimum_target,
                )
                for expected in case.required
            ),
            constraints=case.constraints,
            unmatched_phrases=("ambiguous",) if case.requires_unmatched else (),
        )
        return (
            validate_prompt_interpretation(interpretation, vocabulary),
            GeminiStructuredContent(
                content=interpretation.model_dump(mode="json"),
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
            ),
        )

    monkeypatch.setattr(
        "app.gemini.prompt.evaluation.interpret_prompt_with_metadata",
        complete_remaining,
    )
    resumed = run_prompt_evaluation(
        object(),
        model_id="test-model",
        requests_per_minute=15,
        prior_report=restored,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )

    assert stopped.call_count == 8
    assert resumed.call_count == 18
    assert len(resumed.results) == 18
    assert [result.case_id for result in resumed.results] == [
        case.case_id for case in cases
    ]
    assert resumed.stopped_early is False
    assert resumed.overall_pass is False
