from datetime import UTC, datetime

import httpx
import pytest

from app.integrations.steam.client import (
    SteamAPIError,
    SteamAPIUnavailableError,
    SteamAchievementStatus,
    SteamAchievementSummary,
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
        with pytest.raises(SteamLibraryUnavailableError) as error:
            client.get_owned_games(
                "76561198000000000"
            )

    assert str(error.value) == (
        "This Steam library is private. Set My profile and Game details to "
        "Public in Steam (Edit Profile → Privacy Settings), then try again."
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


def _achievement_client(handler) -> SteamClient:
    return SteamClient("test-key", transport=httpx.MockTransport(handler))


def test_player_achievements_keep_only_counts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ISteamUserStats/GetPlayerAchievements/v1/"
        assert request.url.params["steamid"] == "76561198000000000"
        assert request.url.params["appid"] == "1245620"
        return httpx.Response(
            200,
            json={
                "playerstats": {
                    "steamID": "76561198000000000",
                    "gameName": "ELDEN RING",
                    "success": True,
                    "achievements": [
                        {"apiname": "A", "achieved": 1, "unlocktime": 1},
                        {"apiname": "B", "achieved": 1, "unlocktime": 2},
                        {"apiname": "C", "achieved": 0, "unlocktime": 0},
                    ],
                }
            },
        )

    with _achievement_client(handler) as client:
        summary = client.get_player_achievements("76561198000000000", 1245620)

    assert summary == SteamAchievementSummary(
        SteamAchievementStatus.OK,
        unlocked_count=2,
        total_count=3,
    )


@pytest.mark.parametrize(
    ("status_code", "playerstats", "expected"),
    [
        (
            400,
            {"error": "Requested app has no stats", "success": False},
            SteamAchievementStatus.NO_ACHIEVEMENTS,
        ),
        (
            403,
            {"error": "Profile is not public", "success": False},
            SteamAchievementStatus.PRIVATE,
        ),
        (
            200,
            {"success": True, "gameName": "No achievements"},
            SteamAchievementStatus.NO_ACHIEVEMENTS,
        ),
    ],
)
def test_player_achievement_outcomes_that_are_not_failures(
    status_code: int,
    playerstats: dict[str, object],
    expected: SteamAchievementStatus,
) -> None:
    with _achievement_client(
        lambda request: httpx.Response(
            status_code,
            json={"playerstats": playerstats},
        )
    ) as client:
        summary = client.get_player_achievements("76561198000000000", 10)

    assert summary == SteamAchievementSummary(expected)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"playerstats": {"success": False, "error": "x"}}),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, text="not json"),
        httpx.Response(
            200,
            json={
                "playerstats": {
                    "success": True,
                    "achievements": [{"apiname": "A", "achieved": 2}],
                }
            },
        ),
    ],
)
def test_player_achievement_failures_raise(response: httpx.Response) -> None:
    with _achievement_client(lambda request: response) as client:
        with pytest.raises(SteamAPIError):
            client.get_player_achievements("76561198000000000", 10)


def test_player_achievement_network_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with _achievement_client(handler) as client:
        with pytest.raises(SteamAPIUnavailableError):
            client.get_player_achievements("76561198000000000", 10)
