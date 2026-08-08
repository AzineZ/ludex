import pytest

from app.igdb_client import IGDBResponseError
from app.igdb_metadata import (
    IGDBNamedEntity,
    _normalize_named_entities,
)


def test_normalizes_named_entities_by_id() -> None:
    result = _normalize_named_entities(
        [
            {"id": 36, "name": "MOBA"},
            {"id": 15, "name": "Strategy"},
            {"id": 36, "name": "MOBA"},
        ],
        "genre",
    )

    assert result == (
        IGDBNamedEntity(igdb_id=15, name="Strategy"),
        IGDBNamedEntity(igdb_id=36, name="MOBA"),
    )


@pytest.mark.parametrize(
    "value",
    [
        "Shooter",
        [{}],
        [{"id": True, "name": "Shooter"}],
        [{"id": 5, "name": ""}],
        [
            {"id": 5, "name": "Shooter"},
            {"id": 5, "name": "Strategy"},
        ],
    ],
)
def test_rejects_invalid_named_entities(value: object) -> None:
    with pytest.raises(IGDBResponseError):
        _normalize_named_entities(value, "genre")
