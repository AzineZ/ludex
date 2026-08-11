import pytest
from datetime import UTC, datetime

from app.igdb_metadata import IGDBGameMetadata, IGDBTimeToBeat, IGDBNamedEntity
from app.igdb_persistence import (
    apply_ready_metadata,
    apply_unmatched_result,
    persist_metadata_batch,
    replace_metadata_terms,
    record_metadata_failure,
)
import app.igdb_persistence as igdb_persistence
from app.models import Game, IGDBMetadataTerm, GameIGDBMetadataTerm
from app.database import Base
from app.igdb_matching import (
    IGDBMatchResult,
    IGDBMatchStatus,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def _metadata(
    igdb_game_id: int,
    name: str,
) -> IGDBGameMetadata:
    """Create factual metadata for persistence tests."""
    return IGDBGameMetadata(
        igdb_game_id=igdb_game_id,
        name=name,
        summary=f"Summary for {name}.",
        first_release_at=None,
        cover_image_id=None,
        genres=(IGDBNamedEntity(5, "Shooter"),),
        themes=(),
        keywords=(),
        game_modes=(),
        updated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


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


def test_persists_complete_metadata_batch_atomically() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(
            [
                Game(steam_app_id=440, name="Team Fortress 2"),
                Game(steam_app_id=570, name="Dota 2"),
                Game(steam_app_id=999, name="Unknown Game"),
            ]
        )
        session.commit()

        attempted_at = datetime(2026, 8, 10, tzinfo=UTC)

        persist_metadata_batch(
            session,
            [
                IGDBMatchResult(
                    steam_app_id=440,
                    status=IGDBMatchStatus.MATCHED,
                    igdb_game_id=891,
                ),
                IGDBMatchResult(
                    steam_app_id=570,
                    status=IGDBMatchStatus.MATCHED,
                    igdb_game_id=2963,
                ),
                IGDBMatchResult(
                    steam_app_id=999,
                    status=IGDBMatchStatus.MISSING,
                ),
            ],
            [
                _metadata(891, "Team Fortress 2"),
                _metadata(2963, "Dota 2"),
            ],
            attempted_at,
        )

        session.expire_all()

        team_fortress = session.get(Game, 440)
        dota = session.get(Game, 570)
        unknown = session.get(Game, 999)
        terms = session.scalars(select(IGDBMetadataTerm)).all()

        assert team_fortress is not None
        assert team_fortress.igdb_status == "ready"
        assert team_fortress.igdb_game_id == 891
        assert team_fortress.summary == "Summary for Team Fortress 2."

        assert dota is not None
        assert dota.igdb_status == "ready"
        assert dota.igdb_game_id == 2963
        assert dota.summary == "Summary for Dota 2."

        assert unknown is not None
        assert unknown.igdb_status == "missing"
        assert unknown.igdb_game_id is None

        assert len(terms) == 1
        assert terms[0].kind == "genre"
        assert terms[0].igdb_id == 5
        assert terms[0].name == "Shooter"

    engine.dispose()


def test_rolls_back_entire_metadata_batch_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(
            [
                Game(steam_app_id=440, name="Team Fortress 2"),
                Game(steam_app_id=570, name="Dota 2"),
            ]
        )
        session.commit()

        original_replace = igdb_persistence.replace_metadata_terms

        def fail_on_second_game(
            database_session: Session,
            game: Game,
            metadata: IGDBGameMetadata,
        ) -> None:
            """Simulate a persistence failure after the first game."""
            original_replace(database_session, game, metadata)

            if game.steam_app_id == 570:
                raise RuntimeError("Forced persistence failure.")

        monkeypatch.setattr(
            igdb_persistence,
            "replace_metadata_terms",
            fail_on_second_game,
        )

        with pytest.raises(
            RuntimeError,
            match="Forced persistence failure.",
        ):
            persist_metadata_batch(
                session,
                [
                    IGDBMatchResult(
                        steam_app_id=440,
                        status=IGDBMatchStatus.MATCHED,
                        igdb_game_id=891,
                    ),
                    IGDBMatchResult(
                        steam_app_id=570,
                        status=IGDBMatchStatus.MATCHED,
                        igdb_game_id=2963,
                    ),
                ],
                [
                    _metadata(891, "Team Fortress 2"),
                    _metadata(2963, "Dota 2"),
                ],
                datetime(2026, 8, 10, tzinfo=UTC),
            )

        session.expire_all()

        team_fortress = session.get(Game, 440)
        dota = session.get(Game, 570)
        terms = session.scalars(select(IGDBMetadataTerm)).all()

        assert team_fortress is not None
        assert team_fortress.igdb_status == "pending"
        assert team_fortress.igdb_game_id is None

        assert dota is not None
        assert dota.igdb_status == "pending"
        assert dota.igdb_game_id is None

        assert terms == []

    engine.dispose()


def test_rejects_incomplete_metadata_batch_without_changing_cache() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        game = Game(
            steam_app_id=440,
            name="Team Fortress 2",
            igdb_game_id=891,
            igdb_status="ready",
            summary="Existing cached summary.",
        )
        session.add(game)
        session.commit()

        with pytest.raises(
            ValueError,
            match="Metadata must exactly cover every matched IGDB game.",
        ):
            persist_metadata_batch(
                session,
                [
                    IGDBMatchResult(
                        steam_app_id=440,
                        status=IGDBMatchStatus.MATCHED,
                        igdb_game_id=891,
                    )
                ],
                [],
                datetime(2026, 8, 10, tzinfo=UTC),
            )

        session.expire_all()
        saved_game = session.get(Game, 440)

        assert saved_game is not None
        assert saved_game.igdb_status == "ready"
        assert saved_game.igdb_game_id == 891
        assert saved_game.summary == "Existing cached summary."

    engine.dispose()


def test_records_failure_without_changing_cached_metadata() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    enriched_at = datetime(2026, 8, 1, tzinfo=UTC)
    attempted_at = datetime(2026, 8, 10, tzinfo=UTC)

    with Session(engine) as session:
        game = Game(
            steam_app_id=440,
            name="Team Fortress 2",
            igdb_game_id=891,
            igdb_status="ready",
            igdb_enriched_at=enriched_at,
            summary="Existing cached summary.",
            cover_image_id="existing-cover",
            time_to_beat_normally_seconds=612000,
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

        session.add(game)
        session.commit()

        record_metadata_failure(
            session,
            [440, 440],
            attempted_at,
            "IGDB is temporarily unavailable.",
        )

        session.expire_all()
        saved_game = session.get(Game, 440)

        assert saved_game is not None
        assert saved_game.igdb_last_attempted_at is not None
        assert (
            saved_game.igdb_last_attempted_at.replace(tzinfo=UTC)
            == attempted_at
        )
        assert saved_game.igdb_last_error == (
            "IGDB is temporarily unavailable."
        )

        assert saved_game.igdb_status == "ready"
        assert saved_game.igdb_game_id == 891
        assert saved_game.igdb_enriched_at is not None
        assert saved_game.igdb_enriched_at.replace(tzinfo=UTC) == enriched_at
        assert saved_game.summary == "Existing cached summary."
        assert saved_game.cover_image_id == "existing-cover"
        assert saved_game.time_to_beat_normally_seconds == 612000
        assert [
            (link.term.kind, link.term.igdb_id, link.term.name)
            for link in saved_game.metadata_term_links
        ] == [("genre", 5, "Shooter")]

    engine.dispose()
