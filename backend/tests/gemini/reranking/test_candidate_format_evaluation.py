from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.gemini.reranking.evaluation.candidate_formats import (
    FORMAT_PROMPTS,
    SYNTHETIC_ID_START,
    CatalogueGame,
    TokenPacer,
    build_pool,
    plan_calls,
    run_format_evaluation,
    serialize_prompt,
)


def _game(index: int, **facts: tuple[str, ...]) -> CatalogueGame:
    return CatalogueGame(
        steam_app_id=1_000 + index,
        title=f"Real Game {index}",
        summary="A real game with a factual summary. " * 20,
        genres=facts.get("genres", ("Adventure",)),
        themes=facts.get("themes", ()),
        keywords=facts.get("keywords", ()),
        game_modes=("Single player",),
        normal_completion_minutes=600,
    )


CATALOGUE = tuple(
    _game(
        index,
        themes=(("Horror",) if index % 10 == 0 else ("Action",)),
        genres=(("Shooter",) if index % 3 == 0 else ("Adventure",)),
    )
    for index in range(626)
)
PROMPTS = {prompt.prompt_id: prompt for prompt in FORMAT_PROMPTS}


def test_pools_use_real_games_first_and_stable_synthetic_padding() -> None:
    small = build_pool(CATALOGUE, 400)
    large = build_pool(CATALOGUE, 2_000)

    assert not any(game.synthetic for game in small)
    assert sum(not game.synthetic for game in large) == 626
    assert sum(game.synthetic for game in large) == 1_374
    assert all(
        game.steam_app_id >= SYNTHETIC_ID_START
        for game in large
        if game.synthetic
    )
    assert len({game.steam_app_id for game in large}) == 2_000
    assert build_pool(CATALOGUE, 2_000) == large


def test_names_formats_are_far_smaller_than_the_current_projection() -> None:
    pool = build_pool(CATALOGUE, 400)
    sizes = {
        candidate_format: len(
            serialize_prompt(pool, candidate_format, "x").encode("utf-8")
        )
        for candidate_format in ("current", "names", "names_genres")
    }

    assert sizes["names"] < sizes["names_genres"] < sizes["current"]
    assert '"summary"' not in serialize_prompt(pool, "names", "x")


def test_plan_sends_28_calls_and_records_oversized_current_formats() -> None:
    plans = plan_calls(CATALOGUE)

    sendable = [plan for plan in plans if plan.sendable]
    too_large = [plan for plan in plans if not plan.sendable]
    assert len(sendable) == 28
    assert {(plan.candidate_format, plan.size) for plan in too_large} == {
        ("current", 1_000),
        ("current", 2_000),
    }


def test_factual_oracle_matches_each_prompt() -> None:
    horror = _game(1, themes=("Horror", "Survival"))
    rpg = _game(2, genres=("Role-playing (RPG)",), themes=("Drama",))
    brawler = _game(3, genres=("Hack and slash/Beat 'em up",), themes=("Action",))
    cozy = _game(4, genres=("Simulator",), themes=("Comedy",))

    assert PROMPTS["horror"].fits(horror) and not PROMPTS["horror"].fits(cozy)
    assert PROMPTS["story_rpg"].fits(rpg) and not PROMPTS["story_rpg"].fits(horror)
    assert PROMPTS["combat_not_scary"].fits(brawler)
    assert not PROMPTS["combat_not_scary"].fits(
        replace(brawler, themes=("Action", "Horror"))
    )
    assert PROMPTS["relaxing"].fits(cozy)
    assert not PROMPTS["relaxing"].fits(replace(cozy, themes=("Action",)))


def test_pacer_waits_when_the_token_budget_is_spent() -> None:
    now = [0.0]
    pauses: list[float] = []

    def sleeper(seconds: float) -> None:
        pauses.append(seconds)
        now[0] += seconds

    pacer = TokenPacer(
        requests_per_minute=10,
        tokens_per_minute=100,
        clock=lambda: now[0],
        sleeper=sleeper,
    )
    first = pacer.wait_for(60)
    now[0] = 5.0
    pacer.wait_for(60)

    assert pauses == [55.0]
    TokenPacer.settle(first, 10)
    assert first[1] == 10.0
    with pytest.raises(ValueError):
        pacer.wait_for(101)


class FakeGemini:
    """Pick the first two pool ids each time and report usage."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_structured_content_with_metadata(self, **kwargs: object):
        prompt = str(kwargs["user_prompt"])
        self.prompts.append(prompt)
        ids = [
            int(chunk.split(",")[0])
            for chunk in prompt.split('"steam_app_id":' if '"steam_app_id":' in prompt else '"id":')[1:3]
        ]
        return SimpleNamespace(
            content={
                "status": "ranked",
                "no_match_reason": None,
                "recommendations": [
                    {
                        "steam_app_id": steam_app_id,
                        "summary": "A game about exploring a strange place.",
                        "reasoning": "It fits what you asked for here.",
                    }
                    for steam_app_id in ids
                ],
            },
            input_tokens=1_000,
            output_tokens=100,
        )


def test_run_makes_exactly_the_planned_calls_and_scores_picks() -> None:
    client = FakeGemini()
    pacer = TokenPacer(
        tokens_per_minute=10_000_000,
        requests_per_minute=1_000,
        sleeper=lambda seconds: None,
    )

    report = run_format_evaluation(client, CATALOGUE, pacer=pacer)

    assert report.call_count == 28
    assert len(client.prompts) == 28
    assert len(report.results) == 36
    assert sum(result.status == "too_large" for result in report.results) == 8
    ranked = [result for result in report.results if result.status == "ranked"]
    assert len(ranked) == 28
    assert all(len(result.picks) == 2 for result in ranked)
    assert all(result.fit_share is not None for result in ranked)
