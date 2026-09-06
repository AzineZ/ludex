"""Preserve the documented IGDB enrichment command entry point."""

from app.integrations.igdb.command import main, run_igdb_enrichment_command

__all__ = ["main", "run_igdb_enrichment_command"]


if __name__ == "__main__":
    main()
