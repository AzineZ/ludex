from sqlalchemy.orm import Session

from app.gemini.prompt.confirmation import (
    PromptConfirmationSnapshot,
    PromptConfirmationState,
    build_prompt_confirmation_snapshot,
)
from app.gemini.prompt.coverage import get_prompt_trait_coverage
from app.gemini.prompt.reads import load_prompt_candidates
from app.gemini.prompt.scoring import (
    PromptCandidatePool,
    active_prompt_concepts,
    retrieve_prompt_candidates,
)
from app.gemini.prompt.validation import ValidatedPromptInterpretation


class PromptConfirmationStaleError(ValueError):
    """Indicate that the confirmed vocabulary or coverage snapshot changed."""


class PromptGuidedFallbackRequired(ValueError):
    """Indicate that no honest prompt-derived result can be generated."""


def retrieve_confirmed_prompt_candidates(
    session: Session,
    *,
    profile_id: int,
    validated: ValidatedPromptInterpretation,
    confirmed_snapshot: PromptConfirmationSnapshot,
    session_excluded_steam_app_ids: frozenset[int],
) -> PromptCandidatePool:
    """Revalidate one confirmation and rank cached owned games."""
    current_coverage = get_prompt_trait_coverage(
        session,
        profile_id=profile_id,
    )
    current_snapshot = build_prompt_confirmation_snapshot(
        validated,
        current_coverage,
    )
    if current_snapshot.fingerprint != confirmed_snapshot.fingerprint:
        raise PromptConfirmationStaleError(
            "The prompt confirmation changed and must be reviewed again."
        )
    if current_snapshot.state is PromptConfirmationState.GUIDED_ONLY:
        raise PromptGuidedFallbackRequired(
            "This request requires the guided recommendation flow."
        )

    concepts = active_prompt_concepts(validated, current_snapshot)
    candidates = load_prompt_candidates(
        session,
        profile_id=profile_id,
        concepts=concepts,
    )
    return retrieve_prompt_candidates(
        candidates,
        concepts=concepts,
        constraints=current_snapshot.constraints,
        session_excluded_steam_app_ids=session_excluded_steam_app_ids,
    )
