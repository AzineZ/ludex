from collections.abc import Generator
from contextlib import contextmanager
from io import StringIO
from json import loads
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

import app.gemini.traits.command as command
from app.gemini.client import GeminiClient, GeminiRateLimitError
from app.gemini.traits.batch import GameTraitRunResult
from app.gemini.traits.contracts import GameTraitFacts
from app.gemini.traits.planning import (
    GameTraitGenerationPlan,
    OwnedReadyGameTraitInventory,
)


@contextmanager
def _session_scope() -> Generator[Session, None, None]:
    yield MagicMock(spec=Session)


@contextmanager
def _client_scope() -> Generator[GeminiClient, None, None]:
    yield MagicMock(spec=GeminiClient)


@contextmanager
def _lock(acquired: bool = True) -> Generator[bool, None, None]:
    yield acquired


def _inventory(
    pending_ids: tuple[int, ...],
    current_ids: tuple[int, ...] = (),
) -> OwnedReadyGameTraitInventory:
    facts = GameTraitFacts(
        name="Example",
        summary=None,
        genres=(),
        themes=(),
        keywords=(),
        game_modes=(),
        time_to_beat=(),
        release_information=(),
    )
    return OwnedReadyGameTraitInventory(
        plans=tuple(
            GameTraitGenerationPlan(
                steam_app_id=steam_app_id,
                facts=facts,
                current_derivation_id=(
                    steam_app_id if steam_app_id in current_ids else None
                ),
                needs_generation=steam_app_id in pending_ids,
            )
            for steam_app_id in (*current_ids, *pending_ids)
        )
    )


def test_report_only_counts_primary_and_worst_case_requests(
    monkeypatch,
) -> None:
    output = StringIO()
    error_output = StringIO()
    inventory = _inventory(tuple(range(1, 12)), (100, 101))
    loader = MagicMock(return_value=inventory)
    client_factory = MagicMock()
    monkeypatch.setattr(
        command,
        "load_owned_ready_game_trait_inventory",
        loader,
    )

    exit_code = command.run_gemini_trait_enrichment_command(
        [],
        session_factory=_session_scope,
        client_factory=client_factory,
        output=output,
        error_output=error_output,
    )

    payload = loads(output.getvalue())
    assert exit_code == 0
    assert payload == {
        "configured_maximum_requests": 100,
        "configured_requests_per_minute": 10,
        "current_trait_game_count": 2,
        "mode": "report-only",
        "pending_trait_game_count": 11,
        "primary_request_count": 3,
        "ready_owned_game_count": 13,
        "worst_case_request_count": 10,
        "would_fit_primary_request_budget": True,
    }
    assert error_output.getvalue() == ""
    client_factory.assert_not_called()


def test_apply_reports_before_after_and_resumable_progress(
    monkeypatch,
) -> None:
    output = StringIO()
    error_output = StringIO()
    before = _inventory((1, 2, 3, 4, 5, 6))
    after = _inventory((6,), (1, 2, 3, 4, 5))
    monkeypatch.setattr(
        command,
        "load_owned_ready_game_trait_inventory",
        MagicMock(side_effect=[before, after]),
    )
    runner = MagicMock(
        return_value=GameTraitRunResult(
            generated_steam_app_ids=(1, 2, 3, 4, 5),
            skipped_steam_app_ids=(),
            failures=(),
            request_count=1,
            terminal_error=None,
        )
    )

    exit_code = command.run_gemini_trait_enrichment_command(
        ["--apply"],
        session_factory=_session_scope,
        client_factory=_client_scope,
        apply_lock=_lock,
        batch_runner=runner,
        output=output,
        error_output=error_output,
    )

    payload = loads(output.getvalue())
    assert exit_code == 0
    assert payload["mode"] == "applied"
    assert payload["generated_game_count"] == 5
    assert payload["request_count"] == 1
    assert payload["after"]["pending_trait_game_count"] == 1
    assert payload["resumable"] is True
    assert error_output.getvalue() == ""
    assert runner.call_args.args[2] == (1, 2, 3, 4, 5, 6)


def test_apply_reports_rate_limit_retry_after_without_secret_detail(
    monkeypatch,
) -> None:
    output = StringIO()
    error_output = StringIO()
    inventory = _inventory((1, 2))
    monkeypatch.setattr(
        command,
        "load_owned_ready_game_trait_inventory",
        MagicMock(side_effect=[inventory, inventory]),
    )
    rate_limit = GeminiRateLimitError(
        "Gemini rate-limited the API request.",
        retry_after_seconds=120,
    )
    runner = MagicMock(
        return_value=GameTraitRunResult(
            generated_steam_app_ids=(),
            skipped_steam_app_ids=(),
            failures=(),
            request_count=1,
            terminal_error=rate_limit,
        )
    )

    exit_code = command.run_gemini_trait_enrichment_command(
        ["--apply"],
        session_factory=_session_scope,
        client_factory=_client_scope,
        apply_lock=_lock,
        batch_runner=runner,
        output=output,
        error_output=error_output,
    )

    payload = loads(error_output.getvalue())
    assert exit_code == 1
    assert payload["mode"] == "incomplete"
    assert payload["terminal_code"] == "GeminiRateLimitError"
    assert payload["retry_after_seconds"] == 120
    assert "API" not in error_output.getvalue()
    assert output.getvalue() == ""


def test_apply_lock_blocks_before_client_creation(monkeypatch) -> None:
    output = StringIO()
    error_output = StringIO()
    monkeypatch.setattr(
        command,
        "load_owned_ready_game_trait_inventory",
        MagicMock(return_value=_inventory((1,))),
    )
    client_factory = MagicMock()

    exit_code = command.run_gemini_trait_enrichment_command(
        ["--apply"],
        session_factory=_session_scope,
        client_factory=client_factory,
        apply_lock=lambda: _lock(False),
        output=output,
        error_output=error_output,
    )

    assert exit_code == 2
    assert loads(error_output.getvalue())["mode"] == "blocked"
    assert output.getvalue() == ""
    client_factory.assert_not_called()
