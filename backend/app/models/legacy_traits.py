"""Anchor the unused trait-derivation tables that still exist in deployed databases.

No application code reads or writes these tables. The classes remain only so
SQLAlchemy metadata keeps matching the Alembic schema until a dedicated
migration drops the tables."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


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
