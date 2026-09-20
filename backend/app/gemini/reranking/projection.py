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
COMPACT_PROJECTION = RerankProjection("compact", 240, 3, 3, 4, 3)
MINIMAL_PROJECTION = RerankProjection("minimal", 0, 3, 3, 4, 3)


def _bounded_summary(summary: str | None, characters: int) -> str | None:
    if summary is None or characters == 0:
        return None
    if len(summary) <= characters:
        return summary

    prefix = summary[: characters - 1].rstrip()
    if prefix and not summary[characters - 1].isspace() and " " in prefix:
        prefix = prefix.rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{prefix or summary[: characters - 1]}…"


def select_product_projection(candidate_count: int) -> RerankProjection:
    """Select the approved factual projection for one complete product pool."""
    if not 1 <= candidate_count <= 400:
        raise ValueError("Product reranking requires 1 to 400 candidates.")
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
                    _bounded_summary(
                        candidate.summary,
                        projection.summary_characters,
                    )
                ),
                "genres": candidate.genres[: projection.genres],
                "themes": candidate.themes[: projection.themes],
                "keywords": candidate.keywords[: projection.keywords],
                "game_modes": candidate.game_modes[: projection.game_modes],
            }
        )
        for candidate in candidates
    )
