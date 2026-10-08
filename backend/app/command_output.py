"""Share the JSON output format used by operator commands."""

import json
from io import TextIOBase


def write_json_payload(payload: dict[str, object], output: TextIOBase) -> None:
    """Write one stable, human-readable JSON document and a newline."""
    json.dump(payload, output, indent=2, sort_keys=True)
    output.write("\n")
