from dataclasses import dataclass
from json import JSONDecodeError, loads
from types import TracebackType
from typing import Any, Self

import httpx


GEMINI_API_BASE_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
)


class GeminiAPIError(RuntimeError):
    """Indicate that Gemini rejected or malformed a request."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reason_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason_code = reason_code


class GeminiAuthenticationError(GeminiAPIError):
    """Indicate that Gemini rejected the configured API key."""


class GeminiRateLimitError(GeminiAPIError):
    """Indicate that Gemini rate-limited a request."""

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: int | None = None,
        status_code: int | None = None,
        reason_code: str | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            reason_code=reason_code,
        )
        self.retry_after_seconds = retry_after_seconds


class GeminiUnavailableError(GeminiAPIError):
    """Indicate that Gemini is temporarily unavailable."""


class GeminiResponseError(GeminiAPIError):
    """Indicate that Gemini returned invalid response data."""


@dataclass(frozen=True)
class GeminiStructuredContent:
    """Return validated JSON together with sanitized token accounting."""

    content: dict[str, Any]
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class GeminiClient:
    """Send synchronous structured-output requests to Gemini."""

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Initialize a backend-only Gemini client.

        Args:
            api_key: Private Gemini API key.
            transport: Optional HTTPX transport used by isolated tests.
            timeout_seconds: Total timeout for one provider request.
        """
        self._api_key = api_key
        self._http_client = httpx.Client(
            timeout=timeout_seconds,
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
        response_schema: dict[str, Any] | None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate and decode one structured JSON object.

        Args:
            model_id: Exact stable Gemini model identifier.
            system_instruction: Trusted classifier instructions.
            user_prompt: Per-game prompt containing canonical facts.
            response_schema: Optional JSON Schema restricting the model
                response. ``None`` retains JSON output mode while leaving the
                response contract to the caller's strict validator.
            max_output_tokens: Optional positive response-token ceiling.

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
        return self.generate_structured_content_with_metadata(
            model_id=model_id,
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            response_schema=response_schema,
            max_output_tokens=max_output_tokens,
        ).content

    def generate_structured_content_with_metadata(
        self,
        *,
        model_id: str,
        system_instruction: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None,
        max_output_tokens: int | None = None,
    ) -> GeminiStructuredContent:
        """Generate structured JSON and retain only bounded usage counts."""
        if (
            max_output_tokens is not None
            and (
                not isinstance(max_output_tokens, int)
                or isinstance(max_output_tokens, bool)
                or max_output_tokens <= 0
            )
        ):
            raise ValueError(
                "Maximum output tokens must be a positive integer."
            )

        text_response_format: dict[str, Any] = {
            "mimeType": "APPLICATION_JSON",
        }
        if response_schema is not None:
            text_response_format["schema"] = response_schema
        generation_config: dict[str, Any] = {
            "responseFormat": {"text": text_response_format}
        }

        if max_output_tokens is not None:
            generation_config["maxOutputTokens"] = max_output_tokens

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
            "generationConfig": generation_config,
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
                "Gemini returned invalid response data.",
                reason_code="invalid_http_json",
            ) from None

        response_text = self._extract_response_text(payload)

        try:
            decoded_response: object = loads(response_text)
        except JSONDecodeError:
            raise GeminiResponseError(
                "Gemini returned invalid response data.",
                reason_code="invalid_output_json",
            ) from None

        if not isinstance(decoded_response, dict):
            raise GeminiResponseError(
                "Gemini returned invalid response data.",
                reason_code="invalid_output_shape",
            )

        usage = payload.get("usageMetadata")

        def usage_count(field: str) -> int | None:
            if not isinstance(usage, dict):
                return None
            value = usage.get(field)
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            ):
                return value
            return None

        return GeminiStructuredContent(
            content=decoded_response,
            input_tokens=usage_count("promptTokenCount"),
            output_tokens=usage_count("candidatesTokenCount"),
            total_tokens=usage_count("totalTokenCount"),
        )

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
                "Gemini returned invalid response data.",
                reason_code="invalid_response_envelope",
            )

        candidates = payload.get("candidates")

        if not isinstance(candidates, list) or len(candidates) != 1:
            raise GeminiResponseError(
                "Gemini returned invalid response data.",
                reason_code="invalid_candidate_count",
            )

        candidate = candidates[0]

        if not isinstance(candidate, dict):
            raise GeminiResponseError(
                "Gemini returned invalid response data.",
                reason_code="invalid_candidate",
            )

        finish_reason = candidate.get("finishReason")
        if finish_reason != "STOP":
            reason_code = {
                "MAX_TOKENS": "output_token_limit",
                "SAFETY": "safety_block",
                "RECITATION": "recitation_block",
            }.get(finish_reason, "incomplete_candidate")
            raise GeminiResponseError(
                "Gemini returned invalid response data.",
                reason_code=reason_code,
            )

        content = candidate.get("content")

        if not isinstance(content, dict):
            raise GeminiResponseError(
                "Gemini returned invalid response data.",
                reason_code="invalid_content",
            )

        parts = content.get("parts")

        if not isinstance(parts, list) or len(parts) != 1:
            raise GeminiResponseError(
                "Gemini returned invalid response data.",
                reason_code="invalid_parts",
            )

        part = parts[0]

        if not isinstance(part, dict):
            raise GeminiResponseError(
                "Gemini returned invalid response data.",
                reason_code="invalid_part",
            )

        text = part.get("text")

        if not isinstance(text, str) or not text.strip():
            raise GeminiResponseError(
                "Gemini returned invalid response data.",
                reason_code="missing_text",
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

        reason_code = GeminiClient._classify_rejection_reason(response)

        if response.status_code in {401, 403}:
            raise GeminiAuthenticationError(
                "Gemini authentication was rejected.",
                status_code=response.status_code,
                reason_code=reason_code,
            )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_after_seconds = None
            if retry_after is not None and retry_after.isdecimal():
                retry_after_seconds = int(retry_after)
            raise GeminiRateLimitError(
                "Gemini rate-limited the API request.",
                retry_after_seconds=retry_after_seconds,
                status_code=response.status_code,
                reason_code=reason_code,
            )

        if response.status_code >= 500:
            raise GeminiUnavailableError(
                "Gemini is currently unavailable.",
                status_code=response.status_code,
                reason_code=reason_code,
            )

        raise GeminiAPIError(
            "Gemini rejected the API request.",
            status_code=response.status_code,
            reason_code=reason_code,
        )

    @staticmethod
    def _classify_rejection_reason(response: httpx.Response) -> str | None:
        """Map provider error text to one allowlisted diagnostic category."""
        try:
            payload: object = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        if not isinstance(error, dict):
            return None
        message = error.get("message")
        provider_status = error.get("status")
        normalized = message.casefold() if isinstance(message, str) else ""
        if "nesting depth" in normalized:
            return "schema_nesting_depth"
        if "schema" in normalized and any(
            marker in normalized
            for marker in ("complex", "exceed", "too large")
        ):
            return "schema_complexity"
        if "responseformat" in normalized or "response format" in normalized:
            return "response_format"
        if "maxoutputtokens" in normalized or "max output tokens" in normalized:
            return "output_token_limit"
        if "not supported" in normalized and "model" in normalized:
            return "unsupported_model_feature"
        if provider_status == "INVALID_ARGUMENT":
            return "invalid_argument"
        return None
