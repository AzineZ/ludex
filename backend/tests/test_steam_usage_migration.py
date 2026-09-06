from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


migration = import_module(
    "migrations.versions.6a2f8e4c91bd_add_steam_usage_events"
)


def test_steam_usage_migration_is_additive_and_reversible() -> None:
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        schema = inspect(connection)
        assert schema.get_table_names() == ["steam_usage_events"]
        assert {
            column["name"]
            for column in schema.get_columns("steam_usage_events")
        } == {
            "id",
            "category",
            "subject_digest",
            "created_at",
            "expires_at",
        }
        assert {
            index["name"]
            for index in schema.get_indexes("steam_usage_events")
        } == {
            "ix_steam_usage_events_category_created_at",
            "ix_steam_usage_events_expires_at",
            "ix_steam_usage_events_subject_created_at",
        }

        migration.downgrade()
        assert inspect(connection).get_table_names() == []

    engine.dispose()
