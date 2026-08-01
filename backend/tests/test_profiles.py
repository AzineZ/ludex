import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.steam_client import (
    SteamAPIError,
    SteamAPIUnavailableError,
    SteamClient,
    SteamLibraryUnavailableError,
    SteamOwnedGame,
    SteamProfile,
    SteamProfileNotFoundError,
)

STEAM_ID = "76561198000000000"


def configure_successful_steam_response(
    steam_client: MagicMock,
) -> None:
    steam_client.resolve_steam_id.return_value = STEAM_ID
    steam_client.get_profile.return_value = SteamProfile(
        steam_id=STEAM_ID,
        display_name="Test Player",
        profile_url=f"https://steamcommunity.com/profiles/{STEAM_ID}/",
        avatar_url="https://example.com/avatar.jpg",
    )
    steam_client.get_owned_games.return_value = [
        SteamOwnedGame(
            steam_app_id=20,
            name="Zeta Game",
            icon_url=None,
            playtime_minutes=90,
            recent_playtime_minutes=30,
            last_played_at=None,
        ),
        SteamOwnedGame(
            steam_app_id=10,
            name="Alpha Game",
            icon_url=None,
            playtime_minutes=0,
            recent_playtime_minutes=None,
            last_played_at=None,
        ),
    ]


def test_create_profile_imports_steam_library(
        profile_api_client: TestClient,
        steam_client: MagicMock,
) -> None:
    configure_successful_steam_response(steam_client)

    response = profile_api_client.post(
        "/profiles",
        json={"identifier": STEAM_ID},
    )

    assert response.status_code == 200

    response_data = response.json()

    assert response_data["steam_id"] == STEAM_ID
    assert response_data["display_name"] == "Test Player"
    assert response_data["created_at"] is not None
    assert response_data["last_synced_at"] is not None
    assert response_data["games"] == [
        {
            "steam_app_id": 10,
            "name": "Alpha Game",
            "icon_url": None,
            "playtime_minutes": 0,
            "recent_playtime_minutes": None,
            "last_played_at": None,
        },
        {
            "steam_app_id": 20,
            "name": "Zeta Game",
            "icon_url": None,
            "playtime_minutes": 90,
            "recent_playtime_minutes": 30,
            "last_played_at": None,
        },
    ]

    steam_client.resolve_steam_id.assert_called_once()
    steam_client.get_profile.assert_called_once_with(STEAM_ID)
    steam_client.get_owned_games.assert_called_once_with(STEAM_ID)


def test_list_and_get_profile_use_cached_data(
    profile_api_client: TestClient,
    steam_client: MagicMock,
) -> None:
    configure_successful_steam_response(steam_client)

    create_response = profile_api_client.post(
        "/profiles",
        json={"identifier": STEAM_ID},
    )
    assert create_response.status_code == 200

    profile_id = create_response.json()["id"]
    steam_client.reset_mock()

    list_response = profile_api_client.get("/profiles")

    assert list_response.status_code == 200

    profiles = list_response.json()

    assert len(profiles) == 1
    assert profiles[0]["id"] == profile_id
    assert profiles[0]["steam_id"] == STEAM_ID
    assert profiles[0]["display_name"] == "Test Player"
    assert "games" not in profiles[0]

    detail_response = profile_api_client.get(
        f"/profiles/{profile_id}"
    )

    assert detail_response.status_code == 200

    profile = detail_response.json()

    assert profile["id"] == profile_id
    assert profile["steam_id"] == STEAM_ID
    assert [
        game["name"]
        for game in profile["games"]
    ] == [
        "Alpha Game",
        "Zeta Game",
    ]

    steam_client.resolve_steam_id.assert_not_called()
    steam_client.get_profile.assert_not_called()
    steam_client.get_owned_games.assert_not_called()


def test_refresh_profile_updates_cached_library(
    profile_api_client: TestClient,
    steam_client: MagicMock,
) -> None:
    configure_successful_steam_response(steam_client)

    create_response = profile_api_client.post(
        "/profiles",
        json={"identifier": STEAM_ID},
    )
    assert create_response.status_code == 200

    profile_id = create_response.json()["id"]

    steam_client.reset_mock()
    steam_client.resolve_steam_id.return_value = STEAM_ID
    steam_client.get_profile.return_value = SteamProfile(
        steam_id=STEAM_ID,
        display_name="Updated Player",
        profile_url=f"https://steamcommunity.com/profiles/{STEAM_ID}/",
        avatar_url="https://example.com/updated-avatar.jpg",
    )
    steam_client.get_owned_games.return_value = [
        SteamOwnedGame(
            steam_app_id=10,
            name="Alpha Game",
            icon_url=None,
            playtime_minutes=120,
            recent_playtime_minutes=45,
            last_played_at=None,
        ),
        SteamOwnedGame(
            steam_app_id=30,
            name="New Game",
            icon_url=None,
            playtime_minutes=15,
            recent_playtime_minutes=None,
            last_played_at=None,
        ),
    ]

    refresh_response = profile_api_client.post(
        f"/profiles/{profile_id}/refresh"
    )

    assert refresh_response.status_code == 200

    refreshed_profile = refresh_response.json()

    assert refreshed_profile["display_name"] == "Updated Player"
    assert refreshed_profile["avatar_url"] == (
        "https://example.com/updated-avatar.jpg"
    )
    assert refreshed_profile["games"] == [
        {
            "steam_app_id": 10,
            "name": "Alpha Game",
            "icon_url": None,
            "playtime_minutes": 120,
            "recent_playtime_minutes": 45,
            "last_played_at": None,
        },
        {
            "steam_app_id": 30,
            "name": "New Game",
            "icon_url": None,
            "playtime_minutes": 15,
            "recent_playtime_minutes": None,
            "last_played_at": None,
        },
    ]

    steam_client.resolve_steam_id.assert_called_once()
    steam_client.get_profile.assert_called_once_with(STEAM_ID)
    steam_client.get_owned_games.assert_called_once_with(STEAM_ID)


def test_get_profile_returns_not_found_for_unknown_id(
    profile_api_client: TestClient,
) -> None:
    """Verify that reading an unknown local profile returns HTTP 404."""
    response = profile_api_client.get("/profiles/999")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Profile not found.",
    }


def test_refresh_profile_returns_not_found_for_unknown_id(
    profile_api_client: TestClient,
    steam_client: MagicMock,
) -> None:
    """Verify that refreshing an unknown profile never contacts Steam."""
    response = profile_api_client.post(
        "/profiles/999/refresh"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Profile not found.",
    }

    steam_client.resolve_steam_id.assert_not_called()
    steam_client.get_profile.assert_not_called()
    steam_client.get_owned_games.assert_not_called()


def test_create_profile_rejects_invalid_identifier(
    profile_api_client: TestClient,
    steam_client: MagicMock,
) -> None:
    """Verify that invalid identifiers are rejected before contacting Steam."""
    response = profile_api_client.post(
        "/profiles",
        json={"identifier": "https://example.com/id/player"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Enter a 17-digit Steam ID or a Steam Community profile URL."
        ),
    }

    steam_client.resolve_steam_id.assert_not_called()
    steam_client.get_profile.assert_not_called()
    steam_client.get_owned_games.assert_not_called()


@pytest.mark.parametrize(
    (
        "error",
        "expected_status",
        "expected_detail",
    ),
    [
        (
            SteamProfileNotFoundError(
                "The Steam profile could not be found."
            ),
            404,
            "The Steam profile could not be found.",
        ),
        (
            SteamLibraryUnavailableError(
                "This Steam library is private or unavailable."
            ),
            422,
            "This Steam library is private or unavailable.",
        ),
        (
            SteamAPIUnavailableError(
                "Steam is currently unavailable."
            ),
            503,
            "Steam is currently unavailable.",
        ),
        (
            SteamAPIError(
                "Steam returned invalid response data."
            ),
            502,
            "Steam returned invalid response data.",
        ),
    ],
)
def test_create_profile_maps_steam_errors_to_http_responses(
    profile_api_client: TestClient,
    steam_client: MagicMock,
    error: SteamAPIError,
    expected_status: int,
    expected_detail: str,
) -> None:
    """Verify that Steam domain errors become stable HTTP responses."""
    steam_client.resolve_steam_id.side_effect = error

    response = profile_api_client.post(
        "/profiles",
        json={"identifier": STEAM_ID},
    )

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": expected_detail,
    }
