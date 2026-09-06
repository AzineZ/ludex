import pytest
from datetime import UTC, datetime
from app.integrations.igdb.client import IGDBResponseError, IGDBClient
from unittest.mock import Mock
from app.integrations.igdb.metadata import (
    IGDBNamedEntity,
    _normalize_named_entities,
    IGDBGameMetadata,
    normalize_game_metadata,
    IGDBTimeToBeat,
    normalize_time_to_beat,
    fetch_game_metadata,
)


def _game_record(igdb_game_id: int) -> dict[str, object]:
    return {
        "id": igdb_game_id,
        "name": f"Game {igdb_game_id}",
        "updated_at": 60,
    }


def _time_record(igdb_game_id: int) -> dict[str, object]:
    return {
        "game_id": igdb_game_id,
        "count": 1,
        "updated_at": 60,
    }


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


def test_normalizes_a_complete_game_record() -> None:
    result = normalize_game_metadata(
        {
            "id": 891,
            "name": "Team Fortress 2",
            "summary": "A class-based multiplayer shooter.",
            "first_release_date": 0,
            "updated_at": 60,
            "cover": {"image_id": "co6rzl"},
            "genres": [{"id": 5, "name": "Shooter"}],
            "themes": [{"id": 1, "name": "Action"}],
            "keywords": [{"id": 546, "name": "pvp"}],
            "game_modes": [{"id": 2, "name": "Multiplayer"}],
        }
    )

    assert result == IGDBGameMetadata(
        igdb_game_id=891,
        name="Team Fortress 2",
        summary="A class-based multiplayer shooter.",
        first_release_at=datetime(1970, 1, 1, tzinfo=UTC),
        cover_image_id="co6rzl",
        genres=(IGDBNamedEntity(5, "Shooter"),),
        themes=(IGDBNamedEntity(1, "Action"),),
        keywords=(IGDBNamedEntity(546, "pvp"),),
        game_modes=(IGDBNamedEntity(2, "Multiplayer"),),
        updated_at=datetime(1970, 1, 1, 0, 1, tzinfo=UTC),
    )


def test_normalizes_missing_optional_game_fields() -> None:
    result = normalize_game_metadata(
        {
            "id": 100,
            "name": "Minimal Game",
            "summary": "   ",
            "updated_at": 60,
            "cover": {},
        }
    )

    assert result == IGDBGameMetadata(
        igdb_game_id=100,
        name="Minimal Game",
        summary=None,
        first_release_at=None,
        cover_image_id=None,
        genres=(),
        themes=(),
        keywords=(),
        game_modes=(),
        updated_at=datetime(1970, 1, 1, 0, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"id": 0},
        {"id": True},
        {"name": ""},
        {"summary": 123},
        {"updated_at": None},
        {"updated_at": True},
        {"cover": "invalid"},
        {"cover": {"image_id": 123}},
    ],
)
def test_rejects_invalid_game_records(
    invalid_fields: dict[str, object],
) -> None:
    game: dict[str, object] = {
        "id": 100,
        "name": "Valid Game",
        "updated_at": 60,
    }
    game.update(invalid_fields)

    with pytest.raises(IGDBResponseError):
        normalize_game_metadata(game)


def test_normalizes_time_to_beat_record() -> None:
    result = normalize_time_to_beat(
        {
            "game_id": 891,
            "hastily": 196200,
            "normally": 612000,
            "completely": 4338900,
            "count": 8,
            "updated_at": 60,
        }
    )

    assert result == IGDBTimeToBeat(
        igdb_game_id=891,
        hastily_seconds=196200,
        normally_seconds=612000,
        completely_seconds=4338900,
        submission_count=8,
        updated_at=datetime(1970, 1, 1, 0, 1, tzinfo=UTC),
    )


def test_normalizes_missing_optional_times() -> None:
    result = normalize_time_to_beat(
        {
            "game_id": 100,
            "count": 0,
            "updated_at": 60,
        }
    )

    assert result == IGDBTimeToBeat(
        igdb_game_id=100,
        hastily_seconds=None,
        normally_seconds=None,
        completely_seconds=None,
        submission_count=0,
        updated_at=datetime(1970, 1, 1, 0, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"game_id": 0},
        {"game_id": True},
        {"count": -1},
        {"count": True},
        {"updated_at": None},
        {"hastily": -1},
        {"normally": "60"},
        {"completely": True},
    ],
)
def test_rejects_invalid_time_to_beat_records(
    invalid_fields: dict[str, object],
) -> None:
    record: dict[str, object] = {
        "game_id": 100,
        "count": 5,
        "updated_at": 60,
    }
    record.update(invalid_fields)

    with pytest.raises(IGDBResponseError):
        normalize_time_to_beat(record)


def test_fetches_and_merges_game_metadata() -> None:
    client = Mock(spec=IGDBClient)
    client.query.side_effect = [
        [
            {
                "id": 891,
                "name": "Team Fortress 2",
                "updated_at": 60,
            }
        ],
        [
            {
                "game_id": 891,
                "normally": 612000,
                "count": 8,
                "updated_at": 120,
            }
        ],
    ]

    results = fetch_game_metadata(client, [891])

    assert len(results) == 1
    assert results[0].igdb_game_id == 891
    assert results[0].time_to_beat == IGDBTimeToBeat(
        igdb_game_id=891,
        hastily_seconds=None,
        normally_seconds=612000,
        completely_seconds=None,
        submission_count=8,
        updated_at=datetime(1970, 1, 1, 0, 2, tzinfo=UTC),
    )
    assert client.query.call_count == 2


def test_fetch_metadata_returns_immediately_for_empty_input() -> None:
    client = Mock(spec=IGDBClient)

    assert fetch_game_metadata(client, []) == []
    client.query.assert_not_called()


def test_fetch_metadata_splits_requests_at_batch_boundary() -> None:
    client = Mock(spec=IGDBClient)
    client.query.side_effect = [
        [_game_record(game_id) for game_id in range(1, 101)],
        [],
        [_game_record(101)],
        [],
    ]

    results = fetch_game_metadata(client, list(range(1, 102)))

    assert [result.igdb_game_id for result in results] == list(
        range(1, 102)
    )
    assert client.query.call_count == 4

    first_game_query = client.query.call_args_list[0].args[1]
    first_time_query = client.query.call_args_list[1].args[1]
    second_game_query = client.query.call_args_list[2].args[1]
    second_time_query = client.query.call_args_list[3].args[1]

    assert "where id = (1,2,3" in first_game_query
    assert "where game_id = (1,2,3" in first_time_query
    assert "where id = (101)" in second_game_query
    assert "where game_id = (101)" in second_time_query


def test_rejects_missing_requested_game_metadata() -> None:
    client = Mock(spec=IGDBClient)
    client.query.return_value = []

    with pytest.raises(
        IGDBResponseError,
        match="omitted requested game metadata",
    ):
        fetch_game_metadata(client, [891])


def test_rejects_duplicate_game_metadata() -> None:
    client = Mock(spec=IGDBClient)
    game = _game_record(891)
    client.query.return_value = [game, game]

    with pytest.raises(
        IGDBResponseError,
        match="duplicate game metadata",
    ):
        fetch_game_metadata(client, [891])


def test_rejects_duplicate_time_to_beat_data() -> None:
    client = Mock(spec=IGDBClient)
    time_record = _time_record(891)
    client.query.side_effect = [
        [_game_record(891)],
        [time_record, time_record],
    ]

    with pytest.raises(
        IGDBResponseError,
        match="duplicate time-to-beat data",
    ):
        fetch_game_metadata(client, [891])


def test_rejects_truncated_metadata_batch() -> None:
    client = Mock(spec=IGDBClient)
    client.query.return_value = [_game_record(891)] * 500

    with pytest.raises(
        IGDBResponseError,
        match="potentially truncated metadata batch",
    ):
        fetch_game_metadata(client, [891])


def test_rejects_truncated_time_to_beat_batch() -> None:
    client = Mock(spec=IGDBClient)
    client.query.side_effect = [
        [_game_record(891)],
        [_time_record(891)] * 500,
    ]

    with pytest.raises(
        IGDBResponseError,
        match="potentially truncated time-to-beat batch",
    ):
        fetch_game_metadata(client, [891])
