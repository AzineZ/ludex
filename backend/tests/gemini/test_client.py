from json import loads

import httpx
import pytest

from app.gemini.client import (
    GeminiAPIError,
    GeminiAuthenticationError,
    GeminiClient,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiUnavailableError,
)


MODEL_ID = "gemini-3.5-flash-lite"
GEMINI_HOST = "generativelanguage.googleapis.com"

TEST_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {
            "type": "string",
        }
    },
    "required": ["result"],
    "additionalProperties": False,
}


def test_generates_structured_content_with_exact_request() -> None:
    """Send the confirmed structured-output REST request."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.host == GEMINI_HOST
        assert request.url.path == (
            f"/v1beta/models/{MODEL_ID}:generateContent"
        )
        assert request.headers["x-goog-api-key"] == "test-api-key"
        assert request.headers["content-type"] == "application/json"

        assert loads(request.content) == {
            "systemInstruction": {
                "parts": [{"text": "System instruction"}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "User prompt"}],
                }
            ],
            "generationConfig": {
                "responseFormat": {
                    "text": {
                        "mimeType": "APPLICATION_JSON",
                        "schema": TEST_SCHEMA,
                    }
                }
            },
        }

        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "text": (
                                        '{"result":"classified"}'
                                    )
                                }
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with GeminiClient(
        "test-api-key",
        transport=transport,
    ) as client:
        result = client.generate_structured_content(
            model_id=MODEL_ID,
            system_instruction="System instruction",
            user_prompt="User prompt",
            response_schema=TEST_SCHEMA,
        )

    assert result == {"result": "classified"}


def test_includes_optional_output_token_ceiling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        generation_config = loads(request.content)["generationConfig"]
        assert generation_config["maxOutputTokens"] == 8192
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"result":"ok"}'}]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    with GeminiClient(
        "test-api-key",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = client.generate_structured_content(
            model_id=MODEL_ID,
            system_instruction="System instruction",
            user_prompt="User prompt",
            response_schema=TEST_SCHEMA,
            max_output_tokens=8192,
        )

    assert result == {"result": "ok"}


def test_allows_json_mode_without_provider_schema() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        generation_config = loads(request.content)["generationConfig"]
        assert generation_config["responseFormat"] == {
            "text": {"mimeType": "APPLICATION_JSON"}
        }
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"result":"ok"}'}]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    with GeminiClient(
        "test-api-key",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = client.generate_structured_content(
            model_id=MODEL_ID,
            system_instruction="System instruction",
            user_prompt="User prompt",
            response_schema=None,
        )

    assert result == {"result": "ok"}


def test_detailed_generation_returns_sanitized_usage_counts() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"result":"ok"}'}]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 120,
                    "candidatesTokenCount": 30,
                    "totalTokenCount": 150,
                    "unsafeExtra": "ignored",
                },
            },
        )
    )

    with GeminiClient("test-api-key", transport=transport) as client:
        result = client.generate_structured_content_with_metadata(
            model_id=MODEL_ID,
            system_instruction="System instruction",
            user_prompt="User prompt",
            response_schema=TEST_SCHEMA,
        )

    assert result.content == {"result": "ok"}
    assert result.input_tokens == 120
    assert result.output_tokens == 30
    assert result.total_tokens == 150


def test_rejects_invalid_output_token_ceiling_before_request() -> None:
    transport = httpx.MockTransport(
        lambda request: pytest.fail("No request should be sent.")
    )

    with GeminiClient("test-api-key", transport=transport) as client:
        with pytest.raises(ValueError, match="positive integer"):
            client.generate_structured_content(
                model_id=MODEL_ID,
                system_instruction="System instruction",
                user_prompt="User prompt",
                response_schema=TEST_SCHEMA,
                max_output_tokens=0,
            )


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, GeminiAuthenticationError),
        (403, GeminiAuthenticationError),
        (429, GeminiRateLimitError),
        (500, GeminiUnavailableError),
        (503, GeminiUnavailableError),
        (400, GeminiAPIError),
    ],
)
def test_translates_unsuccessful_responses(
    status_code: int,
    expected_error: type[GeminiAPIError],
) -> None:
    """Translate HTTP failures into stable domain errors."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            status_code,
            json={"error": {"message": "Unsafe upstream detail"}},
        )
    )

    with GeminiClient(
        "test-api-key",
        transport=transport,
    ) as client:
        with pytest.raises(expected_error) as caught:
            client.generate_structured_content(
                model_id=MODEL_ID,
                system_instruction="System instruction",
                user_prompt="User prompt",
                response_schema=TEST_SCHEMA,
            )

    assert caught.value.status_code == status_code


def test_preserves_numeric_retry_after_on_rate_limit() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            429,
            headers={"Retry-After": "120"},
            json={"error": {"message": "Unsafe upstream detail"}},
        )
    )

    with GeminiClient("test-api-key", transport=transport) as client:
        with pytest.raises(GeminiRateLimitError) as caught:
            client.generate_structured_content(
                model_id=MODEL_ID,
                system_instruction="System instruction",
                user_prompt="User prompt",
                response_schema=TEST_SCHEMA,
            )

    assert caught.value.retry_after_seconds == 120
    assert caught.value.status_code == 429


@pytest.mark.parametrize(
    ("message", "provider_status", "expected_reason"),
    [
        (
            "A schema exceeds the maximum allowed nesting depth.",
            "INVALID_ARGUMENT",
            "schema_nesting_depth",
        ),
        (
            "The response schema is too complex.",
            "INVALID_ARGUMENT",
            "schema_complexity",
        ),
        (
            "Request contains an invalid argument.",
            "INVALID_ARGUMENT",
            "invalid_argument",
        ),
    ],
)
def test_sanitizes_provider_rejection_reason(
    message: str,
    provider_status: str,
    expected_reason: str,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400,
            json={
                "error": {
                    "message": message,
                    "status": provider_status,
                }
            },
        )
    )

    with GeminiClient("test-api-key", transport=transport) as client:
        with pytest.raises(GeminiAPIError) as caught:
            client.generate_structured_content(
                model_id=MODEL_ID,
                system_instruction="System instruction",
                user_prompt="User prompt",
                response_schema=TEST_SCHEMA,
            )

    assert caught.value.reason_code == expected_reason
    assert message not in str(caught.value)


def test_network_failure_is_reported_as_unavailable() -> None:
    """Translate transport failures without exposing HTTPX errors."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "Simulated connection failure.",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with GeminiClient(
        "test-api-key",
        transport=transport,
    ) as client:
        with pytest.raises(
            GeminiUnavailableError,
            match="currently unavailable",
        ):
            client.generate_structured_content(
                model_id=MODEL_ID,
                system_instruction="System instruction",
                user_prompt="User prompt",
                response_schema=TEST_SCHEMA,
            )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"candidates": []},
        {"candidates": [{}]},
        {
            "candidates": [
                {
                    "content": {
                        "parts": [],
                    }
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": 123}],
                    }
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "not-json"}],
                    }
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "[]"}],
                    }
                }
            ]
        },
    ],
)
def test_rejects_malformed_success_response(payload: object) -> None:
    """Reject successful HTTP responses without one JSON object."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)
    )

    with GeminiClient(
        "test-api-key",
        transport=transport,
    ) as client:
        with pytest.raises(
            GeminiResponseError,
            match="invalid response data",
        ):
            client.generate_structured_content(
                model_id=MODEL_ID,
                system_instruction="System instruction",
                user_prompt="User prompt",
                response_schema=TEST_SCHEMA,
            )


@pytest.mark.parametrize(
    ("finish_reason", "expected_reason"),
    [
        ("MAX_TOKENS", "output_token_limit"),
        ("SAFETY", "safety_block"),
        ("RECITATION", "recitation_block"),
        ("OTHER", "incomplete_candidate"),
    ],
)
def test_sanitizes_incomplete_candidate_reason(
    finish_reason: str,
    expected_reason: str,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "partial"}]},
                        "finishReason": finish_reason,
                    }
                ]
            },
        )
    )

    with GeminiClient("test-api-key", transport=transport) as client:
        with pytest.raises(GeminiResponseError) as caught:
            client.generate_structured_content(
                model_id=MODEL_ID,
                system_instruction="System instruction",
                user_prompt="User prompt",
                response_schema=TEST_SCHEMA,
            )

    assert caught.value.reason_code == expected_reason


def test_sanitizes_invalid_output_json_reason() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "not-json"}]},
                        "finishReason": "STOP",
                    }
                ]
            },
        )
    )

    with GeminiClient("test-api-key", transport=transport) as client:
        with pytest.raises(GeminiResponseError) as caught:
            client.generate_structured_content(
                model_id=MODEL_ID,
                system_instruction="System instruction",
                user_prompt="User prompt",
                response_schema=TEST_SCHEMA,
            )

    assert caught.value.reason_code == "invalid_output_json"
