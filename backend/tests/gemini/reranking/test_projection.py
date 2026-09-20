import pytest

from app.gemini.reranking.contracts import RerankCandidate
from app.gemini.reranking.projection import (
    BALANCED_PROJECTION,
    COMPACT_PROJECTION,
    RICH_PROJECTION,
    project_rerank_candidates,
    select_product_projection,
)


def candidate(steam_app_id: int) -> RerankCandidate:
    return RerankCandidate(
        steam_app_id=steam_app_id,
        title=f"Game {steam_app_id}",
        summary="s" * 1200,
        genres=tuple(f"Genre {index}" for index in range(8)),
        themes=tuple(f"Theme {index}" for index in range(8)),
        keywords=tuple(f"Keyword {index}" for index in range(12)),
        game_modes=tuple(f"Mode {index}" for index in range(8)),
        profile_playtime_minutes=0,
        normal_completion_minutes=600,
    )


@pytest.mark.parametrize(
    ("candidate_count", "expected"),
    [
        (1, RICH_PROJECTION),
        (30, RICH_PROJECTION),
        (31, BALANCED_PROJECTION),
        (60, BALANCED_PROJECTION),
        (61, COMPACT_PROJECTION),
        (100, COMPACT_PROJECTION),
        (101, COMPACT_PROJECTION),
        (200, COMPACT_PROJECTION),
        (201, COMPACT_PROJECTION),
        (400, COMPACT_PROJECTION),
    ],
)
def test_product_projection_changes_only_at_approved_boundaries(
    candidate_count: int,
    expected,
) -> None:
    assert select_product_projection(candidate_count) is expected


@pytest.mark.parametrize("candidate_count", (0, 401))
def test_product_projection_rejects_stopped_pool_sizes(
    candidate_count: int,
) -> None:
    with pytest.raises(ValueError):
        select_product_projection(candidate_count)


@pytest.mark.parametrize(
    ("projection", "summary_length", "label_lengths"),
    [
        (RICH_PROJECTION, 1200, (8, 8, 12, 8)),
        (BALANCED_PROJECTION, 300, (4, 4, 6, 4)),
        (COMPACT_PROJECTION, 240, (3, 3, 4, 3)),
    ],
)
def test_projection_compacts_facts_without_selecting_or_reordering_games(
    projection,
    summary_length: int,
    label_lengths: tuple[int, int, int, int],
) -> None:
    source = tuple(candidate(identity) for identity in (5, 2, 9))

    projected = project_rerank_candidates(source, projection)

    assert tuple(item.steam_app_id for item in projected) == (5, 2, 9)
    assert len(projected) == len(source)
    assert all(len(item.summary or "") == summary_length for item in projected)
    assert all(
        (
            len(item.genres),
            len(item.themes),
            len(item.keywords),
            len(item.game_modes),
        )
        == label_lengths
        for item in projected
    )


def test_projection_marks_truncated_summary_at_a_word_boundary() -> None:
    source = candidate(1).model_copy(
        update={
            "summary": "complete " * 100
        }
    )

    projected = project_rerank_candidates((source,), COMPACT_PROJECTION)[0]

    assert projected.summary is not None
    assert len(projected.summary) <= COMPACT_PROJECTION.summary_characters
    assert projected.summary.endswith("complete…")
