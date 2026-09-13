from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    create_engine,
    inspect,
)


migration = import_module(
    "migrations.versions.7c4f1e2a9b06_add_gemini_provider_circuit"
)


def test_gemini_provider_circuit_migration_is_additive_and_reversible() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = MetaData()
        Table(
            "gemini_prompt_usage_events",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        metadata.create_all(connection)
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        schema = inspect(connection)
        columns = {
            column["name"]
            for column in schema.get_columns("gemini_prompt_usage_events")
        }
        assert "provider_limited_until" in columns
        assert "ix_gemini_prompt_usage_events_limited_until" in {
            index["name"]
            for index in schema.get_indexes("gemini_prompt_usage_events")
        }
        assert "ck_gemini_prompt_usage_events_provider_limit_order" in {
            constraint["name"]
            for constraint in schema.get_check_constraints(
                "gemini_prompt_usage_events"
            )
        }

        migration.downgrade()
        schema = inspect(connection)
        columns = {
            column["name"]
            for column in schema.get_columns("gemini_prompt_usage_events")
        }
        assert "provider_limited_until" not in columns
    engine.dispose()
