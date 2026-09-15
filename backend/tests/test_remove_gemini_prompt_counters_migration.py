from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect


prompt_usage_migration = import_module(
    "migrations.versions.3f2d8b7c1a90_add_gemini_prompt_usage"
)
provider_circuit_migration = import_module(
    "migrations.versions.7c4f1e2a9b06_add_gemini_provider_circuit"
)
remove_counters_migration = import_module(
    "migrations.versions.8e1a4c9d7b20_remove_gemini_prompt_counters"
)


def test_remove_gemini_prompt_counters_migration_is_reversible() -> None:
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        metadata = MetaData()
        Table(
            "steam_access_sessions",
            metadata,
            Column("id", Integer, primary_key=True),
        )
        metadata.create_all(connection)
        operations = Operations(MigrationContext.configure(connection))
        prompt_usage_migration.op = operations
        provider_circuit_migration.op = operations
        remove_counters_migration.op = operations

        prompt_usage_migration.upgrade()
        provider_circuit_migration.upgrade()
        remove_counters_migration.upgrade()

        assert inspect(connection).get_table_names() == [
            "steam_access_sessions"
        ]

        remove_counters_migration.downgrade()
        schema = inspect(connection)
        assert set(schema.get_table_names()) == {
            "steam_access_sessions",
            "gemini_prompt_reservations",
            "gemini_prompt_usage_events",
        }
        assert "provider_limited_until" in {
            column["name"]
            for column in schema.get_columns("gemini_prompt_usage_events")
        }

    engine.dispose()
