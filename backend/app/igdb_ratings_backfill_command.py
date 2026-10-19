"""Run the one-time IGDB ratings backfill for already-ready games."""

from app.integrations.igdb.ratings_command import (
    main,
    run_igdb_ratings_backfill_command,
)

__all__ = ["main", "run_igdb_ratings_backfill_command"]


if __name__ == "__main__":
    main()
