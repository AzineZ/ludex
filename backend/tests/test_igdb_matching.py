import pytest
from app.igdb_client import IGDBResponseError, IGDBClient
from unittest.mock import Mock
from app.igdb_matching import (
    IGDBMatchResult,
    IGDBMatchStatus,
    normalize_external_game_matches,
    match_steam_app_ids,
)


def test_queries_igdb_using_the_steam_source_and_uid() -> None:
    client = Mock(spec=IGDBClient)
    client.query.return_value = [{"uid": "440", "game": 891}]

    results = match_steam_app_ids(client, [440])

    client.query.assert_called_once_with(
        "external_games",
        (
            "fields game,uid;"
            " where external_game_source = 1"
            ' & uid = ("440");'
            " limit 500;"
        ),
    )
    assert results == [
        IGDBMatchResult(
            steam_app_id=440,
            status=IGDBMatchStatus.MATCHED,
            igdb_game_id=891,
        )
    ]


def test_normalizes_matched_missing_and_ambiguous_games() -> None:
    results = normalize_external_game_matches(
        [440, 570, 730],
        [
            {"uid": "440", "game": 891},
            {"uid": "570", "game": 100},
            {"uid": "570", "game": 200},
            {"uid": "570", "game": 100},
        ],
    )

    assert results == [
        IGDBMatchResult(
            steam_app_id=440,
            status=IGDBMatchStatus.MATCHED,
            igdb_game_id=891,
        ),
        IGDBMatchResult(
            steam_app_id=570,
            status=IGDBMatchStatus.AMBIGUOUS,
            candidate_game_ids=(100, 200),
        ),
        IGDBMatchResult(
            steam_app_id=730,
            status=IGDBMatchStatus.MISSING,
        ),
    ]


@pytest.mark.parametrize("steam_app_id", [0, -1, True, "440"])
def test_rejects_invalid_steam_app_ids(steam_app_id: object) -> None:
    with pytest.raises(
        ValueError,
        match="Steam App IDs must be positive integers",
    ):
        normalize_external_game_matches(
            [steam_app_id], [])  # type: ignore[list-item]


@pytest.mark.parametrize(
    "external_game",
    [
        {},
        {"uid": 440, "game": 891},
        {"uid": "invalid", "game": 891},
    ],
)
def test_rejects_invalid_external_game_identifiers(
    external_game: dict[str, object],
) -> None:
    with pytest.raises(
        IGDBResponseError,
        match="invalid external-game identifier",
    ):
        normalize_external_game_matches([440], [external_game])


@pytest.mark.parametrize("igdb_game_id", [0, -1, True, "891"])
def test_rejects_invalid_igdb_game_references(
    igdb_game_id: object,
) -> None:
    with pytest.raises(
        IGDBResponseError,
        match="invalid game reference",
    ):
        normalize_external_game_matches(
            [440],
            [{"uid": "440", "game": igdb_game_id}],
        )


def test_treats_a_missing_game_reference_as_missing() -> None:
    assert normalize_external_game_matches(
        [440],
        [{"uid": "440"}],
    ) == [
        IGDBMatchResult(
            steam_app_id=440,
            status=IGDBMatchStatus.MISSING,
        )
    ]


def test_returns_one_result_for_duplicate_requested_ids() -> None:
    assert normalize_external_game_matches(
        [440, 440],
        [{"uid": "440", "game": 891}],
    ) == [
        IGDBMatchResult(
            steam_app_id=440,
            status=IGDBMatchStatus.MATCHED,
            igdb_game_id=891,
        )
    ]


def test_returns_immediately_for_an_empty_request() -> None:
    client = Mock(spec=IGDBClient)

    assert match_steam_app_ids(client, []) == []
    client.query.assert_not_called()


def test_splits_requests_at_the_batch_boundary() -> None:
    client = Mock(spec=IGDBClient)
    client.query.side_effect = [[], []]
    steam_app_ids = list(range(1, 102))

    results = match_steam_app_ids(client, steam_app_ids)

    assert len(results) == 101
    assert all(
        result.status is IGDBMatchStatus.MISSING
        for result in results
    )
    assert client.query.call_count == 2

    first_query = client.query.call_args_list[0].args[1]
    second_query = client.query.call_args_list[1].args[1]

    first_uid_list = ",".join(
        f'"{steam_app_id}"' for steam_app_id in range(1, 101)
    )

    assert f"uid = ({first_uid_list})" in first_query
    assert 'uid = ("101")' in second_query


def test_rejects_a_potentially_truncated_batch() -> None:
    client = Mock(spec=IGDBClient)
    client.query.return_value = [
        {"uid": "440", "game": 891}
    ] * 500

    with pytest.raises(
        IGDBResponseError,
        match="potentially truncated match batch",
    ):
        match_steam_app_ids(client, [440])
