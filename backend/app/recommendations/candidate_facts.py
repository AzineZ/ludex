from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateFacts:
    """Store provider-independent facts used by recommendation rules."""

    steam_app_id: int
    owned_by_selected_profile: bool
    total_playtime_minutes: int
    normal_completion_seconds: int | None
    genre_ids: tuple[int, ...] | None
    theme_ids: tuple[int, ...] | None
    keyword_ids: tuple[int, ...] | None
    game_mode_ids: tuple[int, ...] | None
