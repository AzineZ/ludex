"""Emit bounded, searchable diagnostics for the public Gemini reranker."""

import logging
from secrets import token_hex


_LOGGER = logging.getLogger("ludex.gemini")
_LOGGER.setLevel(logging.INFO)


def create_diagnostic_reference() -> str:
    """Create a short public reference that can be matched to one log entry."""
    return f"GEM-{token_hex(6).upper()}"


def _value(value: int | str | None) -> int | str:
    return "none" if value is None else value


def log_rerank_failure(
    *,
    reference: str,
    failure_category: str,
    model_id: str | None,
    candidate_count: int,
    request_bytes: int | None,
    duration_ms: int,
    provider_status: int | None = None,
    reason_code: str | None = None,
    retry_after_seconds: int | None = None,
) -> None:
    """Log only allowlisted operational fields, never request or response data."""
    fields = {
        "event": "gemini_rerank_failed",
        "reference": reference,
        "failure_category": failure_category,
        "model_id": model_id,
        "candidate_count": candidate_count,
        "request_bytes": request_bytes,
        "duration_ms": duration_ms,
        "provider_status": provider_status,
        "reason_code": reason_code,
        "retry_after_seconds": retry_after_seconds,
    }
    _LOGGER.error(
        "event=gemini_rerank_failed reference=%s failure_category=%s "
        "model_id=%s candidate_count=%s request_bytes=%s duration_ms=%s "
        "provider_status=%s reason_code=%s retry_after_seconds=%s",
        reference,
        failure_category,
        _value(model_id),
        candidate_count,
        _value(request_bytes),
        duration_ms,
        _value(provider_status),
        _value(reason_code),
        _value(retry_after_seconds),
        extra=fields,
    )


def log_rerank_success(
    *,
    model_id: str,
    candidate_count: int,
    request_bytes: int,
    duration_ms: int,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
) -> None:
    """Record bounded performance and token counts for a successful call."""
    fields = {
        "event": "gemini_rerank_succeeded",
        "model_id": model_id,
        "candidate_count": candidate_count,
        "request_bytes": request_bytes,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    _LOGGER.info(
        "event=gemini_rerank_succeeded model_id=%s candidate_count=%s "
        "request_bytes=%s duration_ms=%s input_tokens=%s output_tokens=%s "
        "total_tokens=%s",
        model_id,
        candidate_count,
        request_bytes,
        duration_ms,
        _value(input_tokens),
        _value(output_tokens),
        _value(total_tokens),
        extra=fields,
    )
