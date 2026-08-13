from json import JSONDecodeError, loads
from types import TracebackType
from typing import Any, Self

import httpx


GEMINI_API_BASE_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
)


class GeminiAPIError(RuntimeError):
    """Indicate that Gemini rejected or malformed a request."""


class GeminiAuthenticationError(GeminiAPIError):
    """Indicate that Gemini rejected the configured API key."""


class GeminiRateLimitError(GeminiAPIError):
    """Indicate that Gemini rate-limited a request."""


class GeminiUnavailableError(GeminiAPIError):
    """Indicate that Gemini is temporarily unavailable."""


class GeminiResponseError(GeminiAPIError):
    """Indicate that Gemini returned invalid response data."""


class GeminiClient:
    """Send synchronous structured-output requests to Gemini."""

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize a backend-only Gemini client.

        Args:
            api_key: Private Gemini API key.
            transport: Optional HTTPX transport used by isolated tests.
        """
        self._api_key = api_key
        self._http_client = httpx.Client(
            timeout=30.0,
            transport=transport,
        )

    def __enter__(self) -> Self:
        """Enter a context and return this client."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit a context and release the HTTP connection."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http_client.close()

    def generate_structured_content(
        self,
        *,
        model_id: str,
        system_instruction: str,
        user_prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate and decode one structured JSON object.

        Args:
            model_id: Exact stable Gemini model identifier.
            system_instruction: Trusted classifier instructions.
            user_prompt: Per-game prompt containing canonical facts.
            response_schema: JSON Schema restricting the model response.

        Returns:
            The decoded JSON object returned by Gemini.

        Raises:
            GeminiAuthenticationError: If authentication is rejected.
            GeminiRateLimitError: If the request is rate-limited.
            GeminiUnavailableError: If Gemini cannot be reached.
            GeminiResponseError: If a successful response is malformed,
                incomplete, or does not contain a JSON object.
            GeminiAPIError: If Gemini otherwise rejects the request.
        """
        request_body = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "responseFormat": {
                    "text": {
                        "mimeType": "APPLICATION_JSON",
                        "schema": response_schema,
                    }
                }
            },
        }

        try:
            response = self._http_client.post(
                (
                    f"{GEMINI_API_BASE_URL}/models/"
                    f"{model_id}:generateContent"
                ),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self._api_key,
                },
                json=request_body,
            )
        except httpx.RequestError:
            raise GeminiUnavailableError(
                "Gemini is currently unavailable."
            ) from None

        self._raise_api_error(response)

        try:
            payload: object = response.json()
        except ValueError:
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            ) from None

        response_text = self._extract_response_text(payload)

        try:
            decoded_response: object = loads(response_text)
        except JSONDecodeError:
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            ) from None

        if not isinstance(decoded_response, dict):
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            )

        return decoded_response

    @staticmethod
    def _extract_response_text(payload: object) -> str:
        """Extract one completed candidate's structured text.

        Args:
            payload: Decoded Gemini response payload.

        Returns:
            The candidate's non-empty text.

        Raises:
            GeminiResponseError: If the response structure or finish reason is
                invalid.
        """
        if not isinstance(payload, dict):
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            )

        candidates = payload.get("candidates")

        if not isinstance(candidates, list) or len(candidates) != 1:
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            )

        candidate = candidates[0]

        if (
            not isinstance(candidate, dict)
            or candidate.get("finishReason") != "STOP"
        ):
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            )

        content = candidate.get("content")

        if not isinstance(content, dict):
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            )

        parts = content.get("parts")

        if not isinstance(parts, list) or len(parts) != 1:
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            )

        part = parts[0]

        if not isinstance(part, dict):
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            )

        text = part.get("text")

        if not isinstance(text, str) or not text.strip():
            raise GeminiResponseError(
                "Gemini returned invalid response data."
            )

        return text

    @staticmethod
    def _raise_api_error(response: httpx.Response) -> None:
        """Translate an unsuccessful Gemini HTTP response.

        Args:
            response: Completed HTTP response from Gemini.

        Raises:
            GeminiAuthenticationError: For rejected credentials.
            GeminiRateLimitError: For rate limiting.
            GeminiUnavailableError: For server failures.
            GeminiAPIError: For other unsuccessful statuses.
        """
        if response.is_success:
            return

        if response.status_code in {401, 403}:
            raise GeminiAuthenticationError(
                "Gemini authentication was rejected."
            )

        if response.status_code == 429:
            raise GeminiRateLimitError(
                "Gemini rate-limited the API request."
            )

        if response.status_code >= 500:
            raise GeminiUnavailableError(
                "Gemini is currently unavailable."
            )

        raise GeminiAPIError(
            "Gemini rejected the API request."
        )
