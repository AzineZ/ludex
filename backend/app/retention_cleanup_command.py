"""Preserve the documented profile-retention command entry point."""

from app.maintenance.command import main, run_retention_cleanup_command

__all__ = ["main", "run_retention_cleanup_command"]


if __name__ == "__main__":
    main()
