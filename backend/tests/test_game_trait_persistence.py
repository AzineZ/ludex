import pytest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.game_trait_persistence import (
    persist_successful_trait_derivation,
    record_failed_trait_attempt,
)
from app.game_traits import (
    GameTraitFacts,
    GameTraitResponse,
    calculate_facts_fingerprint,
    TraitEvidenceError,
)
from app.models import (
    Game,
    GameCurrentTraitDerivation,
    GameTraitAttempt,
    GameTraitDerivation,
    GameTraitEvidence,
    GameTraitMood,
)


def _valid_response() -> GameTraitResponse:
    """Return a complete, structurally valid trait response."""
    evidence = {
        "field": "summary",
        "value": "A story-driven adventure.",
        "reason": "Directly supports the derived value.",
    }

    return GameTraitResponse.model_validate(
        {
            "story_focus": {
                "value": 4,
                "confidence": 0.80,
                "evidence": [evidence],
            },
            "combat_intensity": {
                "value": 2,
                "confidence": 0.65,
                "evidence": [evidence],
            },
            "difficulty": {
                "value": None,
                "confidence": 0,
                "evidence": [],
            },
            "pacing": {
                "value": 3,
                "confidence": 0.75,
                "evidence": [evidence],
            },
            "session_friendliness": {
                "value": None,
                "confidence": 0,
                "evidence": [],
            },
            "exploration_focus": {
                "value": 5,
                "confidence": 0.90,
                "evidence": [evidence],
            },
            "moods": [
                {
                    "label": "emotional",
                    "confidence": 0.85,
                    "evidence": [evidence],
                }
            ],
        }
    )


def _facts() -> GameTraitFacts:
    """Return canonical facts supporting the test response."""
    return GameTraitFacts(
        name="Example Adventure",
        summary="A story-driven adventure.",
        genres=("Adventure",),
        themes=(),
        keywords=(),
        game_modes=("Single player",),
        time_to_beat=(),
        release_information=(),
    )


def _successful_persistence_arguments() -> dict[str, object]:
    """Return valid keyword arguments for successful persistence."""
    started_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)

    return {
        "steam_app_id": 440,
        "response": _valid_response(),
        "facts": _facts(),
        "schema_version": "1",
        "derivation_version": "1",
        "model_id": "gemini-3.5-flash-lite",
        "operation_id": "11111111-1111-1111-1111-111111111111",
        "attempt_number": 1,
        "started_at": started_at,
        "completed_at": started_at + timedelta(seconds=2),
    }


def _failed_persistence_arguments() -> dict[str, object]:
    """Return valid keyword arguments for failed-attempt persistence."""
    started_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)

    return {
        "steam_app_id": 440,
        "facts": _facts(),
        "schema_version": "1",
        "derivation_version": "1",
        "model_id": "gemini-3.5-flash-lite",
        "operation_id": "11111111-1111-1111-1111-111111111111",
        "attempt_number": 1,
        "started_at": started_at,
        "completed_at": started_at + timedelta(seconds=2),
        "outcome": "invalid_response",
        "error_code": "domain_validation",
        "error_message": "Gemini returned unsupported evidence.",
    }


def test_persists_successful_trait_derivation_atomically() -> None:
    """Persist a complete success and make it the current derivation."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    started_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    completed_at = started_at + timedelta(seconds=2)
    facts = _facts()

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        persist_successful_trait_derivation(
            session,
            steam_app_id=440,
            response=_valid_response(),
            facts=facts,
            schema_version="1",
            derivation_version="1",
            model_id="gemini-3.5-flash-lite",
            operation_id="11111111-1111-1111-1111-111111111111",
            attempt_number=1,
            started_at=started_at,
            completed_at=completed_at,
        )

        derivation = session.scalar(
            select(GameTraitDerivation)
        )

        assert derivation is not None
        assert derivation.steam_app_id == 440
        assert derivation.schema_version == "1"
        assert derivation.derivation_version == "1"
        assert derivation.model_id == "gemini-3.5-flash-lite"
        assert derivation.facts_fingerprint == (
            calculate_facts_fingerprint(facts)
        )
        assert derivation.derived_at.replace(tzinfo=UTC) == completed_at
        assert derivation.story_focus_value == 4
        assert derivation.story_focus_confidence == Decimal("0.80")
        assert derivation.difficulty_value is None
        assert derivation.difficulty_confidence == Decimal("0.00")

        current = session.get(GameCurrentTraitDerivation, 440)

        assert current is not None
        assert current.derivation_id == derivation.id

        moods = session.scalars(
            select(GameTraitMood)
        ).all()

        assert [
            (mood.label, mood.confidence)
            for mood in moods
        ] == [("emotional", Decimal("0.85"))]

        evidence = session.scalars(
            select(GameTraitEvidence).order_by(
                GameTraitEvidence.target_kind,
                GameTraitEvidence.target_name,
                GameTraitEvidence.position,
            )
        ).all()

        assert len(evidence) == 5
        assert {
            (item.target_kind, item.target_name)
            for item in evidence
        } == {
            ("trait", "story_focus"),
            ("trait", "combat_intensity"),
            ("trait", "pacing"),
            ("trait", "exploration_focus"),
            ("mood", "emotional"),
        }
        assert all(item.position == 0 for item in evidence)
        assert all(item.source_field == "summary" for item in evidence)

        attempt = session.scalar(
            select(GameTraitAttempt)
        )

        assert attempt is not None
        assert attempt.outcome == "succeeded"
        assert attempt.derivation_id == derivation.id
        assert attempt.error_code is None
        assert attempt.error_message is None

    engine.dispose()


def test_replaces_current_pointer_without_deleting_history() -> None:
    """Make a replacement current while retaining the prior derivation."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    first_started_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    first_completed_at = first_started_at + timedelta(seconds=2)
    second_started_at = first_completed_at + timedelta(minutes=1)
    second_completed_at = second_started_at + timedelta(seconds=2)

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        persist_successful_trait_derivation(
            session,
            steam_app_id=440,
            response=_valid_response(),
            facts=_facts(),
            schema_version="1",
            derivation_version="1",
            model_id="gemini-3.5-flash-lite",
            operation_id="11111111-1111-1111-1111-111111111111",
            attempt_number=1,
            started_at=first_started_at,
            completed_at=first_completed_at,
        )

        first_current = session.get(
            GameCurrentTraitDerivation,
            440,
        )

        assert first_current is not None
        first_derivation_id = first_current.derivation_id

        session.rollback()

        persist_successful_trait_derivation(
            session,
            steam_app_id=440,
            response=_valid_response(),
            facts=_facts(),
            schema_version="1",
            derivation_version="2",
            model_id="gemini-3.5-flash-lite",
            operation_id="22222222-2222-2222-2222-222222222222",
            attempt_number=1,
            started_at=second_started_at,
            completed_at=second_completed_at,
        )

        derivations = session.scalars(
            select(GameTraitDerivation).order_by(
                GameTraitDerivation.id
            )
        ).all()
        current = session.get(GameCurrentTraitDerivation, 440)
        attempts = session.scalars(
            select(GameTraitAttempt).order_by(GameTraitAttempt.id)
        ).all()
        moods = session.scalars(
            select(GameTraitMood).order_by(
                GameTraitMood.derivation_id
            )
        ).all()
        evidence = session.scalars(
            select(GameTraitEvidence).order_by(
                GameTraitEvidence.derivation_id,
                GameTraitEvidence.id,
            )
        ).all()

        assert len(derivations) == 2
        assert derivations[0].id == first_derivation_id
        assert derivations[0].derivation_version == "1"
        assert derivations[1].derivation_version == "2"

        assert current is not None
        assert current.derivation_id == derivations[1].id

        assert [attempt.derivation_id for attempt in attempts] == [
            derivations[0].id,
            derivations[1].id,
        ]
        assert {
            mood.derivation_id
            for mood in moods
        } == {
            derivations[0].id,
            derivations[1].id,
        }
        assert {
            item.derivation_id
            for item in evidence
        } == {
            derivations[0].id,
            derivations[1].id,
        }

    engine.dispose()


def test_rolls_back_complete_replacement_after_mid_transaction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve the prior derivation when replacement persistence fails."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    first_started_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    first_completed_at = first_started_at + timedelta(seconds=2)
    second_started_at = first_completed_at + timedelta(minutes=1)
    second_completed_at = second_started_at + timedelta(seconds=2)

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        persist_successful_trait_derivation(
            session,
            steam_app_id=440,
            response=_valid_response(),
            facts=_facts(),
            schema_version="1",
            derivation_version="1",
            model_id="gemini-3.5-flash-lite",
            operation_id="11111111-1111-1111-1111-111111111111",
            attempt_number=1,
            started_at=first_started_at,
            completed_at=first_completed_at,
        )

        first_current = session.get(
            GameCurrentTraitDerivation,
            440,
        )

        assert first_current is not None
        first_derivation_id = first_current.derivation_id
        session.rollback()

        original_add = session.add

        def fail_before_attempt_add(
            instance: object,
            _warn: bool = True,
        ) -> None:
            """Simulate failure after replacement records have been prepared.

            Args:
                instance: ORM object being added to the session.
                _warn: SQLAlchemy's internal warning-control flag.

            Raises:
                RuntimeError: When the successful attempt is about to be added.
            """
            if isinstance(instance, GameTraitAttempt):
                raise RuntimeError("Simulated attempt persistence failure.")

            original_add(instance, _warn=_warn)

        with monkeypatch.context() as patch:
            patch.setattr(session, "add", fail_before_attempt_add)

            with pytest.raises(
                RuntimeError,
                match="Simulated attempt persistence failure",
            ):
                persist_successful_trait_derivation(
                    session,
                    steam_app_id=440,
                    response=_valid_response(),
                    facts=_facts(),
                    schema_version="1",
                    derivation_version="2",
                    model_id="gemini-3.5-flash-lite",
                    operation_id=(
                        "22222222-2222-2222-2222-222222222222"
                    ),
                    attempt_number=1,
                    started_at=second_started_at,
                    completed_at=second_completed_at,
                )

        derivations = session.scalars(
            select(GameTraitDerivation)
        ).all()
        attempts = session.scalars(
            select(GameTraitAttempt)
        ).all()
        moods = session.scalars(
            select(GameTraitMood)
        ).all()
        evidence = session.scalars(
            select(GameTraitEvidence)
        ).all()
        current = session.get(GameCurrentTraitDerivation, 440)

        assert [item.id for item in derivations] == [
            first_derivation_id
        ]
        assert len(attempts) == 1
        assert len(moods) == 1
        assert len(evidence) == 5
        assert current is not None
        assert current.derivation_id == first_derivation_id

    engine.dispose()


def test_records_failed_attempt_without_changing_current_derivation() -> None:
    """Record a failed regeneration while preserving usable traits."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    successful_started_at = datetime(
        2026,
        8,
        12,
        12,
        0,
        tzinfo=UTC,
    )
    successful_completed_at = successful_started_at + timedelta(
        seconds=2
    )
    failed_started_at = successful_completed_at + timedelta(minutes=1)
    failed_completed_at = failed_started_at + timedelta(seconds=2)
    facts = _facts()

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        persist_successful_trait_derivation(
            session,
            steam_app_id=440,
            response=_valid_response(),
            facts=facts,
            schema_version="1",
            derivation_version="1",
            model_id="gemini-3.5-flash-lite",
            operation_id="11111111-1111-1111-1111-111111111111",
            attempt_number=1,
            started_at=successful_started_at,
            completed_at=successful_completed_at,
        )

        record_failed_trait_attempt(
            session,
            steam_app_id=440,
            facts=facts,
            schema_version="1",
            derivation_version="2",
            model_id="gemini-3.5-flash-lite",
            operation_id="22222222-2222-2222-2222-222222222222",
            attempt_number=1,
            started_at=failed_started_at,
            completed_at=failed_completed_at,
            outcome="invalid_response",
            error_code="domain_validation",
            error_message="Gemini returned unsupported evidence.",
        )

        derivations = session.scalars(
            select(GameTraitDerivation)
        ).all()
        attempts = session.scalars(
            select(GameTraitAttempt).order_by(GameTraitAttempt.id)
        ).all()
        current = session.get(GameCurrentTraitDerivation, 440)

        assert len(derivations) == 1
        assert current is not None
        assert current.derivation_id == derivations[0].id

        assert len(attempts) == 2
        assert attempts[0].outcome == "succeeded"

        failed_attempt = attempts[1]

        assert failed_attempt.outcome == "invalid_response"
        assert failed_attempt.derivation_id is None
        assert failed_attempt.error_code == "domain_validation"
        assert (
            failed_attempt.error_message
            == "Gemini returned unsupported evidence."
        )
        assert failed_attempt.facts_fingerprint == (
            calculate_facts_fingerprint(facts)
        )

    engine.dispose()


def test_rejects_unverified_evidence_before_persistence() -> None:
    """Reject unsupported citations without creating partial records."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    started_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    completed_at = started_at + timedelta(seconds=2)
    unsupported_facts = _facts().model_copy(
        update={"summary": "A completely different factual summary."}
    )

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        with pytest.raises(
            TraitEvidenceError,
            match="absent from the supplied facts",
        ):
            persist_successful_trait_derivation(
                session,
                steam_app_id=440,
                response=_valid_response(),
                facts=unsupported_facts,
                schema_version="1",
                derivation_version="1",
                model_id="gemini-3.5-flash-lite",
                operation_id=(
                    "11111111-1111-1111-1111-111111111111"
                ),
                attempt_number=1,
                started_at=started_at,
                completed_at=completed_at,
            )

        assert session.scalar(
            select(GameTraitDerivation)
        ) is None
        assert session.scalar(
            select(GameTraitMood)
        ) is None
        assert session.scalar(
            select(GameTraitEvidence)
        ) is None
        assert session.scalar(
            select(GameTraitAttempt)
        ) is None
        assert session.get(GameCurrentTraitDerivation, 440) is None

    engine.dispose()


def test_duplicate_attempt_rolls_back_successful_replacement() -> None:
    """Roll back a replacement whose attempt identity is duplicated."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    first_started_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    first_completed_at = first_started_at + timedelta(seconds=2)
    second_started_at = first_completed_at + timedelta(minutes=1)
    second_completed_at = second_started_at + timedelta(seconds=2)
    operation_id = "11111111-1111-1111-1111-111111111111"

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        persist_successful_trait_derivation(
            session,
            steam_app_id=440,
            response=_valid_response(),
            facts=_facts(),
            schema_version="1",
            derivation_version="1",
            model_id="gemini-3.5-flash-lite",
            operation_id=operation_id,
            attempt_number=1,
            started_at=first_started_at,
            completed_at=first_completed_at,
        )

        first_current = session.get(
            GameCurrentTraitDerivation,
            440,
        )

        assert first_current is not None
        first_derivation_id = first_current.derivation_id
        session.rollback()

        with pytest.raises(IntegrityError):
            persist_successful_trait_derivation(
                session,
                steam_app_id=440,
                response=_valid_response(),
                facts=_facts(),
                schema_version="1",
                derivation_version="2",
                model_id="gemini-3.5-flash-lite",
                operation_id=operation_id,
                attempt_number=1,
                started_at=second_started_at,
                completed_at=second_completed_at,
            )

        derivations = session.scalars(
            select(GameTraitDerivation)
        ).all()
        attempts = session.scalars(
            select(GameTraitAttempt)
        ).all()
        current = session.get(GameCurrentTraitDerivation, 440)

        assert [item.id for item in derivations] == [
            first_derivation_id
        ]
        assert len(attempts) == 1
        assert current is not None
        assert current.derivation_id == first_derivation_id

    engine.dispose()


def test_successful_retry_creates_current_derivation() -> None:
    """Link a successful retry after retaining its failed first attempt."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    first_started_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    first_completed_at = first_started_at + timedelta(seconds=2)
    second_started_at = first_completed_at + timedelta(seconds=1)
    second_completed_at = second_started_at + timedelta(seconds=2)
    operation_id = "11111111-1111-1111-1111-111111111111"

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        record_failed_trait_attempt(
            session,
            steam_app_id=440,
            facts=_facts(),
            schema_version="1",
            derivation_version="1",
            model_id="gemini-3.5-flash-lite",
            operation_id=operation_id,
            attempt_number=1,
            started_at=first_started_at,
            completed_at=first_completed_at,
            outcome="transient_failure",
            error_code="service_unavailable",
            error_message="Gemini was temporarily unavailable.",
        )

        persist_successful_trait_derivation(
            session,
            steam_app_id=440,
            response=_valid_response(),
            facts=_facts(),
            schema_version="1",
            derivation_version="1",
            model_id="gemini-3.5-flash-lite",
            operation_id=operation_id,
            attempt_number=2,
            started_at=second_started_at,
            completed_at=second_completed_at,
        )

        attempts = session.scalars(
            select(GameTraitAttempt).order_by(
                GameTraitAttempt.attempt_number
            )
        ).all()
        derivations = session.scalars(
            select(GameTraitDerivation)
        ).all()
        current = session.get(GameCurrentTraitDerivation, 440)

        assert len(attempts) == 2
        assert attempts[0].outcome == "transient_failure"
        assert attempts[0].derivation_id is None
        assert attempts[1].outcome == "succeeded"

        assert len(derivations) == 1
        assert attempts[1].derivation_id == derivations[0].id
        assert current is not None
        assert current.derivation_id == derivations[0].id

    engine.dispose()


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "expected_message"),
    [
        ("steam_app_id", 0, "positive integer"),
        ("attempt_number", 0, "positive integer"),
        ("schema_version", "", "non-empty string"),
        ("model_id", " padded ", "surrounding whitespace"),
        ("operation_id", "x" * 37, "at most 36 characters"),
        (
            "started_at",
            datetime(2026, 8, 12, 12, 0),
            "timezone-aware",
        ),
        (
            "completed_at",
            datetime(2026, 8, 12, 11, 59, tzinfo=UTC),
            "cannot precede",
        ),
    ],
)
def test_rejects_invalid_success_provenance_before_persistence(
    field_name: str,
    invalid_value: object,
    expected_message: str,
) -> None:
    """Reject invalid trusted metadata without writing partial state."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    arguments = _successful_persistence_arguments()
    arguments[field_name] = invalid_value

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        with pytest.raises(ValueError, match=expected_message):
            persist_successful_trait_derivation(
                session,
                **arguments,
            )

        assert session.scalar(
            select(GameTraitDerivation)
        ) is None
        assert session.scalar(
            select(GameTraitAttempt)
        ) is None
        assert session.get(GameCurrentTraitDerivation, 440) is None

    engine.dispose()


def test_normalizes_and_bounds_failed_attempt_message() -> None:
    """Store a trimmed diagnostic that fits the database column."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    arguments = _failed_persistence_arguments()
    arguments["error_message"] = f"  {'x' * 600}  "

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        record_failed_trait_attempt(
            session,
            **arguments,
        )

        attempt = session.scalar(select(GameTraitAttempt))

        assert attempt is not None
        assert attempt.error_message == "x" * 500

    engine.dispose()


@pytest.mark.parametrize(
    "outcome",
    [
        "succeeded",
        "unsupported_failure",
    ],
)
def test_failure_recorder_rejects_nonfailure_outcome(
    outcome: str,
) -> None:
    """Reject outcomes that cannot describe a failed attempt."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    arguments = _failed_persistence_arguments()
    arguments["outcome"] = outcome

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        with pytest.raises(
            ValueError,
            match="outcome is unsupported",
        ):
            record_failed_trait_attempt(
                session,
                **arguments,
            )

        assert session.scalar(select(GameTraitAttempt)) is None

    engine.dispose()


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "expected_message"),
    [
        ("error_code", "", "non-empty string"),
        ("error_code", "x" * 101, "at most 100 characters"),
        ("error_message", "   ", "non-empty string"),
        ("attempt_number", 0, "positive integer"),
    ],
)
def test_rejects_invalid_failure_diagnostics_before_persistence(
    field_name: str,
    invalid_value: object,
    expected_message: str,
) -> None:
    """Reject invalid failure metadata without recording an attempt."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    arguments = _failed_persistence_arguments()
    arguments[field_name] = invalid_value

    with Session(engine) as session:
        session.add(Game(steam_app_id=440, name="Example Adventure"))
        session.commit()

        with pytest.raises(ValueError, match=expected_message):
            record_failed_trait_attempt(
                session,
                **arguments,
            )

        assert session.scalar(select(GameTraitAttempt)) is None

    engine.dispose()


@pytest.mark.parametrize(
    "record_kind",
    [
        "success",
        "failure",
    ],
)
def test_trait_persistence_requires_saved_game(
    record_kind: str,
) -> None:
    """Prevent successful and failed attempts from referencing absent games."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        with pytest.raises(
            ValueError,
            match="saved Steam game",
        ):
            if record_kind == "success":
                persist_successful_trait_derivation(
                    session,
                    **_successful_persistence_arguments(),
                )
            else:
                record_failed_trait_attempt(
                    session,
                    **_failed_persistence_arguments(),
                )

        assert session.scalar(
            select(GameTraitDerivation)
        ) is None
        assert session.scalar(
            select(GameTraitAttempt)
        ) is None
        assert session.scalar(
            select(GameCurrentTraitDerivation)
        ) is None

    engine.dispose()
