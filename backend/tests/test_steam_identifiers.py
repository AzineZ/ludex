import pytest

from app.integrations.steam.identifiers import (
    InvalidSteamIdentifierError,
    SteamIdentifier,
    normalize_steam_identifier,
)


@pytest.mark.parametrize(
    ("raw_identifier", "expected"),
    [
        (
            "76561198000000000",
            SteamIdentifier(
                kind="steam_id",
                value="76561198000000000",
            ),
        ),
        (
            " 76561198000000000 ",
            SteamIdentifier(
                kind="steam_id",
                value="76561198000000000",
            ),
        ),
        (
            "https://steamcommunity.com/profiles/76561198000000000/",
            SteamIdentifier(
                kind="steam_id",
                value="76561198000000000",
            ),
        ),
        (
            "http://www.steamcommunity.com/profiles/76561198000000000",
            SteamIdentifier(
                kind="steam_id",
                value="76561198000000000",
            ),
        ),
        (
            "steamcommunity.com/id/example-user/",
            SteamIdentifier(
                kind="vanity",
                value="example-user",
            ),
        ),
        (
            "https://steamcommunity.com/id/Example_Name",
            SteamIdentifier(
                kind="vanity",
                value="Example_Name",
            ),
        ),
    ],
)
def test_normalize_steam_identifier(
    raw_identifier: str,
    expected: SteamIdentifier,
) -> None:
    assert normalize_steam_identifier(raw_identifier) == expected


@pytest.mark.parametrize(
    "raw_identifier",
    [
        "",
        "12345",
        "example-user",
        "https://example.com/id/example-user",
        "https://steamcommunity.com/groups/example",
        "https://steamcommunity.com/profiles/not-a-steam-id",
        "https://steamcommunity.com/id/",
        "https://steamcommunity.com/id/example/extra",
        "ftp://steamcommunity.com/id/example",
    ],
)
def test_normalize_steam_identifier_rejects_invalid_input(
    raw_identifier: str,
) -> None:
    with pytest.raises(InvalidSteamIdentifierError):
        normalize_steam_identifier(raw_identifier)
