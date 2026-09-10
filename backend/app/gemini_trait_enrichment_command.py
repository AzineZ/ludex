"""Preserve the documented Gemini trait-preparation entry point."""

from app.gemini.traits.command import (
    main,
    run_gemini_trait_enrichment_command,
)

__all__ = ["main", "run_gemini_trait_enrichment_command"]


if __name__ == "__main__":
    main()
