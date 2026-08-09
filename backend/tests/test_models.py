from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
)


def test_game_defines_igdb_metadata_columns_and_constraints() -> None:
    table = Game.__table__

    expected_columns = {
        "igdb_game_id",
        "igdb_status",
        "igdb_last_attempted_at",
        "igdb_last_error",
        "igdb_enriched_at",
        "igdb_metadata_updated_at",
        "summary",
        "first_release_at",
        "cover_image_id",
        "time_to_beat_hastily_seconds",
        "time_to_beat_normally_seconds",
        "time_to_beat_completely_seconds",
        "time_to_beat_submission_count",
        "time_to_beat_updated_at",
    }

    assert expected_columns <= set(table.columns.keys())
    assert table.c.igdb_status.nullable is False
    assert str(table.c.igdb_status.server_default.arg) == "pending"

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_games_igdb_status" in constraint_names
    assert "ck_games_igdb_game_id_positive" in constraint_names
    assert "ck_games_time_submission_count_nonnegative" in constraint_names


def test_metadata_term_tables_define_identity_and_foreign_keys() -> None:
    term_table = IGDBMetadataTerm.__table__
    link_table = GameIGDBMetadataTerm.__table__

    unique_constraint_names = {
        constraint.name
        for constraint in term_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert (
        "uq_igdb_metadata_terms_kind_igdb_id"
        in unique_constraint_names
    )
    assert {
        column.name for column in link_table.primary_key.columns
    } == {"steam_app_id", "term_id"}

    foreign_keys = {
        foreign_key.parent.name: (
            foreign_key.target_fullname,
            foreign_key.ondelete,
        )
        for foreign_key in link_table.foreign_keys
    }

    assert foreign_keys == {
        "steam_app_id": ("games.steam_app_id", "CASCADE"),
        "term_id": ("igdb_metadata_terms.id", "CASCADE"),
    }


def test_game_metadata_relationship_round_trip() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        game = Game(
            steam_app_id=440,
            name="Team Fortress 2",
        )
        genre = IGDBMetadataTerm(
            kind="genre",
            igdb_id=5,
            name="Shooter",
        )
        game.metadata_term_links.append(
            GameIGDBMetadataTerm(term=genre)
        )

        session.add(game)
        session.commit()
        session.expire_all()

        saved_game = session.get(Game, 440)

        assert saved_game is not None
        assert saved_game.igdb_status == "pending"
        assert [
            (
                link.term.kind,
                link.term.igdb_id,
                link.term.name,
            )
            for link in saved_game.metadata_term_links
        ] == [("genre", 5, "Shooter")]

    engine.dispose()
