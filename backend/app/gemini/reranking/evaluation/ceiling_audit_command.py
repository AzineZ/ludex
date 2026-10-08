"""Operator command that measures ceiling payload sizes with no provider calls."""

from dataclasses import asdict

from app.database import SessionLocal
from app.gemini.reranking.evaluation.ceiling import (
    audit_cached_ceiling_payloads,
    audit_ceiling_fixture_payloads,
)
from app.gemini.reranking.evaluation.harness import print_summary


def main() -> int:
    with SessionLocal() as session:
        cached = audit_cached_ceiling_payloads(session)
    print_summary(
        {
            "fixed_fixture_maximum_request_bytes": (
                audit_ceiling_fixture_payloads()
            ),
            "cached_library_conservative_samples": [
                asdict(result) for result in cached
            ],
            "provider_calls": 0,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
