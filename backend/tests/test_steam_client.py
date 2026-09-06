from datetime import UTC, datetime

import httpx
import pytest

from app.integrations.steam.client import (
    SteamAPIError,
    SteamAPIUnavailableError,
    SteamClient,
    SteamLibraryUnavailableError,
    SteamOwnedGame,
    SteamProfile,
    SteamProfileNotFoundError,
)
from app.integrations.steam.identifiers import SteamIdentifier


def test_numeric_identifier_does_not_call_steam() -> None:
    def unexpected_request(
        request: httpx.Request,
    ) -> httpx.Response:
        raise AssertionError("Steam should not be called")

    transport = httpx.MockTransport(unexpected_request)

    with SteamClient("test-key", transport=transport) as client:
        steam_id = client.resolve_steam_id(
            SteamIdentifier(
                kind="steam_id",
                value="76561198000000000",
            )
        )

    assert steam_id == "76561198000000000"


def test_resolve_vanity_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == (
            "/ISteamUser/ResolveVanityURL/v1/"
        )
        assert request.url.params["key"] == "test-key"
        assert request.url.params["vanityurl"] == "example"

        return httpx.Response(
            200,
            json={
                "response": {
                    "success": 1,
                    "steamid": "76561198000000000",
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with SteamClient("test-key", transport=transport) as client:
        steam_id = client.resolve_steam_id(
            SteamIdentifier(
                kind="vanity",
                value="example",
            )
        )

    assert steam_id == "76561198000000000"


def test_unresolved_vanity_url_is_not_found() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "response": {
                    "success": 42,
                    "message": "No match",
                }
            },
        )
    )

    with SteamClient("test-key", transport=transport) as client:
        with pytest.raises(SteamProfileNotFoundError):
            client.resolve_steam_id(
                SteamIdentifier(
                    kind="vanity",
                    value="missing",
                )
            )


def test_get_profile() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "response": {
                    "players": [
                        {
                            "steamid": "76561198000000000",
                            "personaname": "Example Player",
                            "profileurl": (
                                "https://steamcommunity.com/"
                                "profiles/76561198000000000/"
                            ),
                            "avatarfull": (
                                "https://example.com/avatar.jpg"
                            ),
                        }
                    ]
                }
            },
        )
    )

    with SteamClient("test-key", transport=transport) as client:
        profile = client.get_profile(
            "76561198000000000"
        )

    assert profile == SteamProfile(
        steam_id="76561198000000000",
        display_name="Example Player",
        profile_url=(
            "https://steamcommunity.com/"
            "profiles/76561198000000000/"
        ),
        avatar_url="https://example.com/avatar.jpg",
    )


def test_get_owned_games() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "response": {
                    "game_count": 1,
                    "games": [
                        {
                            "appid": 440,
                            "name": "Team Fortress 2",
                            "img_icon_url": "icon-hash",
                            "playtime_forever": 120,
                            "playtime_2weeks": 30,
                            "rtime_last_played": 1_720_000_000,
                        }
                    ],
                }
            },
        )
    )

    with SteamClient("test-key", transport=transport) as client:
        games = client.get_owned_games(
            "76561198000000000"
        )

    assert games == [
        SteamOwnedGame(
            steam_app_id=440,
            name="Team Fortress 2",
            icon_url=(
                "https://media.steampowered.com/"
                "steamcommunity/public/images/apps/"
                "440/icon-hash.jpg"
            ),
            playtime_minutes=120,
            recent_playtime_minutes=30,
            last_played_at=datetime.fromtimestamp(
                1_720_000_000,
                tz=UTC,
            ),
        )
    ]


def test_empty_public_library_is_valid() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "response": {
                    "game_count": 0,
                    "games": [],
                }
            },
        )
    )

    with SteamClient("test-key", transport=transport) as client:
        games = client.get_owned_games(
            "76561198000000000"
        )

    assert games == []


def test_private_library_is_unavailable() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"response": {}},
        )
    )

    with SteamClient("test-key", transport=transport) as client:
        with pytest.raises(SteamLibraryUnavailableError):
            client.get_owned_games(
                "76561198000000000"
            )


def test_network_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "Connection failed",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with SteamClient("test-key", transport=transport) as client:
        with pytest.raises(SteamAPIUnavailableError):
            client.get_profile(
                "76561198000000000"
            )


@pytest.mark.parametrize(
    ("operation", "payload", "expected_message"),
    [
        (
            "profile",
            {"response": {"players": ["not-an-object"]}},
            "Steam returned an unexpected profile response.",
        ),
        (
            "library",
            {
                "response": {
                    "game_count": 1,
                    "games": [
                        {
                            "appid": "440",
                            "name": "Team Fortress 2",
                        }
                    ],
                }
            },
            "Steam returned an invalid Steam App ID.",
        ),
        (
            "library",
            {
                "response": {
                    "game_count": 1,
                    "games": "not-a-list",
                }
            },
            "Steam returned an unexpected library response.",
        ),
    ],
)
def test_rejects_malformed_profile_and_library_payloads(
    operation: str,
    payload: object,
    expected_message: str,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)
    )

    with SteamClient("test-key", transport=transport) as client:
        with pytest.raises(SteamAPIError, match=expected_message):
            if operation == "profile":
                client.get_profile("76561198000000000")
            else:
                client.get_owned_games("76561198000000000")
