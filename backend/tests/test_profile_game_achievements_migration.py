from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError


migration = import_module(
    "migrations.versions.c8d1f4a6e2b7_add_profile_game_achievements"
)


def test_achievement_migration_adds_table_and_budget_category_reversibly() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = MetaData()
        Table(
            "profile_games",
            metadata,
            Column("profile_id", Integer, nullable=False),
            Column("steam_app_id", BigInteger, nullable=False),
            PrimaryKeyConstraint("profile_id", "steam_app_id"),
        )
        Table(
            "steam_usage_events",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("category", String(20), nullable=False),
            Column("subject_digest", LargeBinary(32), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("expires_at", DateTime(timezone=True), nullable=False),
            CheckConstraint(
                "category IN ('session_create', 'provider_call', 'refresh')",
                name="ck_steam_usage_events_category",
            ),
        )
        metadata.create_all(connection)
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        assert "profile_game_achievements" in inspect(connection).get_table_names()
        connection.execute(
            text(
                "INSERT INTO steam_usage_events "
                "(category, subject_digest, created_at, expires_at) VALUES "
                "('achievement_call', x'00', '2026-10-19', '2026-10-20')"
            )
        )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        "INSERT INTO profile_game_achievements VALUES "
                        "(1, 2, 'ok', 5, 3, 10, '2026-10-19')"
                    )
                )

        migration.downgrade()
        assert "profile_game_achievements" not in inspect(connection).get_table_names()
        assert connection.execute(
            text("SELECT count(*) FROM steam_usage_events")
        ).scalar_one() == 0
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        "INSERT INTO steam_usage_events "
                        "(category, subject_digest, created_at, expires_at) "
                        "VALUES ('achievement_call', x'00', '2026-10-19', "
                        "'2026-10-20')"
                    )
                )
    engine.dispose()
