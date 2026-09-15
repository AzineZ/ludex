from dataclasses import dataclass

from app.gemini.reranking.contracts import RerankCandidate


@dataclass(frozen=True)
class RerankProjection:
    name: str
    summary_characters: int
    genres: int
    themes: int
    keywords: int
    game_modes: int


RICH_PROJECTION = RerankProjection("rich", 1200, 8, 8, 12, 8)
BALANCED_PROJECTION = RerankProjection("balanced", 300, 4, 4, 6, 4)
COMPACT_PROJECTION = RerankProjection("compact", 160, 3, 3, 4, 3)
MINIMAL_PROJECTION = RerankProjection("minimal", 0, 3, 3, 4, 3)


def select_product_projection(candidate_count: int) -> RerankProjection:
    """Select the approved factual projection for one complete product pool."""
    if not 1 <= candidate_count <= 200:
        raise ValueError("Product reranking requires 1 to 200 candidates.")
    if candidate_count <= 30:
        return RICH_PROJECTION
    if candidate_count <= 60:
        return BALANCED_PROJECTION
    return COMPACT_PROJECTION


def project_rerank_candidates(
    candidates: tuple[RerankCandidate, ...],
    projection: RerankProjection,
) -> tuple[RerankCandidate, ...]:
    """Apply only payload compaction; never select or remove a candidate."""
    return tuple(
        candidate.model_copy(
            update={
                "summary": (
                    candidate.summary[: projection.summary_characters]
                    if candidate.summary and projection.summary_characters
                    else None
                ),
                "genres": candidate.genres[: projection.genres],
                "themes": candidate.themes[: projection.themes],
                "keywords": candidate.keywords[: projection.keywords],
                "game_modes": candidate.game_modes[: projection.game_modes],
            }
        )
        for candidate in candidates
    )
