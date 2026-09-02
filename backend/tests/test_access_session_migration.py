from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select

from app.models import Profile
from migrations.versions import d52e7a91c304_add_steam_access_sessions as migration


def test_access_session_migration_is_additive_and_reversible() -> None:
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        Profile.__table__.create(connection)
        connection.execute(
            Profile.__table__.insert().values(
                steam_id="76561198000000000",
                display_name="Existing Player",
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()

        schema = inspect(connection)
        assert set(schema.get_table_names()) == {
            "profiles",
            "steam_access_sessions",
        }
        assert {column["name"] for column in schema.get_columns(
            "steam_access_sessions"
        )} == {
            "id",
            "token_digest",
            "profile_id",
            "created_at",
            "expires_at",
            "revoked_at",
        }
        assert {index["name"] for index in schema.get_indexes(
            "steam_access_sessions"
        )} == {
            "ix_steam_access_sessions_expires_at",
            "ix_steam_access_sessions_profile_id",
            "ix_steam_access_sessions_token_digest",
        }
        assert {constraint["name"] for constraint in schema.get_check_constraints(
            "steam_access_sessions"
        )} == {
            "ck_steam_access_sessions_digest_length",
            "ck_steam_access_sessions_expiration_order",
            "ck_steam_access_sessions_revocation_order",
        }
        assert connection.scalar(select(Profile.steam_id)) == (
            "76561198000000000"
        )

        migration.downgrade()

        assert inspect(connection).get_table_names() == ["profiles"]
        assert connection.scalar(select(Profile.steam_id)) == (
            "76561198000000000"
        )

    engine.dispose()
