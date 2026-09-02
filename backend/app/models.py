from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    ForeignKeyConstraint,
    Numeric,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Profile(Base):
    """Represent a locally saved Steam user profile."""

    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    steam_id: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(100))
    profile_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    owned_games: Mapped[list[ProfileGame]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    access_sessions: Mapped[list[SteamAccessSession]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SteamAccessSession(Base):
    """Authorize one browser to access one cached Steam profile."""

    __tablename__ = "steam_access_sessions"
    __table_args__ = (
        CheckConstraint(
            "length(token_digest) = 32",
            name="ck_steam_access_sessions_digest_length",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_steam_access_sessions_expiration_order",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_steam_access_sessions_revocation_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    token_digest: Mapped[bytes] = mapped_column(
        LargeBinary(32),
        unique=True,
        index=True,
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    profile: Mapped[Profile] = relationship(
        back_populates="access_sessions",
    )


class Game(Base):
    """Represent Steam game metadata shared across local profiles."""

    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint(
            "igdb_status IN "
            "('pending', 'ready', 'missing', 'ambiguous')",
            name="ck_games_igdb_status",
        ),
        CheckConstraint(
            "igdb_game_id IS NULL OR igdb_game_id > 0",
            name="ck_games_igdb_game_id_positive",
        ),
        CheckConstraint(
            "time_to_beat_hastily_seconds IS NULL "
            "OR time_to_beat_hastily_seconds >= 0",
            name="ck_games_hastily_seconds_nonnegative",
        ),
        CheckConstraint(
            "time_to_beat_normally_seconds IS NULL "
            "OR time_to_beat_normally_seconds >= 0",
            name="ck_games_normally_seconds_nonnegative",
        ),
        CheckConstraint(
            "time_to_beat_completely_seconds IS NULL "
            "OR time_to_beat_completely_seconds >= 0",
            name="ck_games_completely_seconds_nonnegative",
        ),
        CheckConstraint(
            "time_to_beat_submission_count IS NULL "
            "OR time_to_beat_submission_count >= 0",
            name="ck_games_time_submission_count_nonnegative",
        ),
    )
    steam_app_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )
    name: Mapped[str] = mapped_column(String(255))
    icon_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    igdb_game_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    igdb_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        index=True,
    )
    igdb_last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    igdb_last_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    igdb_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    igdb_metadata_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    first_release_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cover_image_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    time_to_beat_hastily_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    time_to_beat_normally_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    time_to_beat_completely_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    time_to_beat_submission_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    time_to_beat_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    profile_games: Mapped[list[ProfileGame]] = relationship(
        back_populates="game",
        passive_deletes=True,
    )
    metadata_term_links: Mapped[list[GameIGDBMetadataTerm]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProfileGame(Base):
    """Represent a profile's ownership and playtime for one game."""

    __tablename__ = "profile_games"

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    steam_app_id: Mapped[int] = mapped_column(
        ForeignKey("games.steam_app_id", ondelete="CASCADE"),
        primary_key=True,
    )
    playtime_minutes: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
    )
    recent_playtime_minutes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    last_played_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    profile: Mapped[Profile] = relationship(
        back_populates="owned_games",
    )
    game: Mapped[Game] = relationship(
        back_populates="profile_games",
    )


class IGDBMetadataTerm(Base):
    """Represent a reusable named IGDB metadata value."""

    __tablename__ = "igdb_metadata_terms"
    __table_args__ = (
        UniqueConstraint(
            "kind",
            "igdb_id",
            name="uq_igdb_metadata_terms_kind_igdb_id",
        ),
        CheckConstraint(
            "kind IN ('genre', 'theme', 'keyword', 'game_mode')",
            name="ck_igdb_metadata_terms_kind",
        ),
        CheckConstraint(
            "igdb_id > 0",
            name="ck_igdb_metadata_terms_igdb_id_positive",
        ),
        Index(
            "ix_igdb_metadata_terms_kind_name",
            "kind",
            "name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    igdb_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(255))

    game_links: Mapped[list[GameIGDBMetadataTerm]] = relationship(
        back_populates="term",
        passive_deletes=True,
    )


class GameIGDBMetadataTerm(Base):
    """Associate one shared Steam game with an IGDB metadata term."""

    __tablename__ = "game_igdb_metadata_terms"
    __table_args__ = (
        Index(
            "ix_game_igdb_metadata_terms_term_id",
            "term_id",
        ),
    )

    steam_app_id: Mapped[int] = mapped_column(
        ForeignKey("games.steam_app_id", ondelete="CASCADE"),
        primary_key=True,
    )
    term_id: Mapped[int] = mapped_column(
        ForeignKey("igdb_metadata_terms.id", ondelete="CASCADE"),
        primary_key=True,
    )

    game: Mapped[Game] = relationship(
        back_populates="metadata_term_links",
    )
    term: Mapped[IGDBMetadataTerm] = relationship(
        back_populates="game_links",
    )


class GameTraitDerivation(Base):
    """Represent one immutable successful game-trait interpretation."""

    __tablename__ = "game_trait_derivations"
    __table_args__ = (
        UniqueConstraint(
            "steam_app_id",
            "id",
            name="uq_game_trait_derivations_game_id",
        ),
        CheckConstraint(
            "length(facts_fingerprint) = 64",
            name="ck_game_trait_derivations_fingerprint_length",
        ),
        CheckConstraint(
            "(story_focus_value IS NULL "
            "AND story_focus_confidence = 0) OR "
            "(story_focus_value IS NOT NULL "
            "AND story_focus_value BETWEEN 0 AND 5 "
            "AND story_focus_confidence BETWEEN 0.30 AND 1)",
            name="ck_game_trait_derivations_story_focus_state",
        ),
        CheckConstraint(
            "(combat_intensity_value IS NULL "
            "AND combat_intensity_confidence = 0) OR "
            "(combat_intensity_value IS NOT NULL "
            "AND combat_intensity_value BETWEEN 0 AND 5 "
            "AND combat_intensity_confidence BETWEEN 0.30 AND 1)",
            name="ck_game_trait_derivations_combat_intensity_state",
        ),
        CheckConstraint(
            "(difficulty_value IS NULL "
            "AND difficulty_confidence = 0) OR "
            "(difficulty_value IS NOT NULL "
            "AND difficulty_value BETWEEN 0 AND 5 "
            "AND difficulty_confidence BETWEEN 0.30 AND 1)",
            name="ck_game_trait_derivations_difficulty_state",
        ),
        CheckConstraint(
            "(pacing_value IS NULL "
            "AND pacing_confidence = 0) OR "
            "(pacing_value IS NOT NULL "
            "AND pacing_value BETWEEN 0 AND 5 "
            "AND pacing_confidence BETWEEN 0.30 AND 1)",
            name="ck_game_trait_derivations_pacing_state",
        ),
        CheckConstraint(
            "(session_friendliness_value IS NULL "
            "AND session_friendliness_confidence = 0) OR "
            "(session_friendliness_value IS NOT NULL "
            "AND session_friendliness_value BETWEEN 0 AND 5 "
            "AND session_friendliness_confidence BETWEEN 0.30 AND 1)",
            name=(
                "ck_game_trait_derivations_"
                "session_friendliness_state"
            ),
        ),
        CheckConstraint(
            "(exploration_focus_value IS NULL "
            "AND exploration_focus_confidence = 0) OR "
            "(exploration_focus_value IS NOT NULL "
            "AND exploration_focus_value BETWEEN 0 AND 5 "
            "AND exploration_focus_confidence BETWEEN 0.30 AND 1)",
            name="ck_game_trait_derivations_exploration_focus_state",
        ),
        Index(
            "ix_game_trait_derivations_game_derived_at",
            "steam_app_id",
            "derived_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    steam_app_id: Mapped[int] = mapped_column(
        ForeignKey("games.steam_app_id", ondelete="CASCADE"),
    )
    schema_version: Mapped[str] = mapped_column(String(50))
    derivation_version: Mapped[str] = mapped_column(String(50))
    model_id: Mapped[str] = mapped_column(String(100))
    facts_fingerprint: Mapped[str] = mapped_column(String(64))
    derived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )

    story_focus_value: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    story_focus_confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
    )
    combat_intensity_value: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    combat_intensity_confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
    )
    difficulty_value: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    difficulty_confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
    )
    pacing_value: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    pacing_confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
    )
    session_friendliness_value: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    session_friendliness_confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
    )
    exploration_focus_value: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    exploration_focus_confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
    )


class GameCurrentTraitDerivation(Base):
    """Point one shared game to its current successful derivation."""

    __tablename__ = "game_current_trait_derivations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["steam_app_id"],
            ["games.steam_app_id"],
            ondelete="CASCADE",
            name="fk_current_trait_derivations_game",
        ),
        ForeignKeyConstraint(
            ["steam_app_id", "derivation_id"],
            [
                "game_trait_derivations.steam_app_id",
                "game_trait_derivations.id",
            ],
            ondelete="CASCADE",
            name="fk_current_trait_derivations_matching_derivation",
        ),
        UniqueConstraint(
            "derivation_id",
            name="uq_current_trait_derivations_derivation_id",
        ),
    )

    steam_app_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    derivation_id: Mapped[int] = mapped_column(Integer)


class GameTraitMood(Base):
    """Represent one supported mood belonging to a trait derivation."""

    __tablename__ = "game_trait_moods"
    __table_args__ = (
        CheckConstraint(
            "label IN "
            "('relaxing', 'tense', 'emotional', 'humorous', 'dark')",
            name="ck_game_trait_moods_label",
        ),
        CheckConstraint(
            "confidence BETWEEN 0.30 AND 1",
            name="ck_game_trait_moods_confidence",
        ),
    )

    derivation_id: Mapped[int] = mapped_column(
        ForeignKey("game_trait_derivations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    label: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
    )


class GameTraitEvidence(Base):
    """Represent one verified citation supporting a trait or mood."""

    __tablename__ = "game_trait_evidence"
    __table_args__ = (
        UniqueConstraint(
            "derivation_id",
            "target_kind",
            "target_name",
            "position",
            name="uq_game_trait_evidence_target_position",
        ),
        CheckConstraint(
            "("
            "target_kind = 'trait' AND target_name IN ("
            "'story_focus', "
            "'combat_intensity', "
            "'difficulty', "
            "'pacing', "
            "'session_friendliness', "
            "'exploration_focus'"
            ")"
            ") OR ("
            "target_kind = 'mood' AND target_name IN ("
            "'relaxing', "
            "'tense', "
            "'emotional', "
            "'humorous', "
            "'dark'"
            ")"
            ")",
            name="ck_game_trait_evidence_target",
        ),
        CheckConstraint(
            "source_field IN ("
            "'summary', "
            "'genre', "
            "'theme', "
            "'keyword', "
            "'game_mode', "
            "'time_to_beat', "
            "'release_information'"
            ")",
            name="ck_game_trait_evidence_source_field",
        ),
        CheckConstraint(
            "position BETWEEN 0 AND 2",
            name="ck_game_trait_evidence_position",
        ),
        CheckConstraint(
            "length(source_value) BETWEEN 1 AND 200",
            name="ck_game_trait_evidence_source_value_length",
        ),
        CheckConstraint(
            "length(reason) BETWEEN 1 AND 200",
            name="ck_game_trait_evidence_reason_length",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    derivation_id: Mapped[int] = mapped_column(
        ForeignKey("game_trait_derivations.id", ondelete="CASCADE"),
        index=True,
    )
    target_kind: Mapped[str] = mapped_column(String(10))
    target_name: Mapped[str] = mapped_column(String(30))
    position: Mapped[int] = mapped_column(Integer)
    source_field: Mapped[str] = mapped_column(String(30))
    source_value: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(200))


class GameTraitAttempt(Base):
    """Represent one successful or failed Gemini classification call."""

    __tablename__ = "game_trait_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["steam_app_id", "derivation_id"],
            [
                "game_trait_derivations.steam_app_id",
                "game_trait_derivations.id",
            ],
            ondelete="CASCADE",
            name="fk_game_trait_attempts_matching_derivation",
        ),
        UniqueConstraint(
            "operation_id",
            "attempt_number",
            name="uq_game_trait_attempts_operation_attempt",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_game_trait_attempts_attempt_number",
        ),
        CheckConstraint(
            "outcome IN ("
            "'succeeded', "
            "'transient_failure', "
            "'invalid_response', "
            "'authentication_failure', "
            "'configuration_failure', "
            "'unexpected_failure'"
            ")",
            name="ck_game_trait_attempts_outcome",
        ),
        CheckConstraint(
            "("
            "outcome = 'succeeded' "
            "AND derivation_id IS NOT NULL "
            "AND error_code IS NULL "
            "AND error_message IS NULL"
            ") OR ("
            "outcome <> 'succeeded' "
            "AND derivation_id IS NULL "
            "AND error_message IS NOT NULL"
            ")",
            name="ck_game_trait_attempts_result_state",
        ),
        CheckConstraint(
            "completed_at >= started_at",
            name="ck_game_trait_attempts_time_order",
        ),
        CheckConstraint(
            "length(facts_fingerprint) = 64",
            name="ck_game_trait_attempts_fingerprint_length",
        ),
        Index(
            "ix_game_trait_attempts_game_started_at",
            "steam_app_id",
            "started_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    steam_app_id: Mapped[int] = mapped_column(
        ForeignKey("games.steam_app_id", ondelete="CASCADE"),
    )
    operation_id: Mapped[str] = mapped_column(String(36))
    attempt_number: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(50))
    derivation_version: Mapped[str] = mapped_column(String(50))
    model_id: Mapped[str] = mapped_column(String(100))
    facts_fingerprint: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )
    outcome: Mapped[str] = mapped_column(String(30))
    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    derivation_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
