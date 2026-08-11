from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

import app.igdb_enrichment as enrichment
from app.igdb_client import (
    IGDBClient,
    IGDBUnavailableError,
)
from app.igdb_matching import (
    IGDBMatchResult,
    IGDBMatchStatus,
)


def test_enriches_unique_games_in_paced_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    client = MagicMock(spec=IGDBClient)

    first_batch = list(range(1, 101))
    second_batch = [101]
    requested_ids = first_batch + second_batch + [1]

    first_results = [
        IGDBMatchResult(
            steam_app_id=steam_app_id,
            status=IGDBMatchStatus.MISSING,
        )
        for steam_app_id in first_batch
    ]
    second_results = [
        IGDBMatchResult(
            steam_app_id=101,
            status=IGDBMatchStatus.MISSING,
        )
    ]

    match_mock = MagicMock(
        side_effect=[first_results, second_results]
    )
    metadata_mock = MagicMock(side_effect=[[], []])
    persistence_mock = MagicMock()
    sleeper = MagicMock()

    first_attempt = datetime(2026, 8, 10, 12, tzinfo=UTC)
    second_attempt = datetime(2026, 8, 10, 12, 0, 1, tzinfo=UTC)
    clock = MagicMock(side_effect=[first_attempt, second_attempt])

    monkeypatch.setattr(
        enrichment,
        "match_steam_app_ids",
        match_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "fetch_game_metadata",
        metadata_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "persist_metadata_batch",
        persistence_mock,
    )

    results = enrichment.enrich_game_metadata(
        session,
        client,
        requested_ids,
        clock=clock,
        sleeper=sleeper,
    )

    assert results == first_results + second_results

    assert [
        call.args[1]
        for call in match_mock.call_args_list
    ] == [first_batch, second_batch]

    assert [
        call.args[1]
        for call in metadata_mock.call_args_list
    ] == [[], []]

    assert persistence_mock.call_count == 2
    assert persistence_mock.call_args_list[0].args == (
        session,
        first_results,
        [],
        first_attempt,
    )
    assert persistence_mock.call_args_list[1].args == (
        session,
        second_results,
        [],
        second_attempt,
    )

    sleeper.assert_called_once_with(
        enrichment.ENRICHMENT_BATCH_PAUSE_SECONDS
    )


def test_records_batch_failure_without_persisting_partial_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    client = MagicMock(spec=IGDBClient)
    attempted_at = datetime(2026, 8, 10, 12, tzinfo=UTC)

    match_mock = MagicMock(
        side_effect=IGDBUnavailableError(
            "IGDB is currently unavailable."
        )
    )
    metadata_mock = MagicMock()
    persistence_mock = MagicMock()
    failure_mock = MagicMock()
    sleeper = MagicMock()

    monkeypatch.setattr(
        enrichment,
        "match_steam_app_ids",
        match_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "fetch_game_metadata",
        metadata_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "persist_metadata_batch",
        persistence_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "record_metadata_failure",
        failure_mock,
    )

    with pytest.raises(
        IGDBUnavailableError,
        match="IGDB is currently unavailable.",
    ):
        enrichment.enrich_game_metadata(
            session,
            client,
            [440, 570],
            clock=lambda: attempted_at,
            sleeper=sleeper,
        )

    failure_mock.assert_called_once_with(
        session,
        [440, 570],
        attempted_at,
        "IGDB is currently unavailable.",
    )
    metadata_mock.assert_not_called()
    persistence_mock.assert_not_called()
    sleeper.assert_not_called()


def test_fetches_metadata_only_for_unique_matched_igdb_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    client = MagicMock(spec=IGDBClient)
    attempted_at = datetime(2026, 8, 10, 12, tzinfo=UTC)

    match_results = [
        IGDBMatchResult(
            steam_app_id=440,
            status=IGDBMatchStatus.MATCHED,
            igdb_game_id=891,
        ),
        IGDBMatchResult(
            steam_app_id=441,
            status=IGDBMatchStatus.MATCHED,
            igdb_game_id=891,
        ),
        IGDBMatchResult(
            steam_app_id=999,
            status=IGDBMatchStatus.AMBIGUOUS,
            candidate_game_ids=(10, 20),
        ),
    ]
    metadata_records = [MagicMock()]

    match_mock = MagicMock(return_value=match_results)
    metadata_mock = MagicMock(return_value=metadata_records)
    persistence_mock = MagicMock()

    monkeypatch.setattr(
        enrichment,
        "match_steam_app_ids",
        match_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "fetch_game_metadata",
        metadata_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "persist_metadata_batch",
        persistence_mock,
    )

    results = enrichment.enrich_game_metadata(
        session,
        client,
        [440, 441, 999],
        clock=lambda: attempted_at,
        sleeper=MagicMock(),
    )

    assert results == match_results
    metadata_mock.assert_called_once_with(client, [891])
    persistence_mock.assert_called_once_with(
        session,
        match_results,
        metadata_records,
        attempted_at,
    )


def test_records_failure_when_metadata_retrieval_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    client = MagicMock(spec=IGDBClient)
    attempted_at = datetime(2026, 8, 10, 12, tzinfo=UTC)

    match_results = [
        IGDBMatchResult(
            steam_app_id=440,
            status=IGDBMatchStatus.MATCHED,
            igdb_game_id=891,
        )
    ]

    monkeypatch.setattr(
        enrichment,
        "match_steam_app_ids",
        MagicMock(return_value=match_results),
    )
    monkeypatch.setattr(
        enrichment,
        "fetch_game_metadata",
        MagicMock(
            side_effect=IGDBUnavailableError(
                "IGDB metadata is unavailable."
            )
        ),
    )

    persistence_mock = MagicMock()
    failure_mock = MagicMock()

    monkeypatch.setattr(
        enrichment,
        "persist_metadata_batch",
        persistence_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "record_metadata_failure",
        failure_mock,
    )

    with pytest.raises(
        IGDBUnavailableError,
        match="IGDB metadata is unavailable.",
    ):
        enrichment.enrich_game_metadata(
            session,
            client,
            [440],
            clock=lambda: attempted_at,
            sleeper=MagicMock(),
        )

    failure_mock.assert_called_once_with(
        session,
        [440],
        attempted_at,
        "IGDB metadata is unavailable.",
    )
    persistence_mock.assert_not_called()


def test_rejects_incomplete_matching_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    client = MagicMock(spec=IGDBClient)

    incomplete_results = [
        IGDBMatchResult(
            steam_app_id=440,
            status=IGDBMatchStatus.MISSING,
        )
    ]

    monkeypatch.setattr(
        enrichment,
        "match_steam_app_ids",
        MagicMock(return_value=incomplete_results),
    )

    metadata_mock = MagicMock()
    persistence_mock = MagicMock()
    failure_mock = MagicMock()

    monkeypatch.setattr(
        enrichment,
        "fetch_game_metadata",
        metadata_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "persist_metadata_batch",
        persistence_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "record_metadata_failure",
        failure_mock,
    )

    with pytest.raises(
        ValueError,
        match="Matching must exactly cover the enrichment batch.",
    ):
        enrichment.enrich_game_metadata(
            session,
            client,
            [440, 570],
            clock=lambda: datetime(2026, 8, 10, tzinfo=UTC),
            sleeper=MagicMock(),
        )

    metadata_mock.assert_not_called()
    persistence_mock.assert_not_called()
    failure_mock.assert_not_called()


def test_rejects_naive_enrichment_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match_mock = MagicMock()

    monkeypatch.setattr(
        enrichment,
        "match_steam_app_ids",
        match_mock,
    )

    with pytest.raises(
        ValueError,
        match="The enrichment clock must be timezone-aware.",
    ):
        enrichment.enrich_game_metadata(
            MagicMock(spec=Session),
            MagicMock(spec=IGDBClient),
            [440],
            clock=lambda: datetime(2026, 8, 10),
            sleeper=MagicMock(),
        )

    match_mock.assert_not_called()


def test_empty_enrichment_request_spends_no_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match_mock = MagicMock()
    metadata_mock = MagicMock()
    persistence_mock = MagicMock()
    failure_mock = MagicMock()
    clock = MagicMock()
    sleeper = MagicMock()

    monkeypatch.setattr(
        enrichment,
        "match_steam_app_ids",
        match_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "fetch_game_metadata",
        metadata_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "persist_metadata_batch",
        persistence_mock,
    )
    monkeypatch.setattr(
        enrichment,
        "record_metadata_failure",
        failure_mock,
    )

    results = enrichment.enrich_game_metadata(
        MagicMock(spec=Session),
        MagicMock(spec=IGDBClient),
        [],
        clock=clock,
        sleeper=sleeper,
    )

    assert results == []
    match_mock.assert_not_called()
    metadata_mock.assert_not_called()
    persistence_mock.assert_not_called()
    failure_mock.assert_not_called()
    clock.assert_not_called()
    sleeper.assert_not_called()
