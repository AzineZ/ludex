from app.gemini.reranking.evaluation.candidate_formats import CatalogueGame, build_pool
from app.gemini.reranking.evaluation.large_pool_confirmation import (
    build_request,
    check_facts,
)
from app.gemini.reranking.reranker import build_rerank_user_prompt


def _game(index: int) -> CatalogueGame:
    return CatalogueGame(
        steam_app_id=1_000 + index,
        title=f"Real Game {index}",
        summary="Unused.",
        genres=("Adventure", "Indie"),
        themes=("Action",),
        keywords=("x",),
        game_modes=("Single player",),
        normal_completion_minutes=600,
    )


def test_requests_use_the_product_names_genres_format_with_scores() -> None:
    pool = build_pool(tuple(_game(index) for index in range(10)), 2_000)
    request = build_request(pool, {1_003: ("critic_score", 91)}, "Something")

    prompt = build_rerank_user_prompt(request)

    assert request.candidate_format == "names_genres"
    assert len(request.candidates) == 2_000
    assert '"critic_score":91' in prompt
    assert '"summary"' not in prompt and '"themes"' not in prompt


def test_fact_check_finds_cited_and_invented_scores() -> None:
    scores = {1: ("critic_score", 91)}

    cited = check_facts("Critics score it 91, a fitting pick.", 1, "Game", scores)
    invented = check_facts("Rated 88 by critics.", 1, "Game", scores)
    unscored = check_facts("About 12 hours long.", 2, "Game 2", scores)

    assert cited.cited_supplied_score and cited.unsupported_numbers == ()
    assert not invented.cited_supplied_score
    assert invented.unsupported_numbers == (88,)
    assert unscored.supplied_score is None
    assert unscored.unsupported_numbers == (12,)
