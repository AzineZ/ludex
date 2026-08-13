from json import loads

import httpx
import pytest

from app.gemini_client import (
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
        with pytest.raises(expected_error):
            client.generate_structured_content(
                model_id=MODEL_ID,
                system_instruction="System instruction",
                user_prompt="User prompt",
                response_schema=TEST_SCHEMA,
            )


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
