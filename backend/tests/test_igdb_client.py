import httpx
import pytest

from app.integrations.igdb.client import (
    IGDBAPIError,
    IGDBAuthenticationError,
    IGDBClient,
    IGDBRateLimitError,
    IGDBResponseError,
    IGDBUnavailableError,
)


TOKEN_HOST = "id.twitch.tv"
IGDB_HOST = "api.igdb.com"


class FakeClock:
    """Provide a controllable monotonic clock for expiration tests."""

    def __init__(self, current_time: float = 1_000.0) -> None:
        self.current_time = current_time

    def __call__(self) -> float:
        """Return the controlled current time."""
        return self.current_time

    def advance(self, seconds: float) -> None:
        """Advance the controlled time."""
        self.current_time += seconds


def token_response(
    access_token: str = "test-token",
    expires_in: int = 3_600,
) -> httpx.Response:
    """Create a successful Twitch token response."""
    return httpx.Response(
        200,
        json={
            "access_token": access_token,
            "expires_in": expires_in,
            "token_type": "bearer",
        },
    )


def test_query_authenticates_and_sends_igdb_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == TOKEN_HOST:
            assert request.method == "POST"
            assert request.url.path == "/oauth2/token"
            assert request.url.params["client_id"] == "test-client"
            assert request.url.params["client_secret"] == "test-secret"
            assert (
                request.url.params["grant_type"]
                == "client_credentials"
            )

            return token_response()

        assert request.url.host == IGDB_HOST
        assert request.url.path == "/v4/games"
        assert request.headers["Client-ID"] == "test-client"
        assert (
            request.headers["Authorization"]
            == "Bearer test-token"
        )
        assert request.content == b"fields id,name; limit 1;"

        return httpx.Response(
            200,
            json=[
                {
                    "id": 1942,
                    "name": "The Witcher 3: Wild Hunt",
                }
            ],
        )

    transport = httpx.MockTransport(handler)

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        games = client.query(
            "games",
            "fields id,name; limit 1;",
        )

    assert games == [
        {
            "id": 1942,
            "name": "The Witcher 3: Wild Hunt",
        }
    ]


def test_token_is_reused_before_expiration() -> None:
    request_counts = {
        "token": 0,
        "igdb": 0,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == TOKEN_HOST:
            request_counts["token"] += 1
            return token_response()

        request_counts["igdb"] += 1
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        client.query("games", "fields id; limit 1;")
        client.query("games", "fields id; limit 1;")

    assert request_counts == {
        "token": 1,
        "igdb": 2,
    }


def test_expired_token_is_replaced() -> None:
    clock = FakeClock()
    token_requests = 0
    authorization_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_requests

        if request.url.host == TOKEN_HOST:
            token_requests += 1

            return token_response(
                access_token=f"token-{token_requests}",
                expires_in=100,
            )

        authorization_headers.append(
            request.headers["Authorization"]
        )
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
        clock=clock,
    ) as client:
        client.query("games", "fields id; limit 1;")

        # A 100-second token uses a 10-second refresh margin.
        clock.advance(91)

        client.query("games", "fields id; limit 1;")

    assert token_requests == 2
    assert authorization_headers == [
        "Bearer token-1",
        "Bearer token-2",
    ]


def test_rejected_credentials_raise_authentication_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            401,
            json={"message": "Invalid OAuth token"},
        )
    )

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        with pytest.raises(IGDBAuthenticationError):
            client.query("games", "fields id; limit 1;")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"access_token": "", "expires_in": 3_600},
        {"access_token": "token"},
        {"access_token": "token", "expires_in": 0},
        {"access_token": "token", "expires_in": True},
        {"access_token": "token", "expires_in": "3600"},
        [],
    ],
)
def test_invalid_token_response_is_rejected(
    payload: object,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=payload,
        )
    )

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        with pytest.raises(IGDBResponseError):
            client.query("games", "fields id; limit 1;")


def test_network_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "Connection failed",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        with pytest.raises(IGDBUnavailableError):
            client.query("games", "fields id; limit 1;")


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, IGDBAuthenticationError),
        (403, IGDBAuthenticationError),
        (429, IGDBRateLimitError),
        (503, IGDBUnavailableError),
        (422, IGDBAPIError),
    ],
)
def test_igdb_status_errors_are_translated(
    status_code: int,
    expected_error: type[IGDBAPIError],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == TOKEN_HOST:
            return token_response()

        return httpx.Response(
            status_code,
            json={"message": "Request rejected"},
        )

    transport = httpx.MockTransport(handler)

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        with pytest.raises(expected_error):
            client.query("games", "fields id; limit 1;")


def test_invalid_igdb_json_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == TOKEN_HOST:
            return token_response()

        return httpx.Response(
            200,
            content=b"not-json",
        )

    transport = httpx.MockTransport(handler)

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        with pytest.raises(IGDBResponseError):
            client.query("games", "fields id; limit 1;")


@pytest.mark.parametrize(
    "payload",
    [
        {"id": 1942},
        [1942],
        ["invalid entry"],
    ],
)
def test_invalid_igdb_payload_is_rejected(
    payload: object,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == TOKEN_HOST:
            return token_response()

        return httpx.Response(
            200,
            json=payload,
        )

    transport = httpx.MockTransport(handler)

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        with pytest.raises(IGDBResponseError):
            client.query("games", "fields id; limit 1;")


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "/games",
        "../games",
        "https://example.com",
        "external/games",
    ],
)
def test_invalid_endpoint_is_rejected(
    endpoint: str,
) -> None:
    def unexpected_request(
        request: httpx.Request,
    ) -> httpx.Response:
        raise AssertionError("No HTTP request should be sent")

    transport = httpx.MockTransport(unexpected_request)

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        with pytest.raises(ValueError):
            client.query(
                endpoint,
                "fields id; limit 1;",
            )


def test_empty_query_is_rejected() -> None:
    def unexpected_request(
        request: httpx.Request,
    ) -> httpx.Response:
        raise AssertionError("No HTTP request should be sent")

    transport = httpx.MockTransport(unexpected_request)

    with IGDBClient(
        "test-client",
        "test-secret",
        transport=transport,
    ) as client:
        with pytest.raises(ValueError):
            client.query("games", "   ")
