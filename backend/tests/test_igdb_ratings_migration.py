from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    BigInteger,
    Column,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError


migration = import_module("migrations.versions.b4c7e2d91f35_add_igdb_ratings")

RATING_COLUMNS = {
    "igdb_total_rating",
    "igdb_total_rating_count",
    "igdb_aggregated_rating",
    "igdb_aggregated_rating_count",
    "igdb_ratings_checked_at",
}


def test_igdb_ratings_migration_is_additive_constrained_and_reversible() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = MetaData()
        Table(
            "games",
            metadata,
            Column("steam_app_id", BigInteger, primary_key=True),
            Column("name", String(255), nullable=False),
        )
        metadata.create_all(connection)
        connection.execute(text("INSERT INTO games VALUES (1, 'Kept')"))
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        schema = inspect(connection)
        assert RATING_COLUMNS <= {
            column["name"] for column in schema.get_columns("games")
        }
        assert {
            "ck_games_igdb_total_rating_range",
            "ck_games_igdb_aggregated_rating_range",
            "ck_games_igdb_total_rating_count_nonnegative",
            "ck_games_igdb_aggregated_rating_count_nonnegative",
        } <= {
            constraint["name"]
            for constraint in schema.get_check_constraints("games")
        }
        assert connection.execute(
            text("SELECT name, igdb_total_rating FROM games")
        ).all() == [("Kept", None)]

        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text("UPDATE games SET igdb_total_rating = 101")
                )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text("UPDATE games SET igdb_aggregated_rating_count = -1")
                )

        migration.downgrade()
        schema = inspect(connection)
        assert not RATING_COLUMNS & {
            column["name"] for column in schema.get_columns("games")
        }
        assert connection.execute(text("SELECT name FROM games")).all() == [
            ("Kept",),
        ]
    engine.dispose()
