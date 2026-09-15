import pytest
from pydantic import ValidationError

from app.gemini.client import GeminiRateLimitError, GeminiStructuredContent
from app.gemini.reranking.ceiling_evaluation import (
    CEILING_EVALUATION_CALLS_PER_SIZE,
    CEILING_EVALUATION_SIZES,
    RICH_CONTEXT_CANDIDATE_COUNT,
    RICH_CONTEXT_MAX_INPUT_TOKENS,
    RICH_CONTEXT_MAX_REQUEST_BYTES,
    CeilingRerankRequest,
    apply_reason_review,
    audit_ceiling_fixture_payloads,
    audit_rich_context_fixture_payloads,
    build_ceiling_evaluation_cases,
    build_rich_context_evaluation_cases,
    run_ceiling_evaluation,
    run_rich_context_evaluation,
)
from app.gemini.reranking.contracts import (
    MAX_RERANK_CANDIDATES,
    RerankRequest,
    RerankResponse,
)
from app.gemini.reranking.reranker import MAX_RERANK_REQUEST_BYTES


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0

    def clock(self) -> float:
        self.value += 0.01
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


@pytest.mark.parametrize("candidate_count", CEILING_EVALUATION_SIZES)
def test_fixture_has_exact_size_five_cases_and_strategic_matches(
    candidate_count: int,
) -> None:
    cases = build_ceiling_evaluation_cases(candidate_count)

    assert len(cases) == CEILING_EVALUATION_CALLS_PER_SIZE == 5
    assert {len(case.request.candidates) for case in cases} == {candidate_count}
    assert cases[-1].repeat_of == "c01"
    candidate_ids = [
        candidate.steam_app_id for candidate in cases[0].request.candidates
    ]
    high_fit_positions = sorted(
        candidate_ids.index(identity)
        for identity in cases[0].expected_high_fit_ids
    )
    assert high_fit_positions[0] < candidate_count // 4
    assert high_fit_positions[1] >= candidate_count // 3
    assert high_fit_positions[2] >= candidate_count * 3 // 4


def test_historical_ceiling_fixtures_fit_the_expanded_product_contract() -> None:
    product_size = build_ceiling_evaluation_cases(100)[0].request
    evaluation_only = build_ceiling_evaluation_cases(150)[0].request

    assert len(product_size.candidates) == 100
    assert len(evaluation_only.candidates) == 150
    assert MAX_RERANK_CANDIDATES == 200
    assert len(
        RerankRequest.model_validate(product_size.model_dump()).candidates
    ) == 100
    assert len(
        RerankRequest.model_validate(evaluation_only.model_dump()).candidates
    ) == 150
    with pytest.raises(ValidationError):
        RerankRequest.model_validate(
            {
                **evaluation_only.model_dump(),
                "candidates": tuple(evaluation_only.candidates)
                + tuple(evaluation_only.candidates[:51]),
            }
        )
    with pytest.raises(ValidationError):
        CeilingRerankRequest.model_validate(
            {
                **evaluation_only.model_dump(),
                "candidates": tuple(evaluation_only.candidates) * 2,
            }
        )


def test_zero_call_fixture_audit_stays_within_existing_payload_budget() -> None:
    sizes = audit_ceiling_fixture_payloads()

    assert tuple(sizes) == CEILING_EVALUATION_SIZES
    assert sizes[60] < sizes[100] < sizes[150]
    assert sizes[150] <= MAX_RERANK_REQUEST_BYTES


def test_rich_context_fixture_exercises_approved_100_game_payload() -> None:
    cases = build_rich_context_evaluation_cases()
    payloads = audit_rich_context_fixture_payloads()

    assert len(cases) == CEILING_EVALUATION_CALLS_PER_SIZE
    assert {
        len(case.request.candidates) for case in cases
    } == {RICH_CONTEXT_CANDIDATE_COUNT}
    assert min(payloads) > 60_000
    assert max(payloads) <= RICH_CONTEXT_MAX_REQUEST_BYTES
    assert all(
        len(candidate.summary or "") == 600
        for candidate in cases[0].request.candidates
    )


def test_perfect_outputs_pass_automated_gates_then_human_review(
    monkeypatch,
) -> None:
    cases = build_ceiling_evaluation_cases(100)
    pending = iter(cases)

    def rerank(client, *, model_id, request, max_request_bytes):
        case = next(pending)
        content = {
            "status": "ranked",
            "recommendations": [
                {
                    "steam_app_id": identity,
                    "summary": "A concise game-focused summary.",
                    "reasoning": "It closely fits the requested experience.",
                }
                for identity in case.expected_high_fit_ids
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
        "app.gemini.reranking.ceiling_evaluation.rerank_with_metadata",
        rerank,
    )
    fake_time = FakeTime()
    report = run_ceiling_evaluation(
        object(),
        candidate_count=100,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )

    assert report.call_count == 5
    assert report.automated_pass is True
    assert report.overall_pass is False
    assert apply_reason_review(report, passed=True).overall_pass is True


def test_rate_limit_stops_without_retrying(monkeypatch) -> None:
    def limited(*args, **kwargs):
        raise GeminiRateLimitError("limited", retry_after_seconds=60)

    monkeypatch.setattr(
        "app.gemini.reranking.ceiling_evaluation.rerank_with_metadata",
        limited,
    )
    fake_time = FakeTime()
    report = run_ceiling_evaluation(
        object(),
        candidate_count=60,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )

    assert report.call_count == 1
    assert report.stopped_early is True
    assert report.results[0].error_code == "rate_limited"


def test_rich_context_stops_after_first_input_token_failure(monkeypatch) -> None:
    calls = 0

    def oversized_tokens(client, *, model_id, request, max_request_bytes):
        nonlocal calls
        calls += 1
        content = {
            "status": "ranked",
            "recommendations": [
                {
                    "steam_app_id": request.candidates[2].steam_app_id,
                    "summary": "A concise game-focused summary.",
                    "reasoning": "It fits the requested experience.",
                }
            ],
            "no_match_reason": None,
        }
        return (
            RerankResponse.model_validate(content),
            GeminiStructuredContent(
                content=content,
                input_tokens=RICH_CONTEXT_MAX_INPUT_TOKENS + 1,
                output_tokens=20,
                total_tokens=RICH_CONTEXT_MAX_INPUT_TOKENS + 21,
            ),
        )

    monkeypatch.setattr(
        "app.gemini.reranking.ceiling_evaluation.rerank_with_metadata",
        oversized_tokens,
    )
    fake_time = FakeTime()
    report = run_rich_context_evaluation(
        object(),
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )

    assert calls == report.call_count == 1
    assert report.stopped_early is True
    assert report.input_token_pass is False
    assert report.results[0].error_code == "input_tokens_exceeded"


def test_oversized_payload_stops_before_constructing_a_provider_call(
    monkeypatch,
) -> None:
    called = False

    def rerank(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "app.gemini.reranking.ceiling_evaluation.rerank_with_metadata",
        rerank,
    )
    monkeypatch.setattr(
        "app.gemini.reranking.ceiling_evaluation.rerank_user_prompt_size_bytes",
        lambda request: MAX_RERANK_REQUEST_BYTES + 1,
    )
    report = run_ceiling_evaluation(object(), candidate_count=150)

    assert called is False
    assert report.call_count == 0
    assert report.stopped_early is True
    assert report.results[0].error_code == "payload_too_large"
