from app.gemini.client import GeminiRateLimitError, GeminiStructuredContent
from app.gemini.reranking.contracts import RerankResponse
from app.gemini.reranking.evaluation import (
    RERANK_EVALUATION_MAX_CALLS,
    apply_reason_review,
    build_rerank_evaluation_cases,
    run_rerank_evaluation,
)


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0

    def clock(self) -> float:
        self.value += 0.01
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_fixture_has_eight_primary_cases_two_repeats_and_max_thirty() -> None:
    cases = build_rerank_evaluation_cases()

    assert len(cases) == 10
    assert RERANK_EVALUATION_MAX_CALLS == 10
    assert [case.repeat_of for case in cases[-2:]] == ["r01", "r03"]
    assert {len(case.request.candidates) for case in cases} == {6, 15, 30}
    assert max(len(case.request.candidates) for case in cases) == 30
    assert {1055540, 1135690} <= set(cases[1].expected_high_fit_ids)


def test_perfect_outputs_pass_automated_gates_then_human_review(monkeypatch) -> None:
    cases = build_rerank_evaluation_cases()
    pending = iter(cases)

    def rerank(client, *, model_id, request):
        case = next(pending)
        if case.expected_no_match:
            content = {
                "status": "no_match",
                "recommendations": [],
                "no_match_reason": "None of these games plausibly fit.",
            }
        else:
            high_fit = tuple(case.expected_high_fit_ids)
            content = {
                "status": "ranked",
                "recommendations": [
                    {
                        "steam_app_id": steam_app_id,
                        "summary": "A concise game-focused summary.",
                        "reasoning": "It fits the requested experience.",
                    }
                    for steam_app_id in high_fit[:3]
                ],
                "no_match_reason": None,
            }
        return (
            RerankResponse.model_validate(content),
            GeminiStructuredContent(
                content=content,
                input_tokens=1000,
                output_tokens=100,
                total_tokens=1100,
            ),
        )

    monkeypatch.setattr(
        "app.gemini.reranking.evaluation.rerank_with_metadata",
        rerank,
    )
    fake_time = FakeTime()
    report = run_rerank_evaluation(
        object(),
        model_id="test-model",
        requests_per_minute=15,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )

    assert report.call_count == 10
    assert report.stopped_early is False
    assert report.validity_pass is True
    assert report.ranking_quality_pass is True
    assert report.special_cases_pass is True
    assert report.repeats_pass is True
    assert report.latency_pass is True
    assert report.payload_pass is True
    assert report.automated_pass is True
    assert report.human_reason_review_pass is None
    assert report.overall_pass is False

    reviewed = apply_reason_review(report, passed=True)
    assert reviewed.human_reason_review_pass is True
    assert reviewed.overall_pass is True


def test_rate_limit_stops_without_spending_remaining_calls(monkeypatch) -> None:
    def limited(*args, **kwargs):
        raise GeminiRateLimitError("limited", retry_after_seconds=60)

    monkeypatch.setattr(
        "app.gemini.reranking.evaluation.rerank_with_metadata",
        limited,
    )
    fake_time = FakeTime()
    report = run_rerank_evaluation(
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


def test_repeat_gate_requires_two_shared_top_three_ids(monkeypatch) -> None:
    cases = build_rerank_evaluation_cases()
    pending = iter(cases)

    def rerank(client, *, model_id, request):
        case = next(pending)
        if case.expected_no_match:
            content = {
                "status": "no_match",
                "recommendations": [],
                "no_match_reason": "No fit.",
            }
        else:
            ids = list(case.expected_high_fit_ids[:3])
            if case.repeat_of == "r03":
                ids = [ids[0]] + [
                    candidate.steam_app_id
                    for candidate in case.request.candidates
                    if candidate.steam_app_id not in ids
                ][:2]
            content = {
                "status": "ranked",
                "recommendations": [
                    {
                        "steam_app_id": value,
                        "summary": "A concise game-focused summary.",
                        "reasoning": "A possible fit for the visitor request.",
                    }
                    for value in ids
                ],
                "no_match_reason": None,
            }
        return (
            RerankResponse.model_validate(content),
            GeminiStructuredContent(
                content=content,
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
            ),
        )

    monkeypatch.setattr(
        "app.gemini.reranking.evaluation.rerank_with_metadata",
        rerank,
    )
    fake_time = FakeTime()
    report = run_rerank_evaluation(
        object(),
        model_id="test-model",
        requests_per_minute=15,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )

    assert report.repeats_pass is False
    assert report.automated_pass is False
