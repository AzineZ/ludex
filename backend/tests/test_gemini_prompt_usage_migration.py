from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect


migration = import_module(
    "migrations.versions.3f2d8b7c1a90_add_gemini_prompt_usage"
)


def test_gemini_prompt_usage_migration_is_additive_and_reversible() -> None:
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        metadata = MetaData()
        Table(
            "steam_access_sessions",
            metadata,
            Column("id", Integer, primary_key=True),
        )
        metadata.create_all(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        schema = inspect(connection)
        assert set(schema.get_table_names()) == {
            "steam_access_sessions",
            "gemini_prompt_reservations",
            "gemini_prompt_usage_events",
        }
        assert {
            column["name"]
            for column in schema.get_columns("gemini_prompt_reservations")
        } == {
            "id",
            "access_session_id",
            "created_at",
            "expires_at",
            "completed_at",
        }
        assert {
            index["name"]
            for index in schema.get_indexes("gemini_prompt_reservations")
        } == {
            "ix_gemini_prompt_reservations_session_created_at",
            "uq_gemini_prompt_reservations_active_session",
        }
        assert {
            column["name"]
            for column in schema.get_columns("gemini_prompt_usage_events")
        } == {
            "id",
            "reservation_id",
            "created_at",
            "expires_at",
        }

        migration.downgrade()
        assert inspect(connection).get_table_names() == [
            "steam_access_sessions"
        ]

    engine.dispose()
