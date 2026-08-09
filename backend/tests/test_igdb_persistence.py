import pytest
from datetime import UTC, datetime

from app.igdb_metadata import IGDBGameMetadata, IGDBTimeToBeat, IGDBNamedEntity
from app.igdb_persistence import apply_ready_metadata, replace_metadata_terms, apply_unmatched_result
from app.models import Game, IGDBMetadataTerm, GameIGDBMetadataTerm
from app.database import Base
from app.igdb_matching import IGDBMatchStatus

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_applies_ready_metadata_to_shared_game() -> None:
    source_updated_at = datetime(2026, 8, 1, tzinfo=UTC)
    time_updated_at = datetime(2026, 8, 2, tzinfo=UTC)
    enriched_at = datetime(2026, 8, 8, tzinfo=UTC)

    metadata = IGDBGameMetadata(
        igdb_game_id=891,
        name="Team Fortress 2",
        summary="A class-based multiplayer shooter.",
        first_release_at=datetime(2007, 10, 10, tzinfo=UTC),
        cover_image_id="co6rzl",
        genres=(),
        themes=(),
        keywords=(),
        game_modes=(),
        updated_at=source_updated_at,
        time_to_beat=IGDBTimeToBeat(
            igdb_game_id=891,
            hastily_seconds=196200,
            normally_seconds=612000,
            completely_seconds=4338900,
            submission_count=8,
            updated_at=time_updated_at,
        ),
    )
    game = Game(
        steam_app_id=440,
        name="Team Fortress 2",
    )

    apply_ready_metadata(game, metadata, enriched_at)

    assert game.igdb_game_id == 891
    assert game.igdb_status == "ready"
    assert game.igdb_last_attempted_at == enriched_at
    assert game.igdb_last_error is None
    assert game.igdb_enriched_at == enriched_at
    assert game.igdb_metadata_updated_at == source_updated_at
    assert game.summary == metadata.summary
    assert game.first_release_at == metadata.first_release_at
    assert game.cover_image_id == "co6rzl"
    assert game.time_to_beat_hastily_seconds == 196200
    assert game.time_to_beat_normally_seconds == 612000
    assert game.time_to_beat_completely_seconds == 4338900
    assert game.time_to_beat_submission_count == 8
    assert game.time_to_beat_updated_at == time_updated_at


def test_replaces_metadata_terms_and_reuses_lookup_rows() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        stale_theme = IGDBMetadataTerm(
            kind="theme",
            igdb_id=1,
            name="Action",
        )
        reusable_genre = IGDBMetadataTerm(
            kind="genre",
            igdb_id=5,
            name="Old Shooter Name",
        )
        game = Game(
            steam_app_id=440,
            name="Team Fortress 2",
        )
        game.metadata_term_links.append(
            GameIGDBMetadataTerm(term=stale_theme)
        )

        session.add_all([game, reusable_genre])
        session.commit()

        metadata = IGDBGameMetadata(
            igdb_game_id=891,
            name="Team Fortress 2",
            summary=None,
            first_release_at=None,
            cover_image_id=None,
            genres=(IGDBNamedEntity(5, "Shooter"),),
            themes=(IGDBNamedEntity(27, "Comedy"),),
            keywords=(),
            game_modes=(),
            updated_at=datetime(2026, 8, 1, tzinfo=UTC),
        )

        replace_metadata_terms(session, game, metadata)
        session.commit()
        session.expire_all()

        saved_game = session.get(Game, 440)

        assert saved_game is not None
        assert {
            (
                link.term.kind,
                link.term.igdb_id,
                link.term.name,
            )
            for link in saved_game.metadata_term_links
        } == {
            ("genre", 5, "Shooter"),
            ("theme", 27, "Comedy"),
        }

    engine.dispose()


@pytest.mark.parametrize(
    "status",
    [
        IGDBMatchStatus.MISSING,
        IGDBMatchStatus.AMBIGUOUS,
    ],
)
def test_unmatched_result_clears_stale_factual_metadata(
    status: IGDBMatchStatus,
) -> None:
    attempted_at = datetime(2026, 8, 8, tzinfo=UTC)
    game = Game(
        steam_app_id=440,
        name="Team Fortress 2",
        igdb_game_id=891,
        igdb_status="ready",
        summary="Old summary",
        cover_image_id="old-cover",
        time_to_beat_normally_seconds=100,
    )
    game.metadata_term_links.append(
        GameIGDBMetadataTerm(
            term=IGDBMetadataTerm(
                kind="genre",
                igdb_id=5,
                name="Shooter",
            )
        )
    )

    apply_unmatched_result(game, status, attempted_at)

    assert game.name == "Team Fortress 2"
    assert game.igdb_status == status.value
    assert game.igdb_game_id is None
    assert game.igdb_last_attempted_at == attempted_at
    assert game.summary is None
    assert game.cover_image_id is None
    assert game.time_to_beat_normally_seconds is None
    assert game.metadata_term_links == []
