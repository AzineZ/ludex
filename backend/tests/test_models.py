from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine, ForeignKeyConstraint
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models import (
    Game,
    GameCurrentTraitDerivation,
    GameIGDBMetadataTerm,
    GameTraitAttempt,
    GameTraitDerivation,
    GameTraitEvidence,
    GameTraitMood,
    IGDBMetadataTerm,
)

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pytest


def test_game_defines_igdb_metadata_columns_and_constraints() -> None:
    table = Game.__table__

    expected_columns = {
        "igdb_game_id",
        "igdb_status",
        "igdb_last_attempted_at",
        "igdb_last_error",
        "igdb_enriched_at",
        "igdb_metadata_updated_at",
        "summary",
        "first_release_at",
        "cover_image_id",
        "time_to_beat_hastily_seconds",
        "time_to_beat_normally_seconds",
        "time_to_beat_completely_seconds",
        "time_to_beat_submission_count",
        "time_to_beat_updated_at",
    }

    assert expected_columns <= set(table.columns.keys())
    assert table.c.igdb_status.nullable is False
    assert str(table.c.igdb_status.server_default.arg) == "pending"

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_games_igdb_status" in constraint_names
    assert "ck_games_igdb_game_id_positive" in constraint_names
    assert "ck_games_time_submission_count_nonnegative" in constraint_names


def test_metadata_term_tables_define_identity_and_foreign_keys() -> None:
    term_table = IGDBMetadataTerm.__table__
    link_table = GameIGDBMetadataTerm.__table__

    unique_constraint_names = {
        constraint.name
        for constraint in term_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert (
        "uq_igdb_metadata_terms_kind_igdb_id"
        in unique_constraint_names
    )
    assert {
        column.name for column in link_table.primary_key.columns
    } == {"steam_app_id", "term_id"}

    foreign_keys = {
        foreign_key.parent.name: (
            foreign_key.target_fullname,
            foreign_key.ondelete,
        )
        for foreign_key in link_table.foreign_keys
    }

    assert foreign_keys == {
        "steam_app_id": ("games.steam_app_id", "CASCADE"),
        "term_id": ("igdb_metadata_terms.id", "CASCADE"),
    }


def test_game_metadata_relationship_round_trip() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        game = Game(
            steam_app_id=440,
            name="Team Fortress 2",
        )
        genre = IGDBMetadataTerm(
            kind="genre",
            igdb_id=5,
            name="Shooter",
        )
        game.metadata_term_links.append(
            GameIGDBMetadataTerm(term=genre)
        )

        session.add(game)
        session.commit()
        session.expire_all()

        saved_game = session.get(Game, 440)

        assert saved_game is not None
        assert saved_game.igdb_status == "pending"
        assert [
            (
                link.term.kind,
                link.term.igdb_id,
                link.term.name,
            )
            for link in saved_game.metadata_term_links
        ] == [("genre", 5, "Shooter")]

    engine.dispose()


def _trait_derivation(steam_app_id: int) -> GameTraitDerivation:
    """Return one valid immutable trait derivation model."""
    return GameTraitDerivation(
        steam_app_id=steam_app_id,
        schema_version="1",
        derivation_version="1",
        model_id="gemini-3.5-flash-lite",
        facts_fingerprint="a" * 64,
        derived_at=datetime(2026, 8, 11, tzinfo=UTC),
        story_focus_value=4,
        story_focus_confidence=Decimal("0.80"),
        combat_intensity_value=2,
        combat_intensity_confidence=Decimal("0.65"),
        difficulty_value=None,
        difficulty_confidence=Decimal("0.00"),
        pacing_value=3,
        pacing_confidence=Decimal("0.75"),
        session_friendliness_value=None,
        session_friendliness_confidence=Decimal("0.00"),
        exploration_focus_value=5,
        exploration_focus_confidence=Decimal("0.90"),
    )


def test_trait_derivation_defines_fixed_trait_columns() -> None:
    table = GameTraitDerivation.__table__

    expected_columns = {
        "id",
        "steam_app_id",
        "schema_version",
        "derivation_version",
        "model_id",
        "facts_fingerprint",
        "derived_at",
        "story_focus_value",
        "story_focus_confidence",
        "combat_intensity_value",
        "combat_intensity_confidence",
        "difficulty_value",
        "difficulty_confidence",
        "pacing_value",
        "pacing_confidence",
        "session_friendliness_value",
        "session_friendliness_confidence",
        "exploration_focus_value",
        "exploration_focus_confidence",
    }

    assert expected_columns == set(table.columns.keys())

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    for trait_name in (
        "story_focus",
        "combat_intensity",
        "difficulty",
        "pacing",
        "session_friendliness",
        "exploration_focus",
    ):
        assert (
            f"ck_game_trait_derivations_{trait_name}_state"
            in constraint_names
        )


def test_current_derivation_pointer_uses_matching_game_identity() -> None:
    table = GameCurrentTraitDerivation.__table__

    composite_foreign_keys = [
        constraint
        for constraint in table.constraints
        if (
            isinstance(constraint, ForeignKeyConstraint)
            and len(constraint.elements) == 2
        )
    ]

    assert len(composite_foreign_keys) == 1
    assert {
        (
            element.parent.name,
            element.target_fullname,
        )
        for element in composite_foreign_keys[0].elements
    } == {
        (
            "steam_app_id",
            "game_trait_derivations.steam_app_id",
        ),
        (
            "derivation_id",
            "game_trait_derivations.id",
        ),
    }


def test_trait_derivation_and_current_pointer_round_trip() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Game(
                steam_app_id=440,
                name="Team Fortress 2",
            )
        )
        session.flush()

        derivation = _trait_derivation(440)
        session.add(derivation)
        session.flush()

        session.add(
            GameCurrentTraitDerivation(
                steam_app_id=440,
                derivation_id=derivation.id,
            )
        )
        session.commit()
        session.expire_all()

        current = session.get(GameCurrentTraitDerivation, 440)

        assert current is not None

        saved_derivation = session.get(
            GameTraitDerivation,
            current.derivation_id,
        )

        assert saved_derivation is not None
        assert saved_derivation.story_focus_value == 4
        assert (
            saved_derivation.story_focus_confidence
            == Decimal("0.80")
        )
        assert saved_derivation.difficulty_value is None


def test_database_rejects_inconsistent_trait_state() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Game(
                steam_app_id=440,
                name="Team Fortress 2",
            )
        )
        session.flush()

        derivation = _trait_derivation(440)
        derivation.difficulty_confidence = Decimal("0.30")
        session.add(derivation)

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()

    engine.dispose()


def test_trait_child_tables_define_required_constraints() -> None:
    mood_table = GameTraitMood.__table__
    evidence_table = GameTraitEvidence.__table__
    attempt_table = GameTraitAttempt.__table__

    assert {
        column.name for column in mood_table.primary_key.columns
    } == {"derivation_id", "label"}

    constraint_names = {
        constraint.name
        for table in (mood_table, evidence_table, attempt_table)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert {
        "ck_game_trait_moods_label",
        "ck_game_trait_moods_confidence",
        "ck_game_trait_evidence_target",
        "ck_game_trait_evidence_source_field",
        "ck_game_trait_evidence_position",
        "ck_game_trait_attempts_outcome",
        "ck_game_trait_attempts_result_state",
        "ck_game_trait_attempts_attempt_number",
    } <= constraint_names


def test_trait_mood_and_evidence_round_trip() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Team Fortress 2"))
        session.flush()

        derivation = _trait_derivation(440)
        session.add(derivation)
        session.flush()

        mood = GameTraitMood(
            derivation_id=derivation.id,
            label="tense",
            confidence=Decimal("0.80"),
        )
        evidence = GameTraitEvidence(
            derivation_id=derivation.id,
            target_kind="trait",
            target_name="story_focus",
            position=0,
            source_field="summary",
            source_value="A class-based multiplayer shooter.",
            reason="Directly supports the derived value.",
        )
        session.add_all([mood, evidence])
        session.commit()
        session.expire_all()

        saved_mood = session.get(
            GameTraitMood,
            (derivation.id, "tense"),
        )
        saved_evidence = session.get(
            GameTraitEvidence,
            evidence.id,
        )

        assert saved_mood is not None
        assert saved_mood.confidence == Decimal("0.80")
        assert saved_evidence is not None
        assert saved_evidence.target_name == "story_focus"
        assert saved_evidence.source_field == "summary"

    engine.dispose()


@pytest.mark.parametrize(
    ("label", "confidence"),
    [
        ("cozy", Decimal("0.80")),
        ("tense", Decimal("0.29")),
    ],
)
def test_database_rejects_invalid_mood_state(
    label: str,
    confidence: Decimal,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Team Fortress 2"))
        session.flush()

        derivation = _trait_derivation(440)
        session.add(derivation)
        session.flush()

        session.add(
            GameTraitMood(
                derivation_id=derivation.id,
                label=label,
                confidence=confidence,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()

    engine.dispose()


def test_database_rejects_mismatched_evidence_target() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Team Fortress 2"))
        session.flush()

        derivation = _trait_derivation(440)
        session.add(derivation)
        session.flush()

        session.add(
            GameTraitEvidence(
                derivation_id=derivation.id,
                target_kind="mood",
                target_name="story_focus",
                position=0,
                source_field="summary",
                source_value="A class-based multiplayer shooter.",
                reason="Uses a trait name as though it were a mood.",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()

    engine.dispose()


def test_failed_trait_attempt_round_trip() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    started_at = datetime(2026, 8, 11, tzinfo=UTC)

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Team Fortress 2"))
        session.flush()

        attempt = GameTraitAttempt(
            steam_app_id=440,
            operation_id="11111111-1111-1111-1111-111111111111",
            attempt_number=1,
            schema_version="1",
            derivation_version="1",
            model_id="gemini-3.5-flash-lite",
            facts_fingerprint="a" * 64,
            started_at=started_at,
            completed_at=started_at + timedelta(seconds=2),
            outcome="invalid_response",
            error_code="domain_validation",
            error_message="Gemini returned unsupported evidence.",
            derivation_id=None,
        )
        session.add(attempt)
        session.commit()
        session.expire_all()

        saved_attempt = session.get(GameTraitAttempt, attempt.id)

        assert saved_attempt is not None
        assert saved_attempt.outcome == "invalid_response"
        assert saved_attempt.derivation_id is None
        assert saved_attempt.error_code == "domain_validation"

    engine.dispose()


def test_successful_attempt_requires_saved_derivation() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    started_at = datetime(2026, 8, 11, tzinfo=UTC)

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Team Fortress 2"))
        session.flush()

        session.add(
            GameTraitAttempt(
                steam_app_id=440,
                operation_id="11111111-1111-1111-1111-111111111111",
                attempt_number=1,
                schema_version="1",
                derivation_version="1",
                model_id="gemini-3.5-flash-lite",
                facts_fingerprint="a" * 64,
                started_at=started_at,
                completed_at=started_at,
                outcome="succeeded",
                error_code=None,
                error_message=None,
                derivation_id=None,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()

    engine.dispose()
