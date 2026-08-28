from collections.abc import Generator
from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.recommendations.retrieval as retrieval_module
from app.database import Base
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
)
from app.recommendations.contracts import (
    PlayStatus,
    PreferenceConstraints,
    RecommendationPreference,
    ReferencePreference,
    SelectedFacets,
)
from app.recommendations.preference_validation import (
    PreferenceValidationCode,
    PreferenceValidationError,
)
from app.recommendations.retrieval import (
    FactualCandidatePool,
    retrieve_factual_candidates,
)


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        yield session

    engine.dispose()


def _profile(profile_id: int = 1) -> Profile:
    return Profile(
        id=profile_id,
        steam_id=f"7656119800000000{profile_id}",
        display_name=f"Player {profile_id}",
    )


def _owned_game(
    profile: Profile,
    steam_app_id: int,
    *,
    genre: int | IGDBMetadataTerm | None,
    playtime_minutes: int = 0,
    normal_completion_seconds: int | None = None,
) -> ProfileGame:
    game = Game(
        steam_app_id=steam_app_id,
        name=f"Game {steam_app_id}",
        igdb_status="ready",
        time_to_beat_normally_seconds=normal_completion_seconds,
    )
    if genre is not None:
        term = (
            genre
            if isinstance(genre, IGDBMetadataTerm)
            else IGDBMetadataTerm(
                kind="genre",
                igdb_id=genre,
                name=f"Genre {genre}",
            )
        )
        game.metadata_term_links.append(
            GameIGDBMetadataTerm(term=term)
        )
    return ProfileGame(
        profile=profile,
        game=game,
        playtime_minutes=playtime_minutes,
    )


def _preference(
    *,
    play_status: PlayStatus = PlayStatus.EITHER,
    maximum_completion_minutes: int | None = None,
) -> RecommendationPreference:
    return RecommendationPreference(
        references=(
            ReferencePreference(
                steam_app_id=100,
                facets=SelectedFacets(
                    genre_ids=(10,),
                    theme_ids=(),
                    keyword_ids=(),
                    game_mode_ids=(),
                ),
            ),
        ),
        constraints=PreferenceConstraints(
            maximum_completion_minutes=maximum_completion_minutes,
            play_status=play_status,
        ),
    )


def test_validation_failure_happens_before_candidate_loading(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader_called = False

    def record_loader_call(*args: object, **kwargs: object) -> tuple[()]:
        nonlocal loader_called
        loader_called = True
        return ()

    monkeypatch.setattr(
        retrieval_module,
        "load_candidate_facts",
        record_loader_call,
    )

    with pytest.raises(PreferenceValidationError) as caught:
        retrieve_factual_candidates(
            database_session,
            profile_id=999,
            preference=_preference(),
            session_excluded_steam_app_ids=frozenset(),
        )

    assert caught.value.issue.code is PreferenceValidationCode.PROFILE_NOT_FOUND
    assert loader_called is False


def test_reference_only_library_returns_successful_empty_pool(
    database_session: Session,
) -> None:
    profile = _profile()
    database_session.add(
        _owned_game(profile, 100, genre=10)
    )
    database_session.commit()

    result = retrieve_factual_candidates(
        database_session,
        profile_id=profile.id,
        preference=_preference(),
        session_excluded_steam_app_ids=frozenset(),
    )

    assert result == FactualCandidatePool(
        candidates=(),
        eligible_count=0,
    )
    assert result.returned_count == 0
    assert result.is_truncated is False


def test_sparse_library_returns_all_eligible_candidates_with_evidence(
    database_session: Session,
) -> None:
    profile = _profile()
    shared_genre = IGDBMetadataTerm(
        kind="genre",
        igdb_id=10,
        name="Genre 10",
    )
    database_session.add_all(
        [
            _owned_game(profile, 100, genre=shared_genre),
            _owned_game(profile, 300, genre=None),
            _owned_game(profile, 200, genre=shared_genre),
        ]
    )
    database_session.commit()

    result = retrieve_factual_candidates(
        database_session,
        profile_id=profile.id,
        preference=_preference(),
        session_excluded_steam_app_ids=frozenset(),
    )

    assert tuple(candidate.steam_app_id for candidate in result.candidates) == (
        200,
        300,
    )
    assert tuple(
        candidate.evidence.score_basis_points
        for candidate in result.candidates
    ) == (10_000, 0)
    assert result.eligible_count == 2
    assert result.returned_count == 2
    assert result.is_truncated is False


def test_candidate_pool_is_immutable() -> None:
    result = FactualCandidatePool(candidates=(), eligible_count=0)

    with pytest.raises(FrozenInstanceError):
        result.eligible_count = 1  # type: ignore[misc]


def test_orchestration_applies_every_hard_constraint_before_scoring(
    database_session: Session,
) -> None:
    profile = _profile()
    shared_genre = IGDBMetadataTerm(
        kind="genre",
        igdb_id=10,
        name="Genre 10",
    )
    database_session.add_all(
        [
            _owned_game(profile, 100, genre=shared_genre),
            _owned_game(profile, 200, genre=shared_genre),
            _owned_game(
                profile,
                300,
                genre=shared_genre,
                playtime_minutes=1,
                normal_completion_seconds=3_600,
            ),
            _owned_game(
                profile,
                400,
                genre=shared_genre,
                normal_completion_seconds=3_601,
            ),
            _owned_game(
                profile,
                500,
                genre=shared_genre,
                normal_completion_seconds=None,
            ),
            _owned_game(
                profile,
                600,
                genre=shared_genre,
                normal_completion_seconds=3_600,
            ),
            _owned_game(
                profile,
                700,
                genre=None,
                normal_completion_seconds=3_600,
            ),
        ]
    )
    database_session.commit()

    result = retrieve_factual_candidates(
        database_session,
        profile_id=profile.id,
        preference=_preference(
            play_status=PlayStatus.UNPLAYED,
            maximum_completion_minutes=60,
        ),
        session_excluded_steam_app_ids=frozenset({200}),
    )

    assert tuple(candidate.steam_app_id for candidate in result.candidates) == (
        600,
        700,
    )
    assert result.eligible_count == 2


def test_large_tied_library_truncates_to_lowest_15_app_ids(
    database_session: Session,
) -> None:
    profile = _profile()
    database_session.add(_owned_game(profile, 100, genre=10))
    database_session.add_all(
        [
            _owned_game(profile, steam_app_id, genre=None)
            for steam_app_id in range(1_016, 1_000, -1)
        ]
    )
    database_session.commit()

    result = retrieve_factual_candidates(
        database_session,
        profile_id=profile.id,
        preference=_preference(),
        session_excluded_steam_app_ids=frozenset(),
    )

    assert tuple(candidate.steam_app_id for candidate in result.candidates) == (
        *range(1_001, 1_016),
    )
    assert result.eligible_count == 16
    assert result.returned_count == 15
    assert result.is_truncated is True


def test_multi_reference_scores_and_evidence_pass_through_unchanged(
    database_session: Session,
) -> None:
    profile = _profile()
    genre_10 = IGDBMetadataTerm(
        kind="genre",
        igdb_id=10,
        name="Genre 10",
    )
    genre_20 = IGDBMetadataTerm(
        kind="genre",
        igdb_id=20,
        name="Genre 20",
    )
    candidate_with_both = _owned_game(
        profile,
        300,
        genre=genre_10,
    )
    candidate_with_both.game.metadata_term_links.append(
        GameIGDBMetadataTerm(term=genre_20)
    )
    database_session.add_all(
        [
            _owned_game(profile, 100, genre=genre_10),
            _owned_game(profile, 101, genre=genre_20),
            _owned_game(profile, 200, genre=genre_10),
            candidate_with_both,
        ]
    )
    database_session.commit()
    preference = RecommendationPreference(
        references=(
            ReferencePreference(
                steam_app_id=100,
                facets=SelectedFacets(
                    genre_ids=(10,),
                    theme_ids=(),
                    keyword_ids=(),
                    game_mode_ids=(),
                ),
            ),
            ReferencePreference(
                steam_app_id=101,
                facets=SelectedFacets(
                    genre_ids=(20,),
                    theme_ids=(),
                    keyword_ids=(),
                    game_mode_ids=(),
                ),
            ),
        ),
        constraints=PreferenceConstraints(
            maximum_completion_minutes=None,
            play_status=PlayStatus.EITHER,
        ),
    )

    result = retrieve_factual_candidates(
        database_session,
        profile_id=profile.id,
        preference=preference,
        session_excluded_steam_app_ids=frozenset(),
    )

    assert tuple(candidate.steam_app_id for candidate in result.candidates) == (
        300,
        200,
    )
    assert tuple(
        candidate.evidence.score_basis_points
        for candidate in result.candidates
    ) == (10_000, 5_000)
    assert all(
        candidate.evidence.version == "factual-overlap-v1"
        for candidate in result.candidates
    )


def test_retrieval_uses_three_cache_only_selects_for_large_library(
    database_session: Session,
) -> None:
    profile = _profile()
    database_session.add(_owned_game(profile, 100, genre=10))
    database_session.add_all(
        [
            _owned_game(profile, steam_app_id, genre=None)
            for steam_app_id in range(1_000, 1_020)
        ]
    )
    database_session.commit()
    statements: list[str] = []

    def record_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    bind = database_session.get_bind()
    event.listen(bind, "before_cursor_execute", record_statement)

    try:
        retrieve_factual_candidates(
            database_session,
            profile_id=profile.id,
            preference=_preference(),
            session_excluded_steam_app_ids=frozenset(),
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_statement)

    statement_kinds = tuple(
        statement.lstrip().split(maxsplit=1)[0].upper()
        for statement in statements
    )
    assert statement_kinds == ("SELECT", "SELECT", "SELECT")
    assert "game_trait" not in " ".join(statements).lower()


def test_retrieval_does_not_autoflush_pending_candidates(
    database_session: Session,
) -> None:
    profile = _profile()
    database_session.add(_owned_game(profile, 100, genre=10))
    database_session.commit()
    pending_ownership = _owned_game(profile, 200, genre=None)
    database_session.add(pending_ownership)

    result = retrieve_factual_candidates(
        database_session,
        profile_id=profile.id,
        preference=_preference(),
        session_excluded_steam_app_ids=frozenset(),
    )

    assert result.candidates == ()
    assert pending_ownership in database_session.new
    assert pending_ownership.game in database_session.new
