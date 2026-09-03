from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Game, Profile, ProfileGame
from app.profile_service import sync_profile
from app.steam_client import (
    SteamAPIUnavailableError,
    SteamClient,
    SteamOwnedGame,
    SteamProfile,
)


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        yield session


def make_steam_client(
    steam_id: str,
    display_name: str,
    games: list[SteamOwnedGame],
) -> MagicMock:
    client = MagicMock(spec=SteamClient)
    client.resolve_steam_id.return_value = steam_id
    client.get_profile.return_value = SteamProfile(
        steam_id=steam_id,
        display_name=display_name,
        profile_url=(
            f"https://steamcommunity.com/profiles/{steam_id}/"
        ),
        avatar_url="https://example.com/avatar.jpg",
    )
    client.get_owned_games.return_value = games

    return client


def make_game(
    steam_app_id: int,
    name: str,
    playtime_minutes: int,
) -> SteamOwnedGame:
    return SteamOwnedGame(
        steam_app_id=steam_app_id,
        name=name,
        icon_url=f"https://example.com/{steam_app_id}.jpg",
        playtime_minutes=playtime_minutes,
        recent_playtime_minutes=None,
        last_played_at=None,
    )


def test_sync_profile_creates_profile_and_library(
    database_session: Session,
) -> None:
    client = make_steam_client(
        steam_id="76561198000000000",
        display_name="First Player",
        games=[
            make_game(440, "Team Fortress 2", 120),
            make_game(570, "Dota 2", 60),
        ],
    )

    profile = sync_profile(
        database_session,
        client,
        "76561198000000000",
    )

    assert profile.id is not None
    assert profile.display_name == "First Player"
    assert profile.last_synced_at is not None
    assert len(profile.owned_games) == 2

    assert database_session.scalar(
        select(func.count()).select_from(Profile)
    ) == 1
    assert database_session.scalar(
        select(func.count()).select_from(Game)
    ) == 2
    assert database_session.scalar(
        select(func.count()).select_from(ProfileGame)
    ) == 2


def test_sync_profile_refreshes_existing_profile(
    database_session: Session,
) -> None:
    client = make_steam_client(
        steam_id="76561198000000000",
        display_name="Original Name",
        games=[
            make_game(440, "Team Fortress 2", 120),
            make_game(570, "Dota 2", 60),
        ],
    )

    original_profile = sync_profile(
        database_session,
        client,
        "76561198000000000",
    )
    original_profile_id = original_profile.id

    client.get_profile.return_value = SteamProfile(
        steam_id="76561198000000000",
        display_name="Updated Name",
        profile_url="https://example.com/profile",
        avatar_url="https://example.com/new-avatar.jpg",
    )
    client.get_owned_games.return_value = [
        make_game(440, "Team Fortress 2", 240),
        make_game(730, "Counter-Strike 2", 30),
    ]

    refreshed_profile = sync_profile(
        database_session,
        client,
        "76561198000000000",
    )

    assert refreshed_profile.id == original_profile_id
    assert refreshed_profile.display_name == "Updated Name"

    ownerships = database_session.scalars(
        select(ProfileGame).where(
            ProfileGame.profile_id == refreshed_profile.id
        )
    ).all()

    assert {
        ownership.steam_app_id
        for ownership in ownerships
    } == {440, 730}

    refreshed_playtime = database_session.scalar(
        select(ProfileGame.playtime_minutes).where(
            ProfileGame.profile_id == refreshed_profile.id,
            ProfileGame.steam_app_id == 440,
        )
    )

    assert refreshed_playtime == 240

    # Dota remains in the shared game cache even though this
    # profile no longer owns it.
    assert database_session.scalar(
        select(func.count()).select_from(Game)
    ) == 3


def test_profiles_share_cached_game_rows(
    database_session: Session,
) -> None:
    shared_game = make_game(
        440,
        "Team Fortress 2",
        120,
    )

    first_client = make_steam_client(
        steam_id="76561198000000000",
        display_name="First Player",
        games=[shared_game],
    )
    second_client = make_steam_client(
        steam_id="76561198000000001",
        display_name="Second Player",
        games=[shared_game],
    )

    sync_profile(
        database_session,
        first_client,
        "76561198000000000",
    )
    sync_profile(
        database_session,
        second_client,
        "76561198000000001",
    )

    assert database_session.scalar(
        select(func.count()).select_from(Profile)
    ) == 2
    assert database_session.scalar(
        select(func.count()).select_from(Game)
    ) == 1
    assert database_session.scalar(
        select(func.count()).select_from(ProfileGame)
    ) == 2


def test_failed_refresh_preserves_cached_profile(
    database_session: Session,
) -> None:
    client = make_steam_client(
        steam_id="76561198000000000",
        display_name="Cached Name",
        games=[
            make_game(440, "Team Fortress 2", 120),
        ],
    )

    cached_profile = sync_profile(
        database_session,
        client,
        "76561198000000000",
    )
    cached_sync_time = cached_profile.last_synced_at

    client.get_owned_games.side_effect = (
        SteamAPIUnavailableError(
            "Steam is currently unavailable."
        )
    )

    with pytest.raises(SteamAPIUnavailableError):
        sync_profile(
            database_session,
            client,
            "76561198000000000",
        )

    stored_profile = database_session.scalar(
        select(Profile).where(
            Profile.steam_id == "76561198000000000"
        )
    )

    assert stored_profile is not None
    assert stored_profile.display_name == "Cached Name"
    assert stored_profile.last_synced_at == cached_sync_time
    assert len(stored_profile.owned_games) == 1


def test_failed_profile_write_rolls_back_the_complete_snapshot(
    database_session: Session,
) -> None:
    client = make_steam_client(
        steam_id="76561198000000000",
        display_name="Cached Name",
        games=[make_game(440, "Team Fortress 2", 120)],
    )
    cached_profile = sync_profile(
        database_session,
        client,
        "76561198000000000",
    )
    cached_sync_time = cached_profile.last_synced_at

    client.get_profile.return_value = SteamProfile(
        steam_id="76561198000000000",
        display_name="Partial Name",
        profile_url="https://example.com/partial",
        avatar_url="https://example.com/partial-avatar.jpg",
    )
    client.get_owned_games.return_value = [
        make_game(440, "Changed Team Fortress 2", 999),
        make_game(730, "Counter-Strike 2", 30),
    ]

    engine = database_session.get_bind()

    def fail_new_ownership(_, __, statement, ___, ____, _____) -> None:
        if statement.lstrip().upper().startswith(
            "INSERT INTO PROFILE_GAMES"
        ):
            raise OperationalError(
                statement,
                {},
                RuntimeError("simulated profile write failure"),
            )

    event.listen(engine, "before_cursor_execute", fail_new_ownership)
    try:
        with pytest.raises(
            OperationalError,
            match="simulated profile write failure",
        ):
            sync_profile(
                database_session,
                client,
                "76561198000000000",
            )
    finally:
        event.remove(engine, "before_cursor_execute", fail_new_ownership)

    stored_profile = database_session.scalar(
        select(Profile).where(
            Profile.steam_id == "76561198000000000"
        )
    )
    ownership = database_session.scalar(
        select(ProfileGame).where(ProfileGame.steam_app_id == 440)
    )

    assert stored_profile is not None
    assert stored_profile.display_name == "Cached Name"
    assert stored_profile.last_synced_at.replace(
        tzinfo=None
    ) == cached_sync_time.replace(tzinfo=None)
    assert ownership is not None
    assert ownership.playtime_minutes == 120
    assert database_session.scalar(
        select(func.count()).select_from(Game)
    ) == 1
    assert database_session.scalar(
        select(func.count()).select_from(ProfileGame)
    ) == 1
