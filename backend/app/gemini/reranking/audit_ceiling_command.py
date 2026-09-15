from dataclasses import asdict
from json import dumps

from app.database import SessionLocal
from app.gemini.reranking.ceiling_evaluation import (
    audit_cached_ceiling_payloads,
    audit_ceiling_fixture_payloads,
)


def main() -> int:
    with SessionLocal() as session:
        cached = audit_cached_ceiling_payloads(session)
    print(
        dumps(
            {
                "fixed_fixture_maximum_request_bytes": (
                    audit_ceiling_fixture_payloads()
                ),
                "cached_library_conservative_samples": [
                    asdict(result) for result in cached
                ],
                "provider_calls": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
