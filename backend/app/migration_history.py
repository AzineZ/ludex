"""Resolve the repository's single authoritative Alembic head."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def get_single_alembic_head() -> str:
    """Return the current head, rejecting a branched migration history."""
    alembic_config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(alembic_config).get_heads()
    if len(heads) != 1:
        raise RuntimeError("The migration history does not have one head.")
    return heads[0]


def main() -> None:
    """Print the single head for owner-operated recovery scripts."""
    print(get_single_alembic_head())


if __name__ == "__main__":
    main()
