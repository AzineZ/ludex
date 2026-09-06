from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
)


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        yield session

    engine.dispose()

def _profile(profile_id: int) -> Profile:
    return Profile(
        id=profile_id,
        steam_id=f"7656119800000000{profile_id}",
        display_name=f"Player {profile_id}",
    )

def _ownership(profile: Profile, game: Game) -> ProfileGame:
    return ProfileGame(
        profile=profile,
        game=game,
        playtime_minutes=0,
    )

def _term(
    kind: str,
    igdb_id: int,
    name: str,
) -> GameIGDBMetadataTerm:
    return GameIGDBMetadataTerm(
        term=IGDBMetadataTerm(
            kind=kind,
            igdb_id=igdb_id,
            name=name,
        )
    )
