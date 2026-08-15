from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.recommendations.preference_validation as validation_module
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
    ValidatedRecommendationPreference,
    validate_preference,
)


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(
        engine,
        autoflush=False,
        expire_on_commit=False,
    ) as session:
        yield session

    engine.dispose()


def _profile(profile_id: int) -> Profile:
    return Profile(
        id=profile_id,
        steam_id=f"7656119800000000{profile_id}",
        display_name=f"Player {profile_id}",
    )


def _ownership(profile: Profile, game: Game) -> ProfileGame:
    return ProfileGame(
        profile=profile,
        game=game,
        playtime_minutes=0,
    )


def _term_link(
    kind: str,
    igdb_id: int,
    name: str | None = None,
) -> GameIGDBMetadataTerm:
    return GameIGDBMetadataTerm(
        term=IGDBMetadataTerm(
            kind=kind,
            igdb_id=igdb_id,
            name=name or f"{kind}-{igdb_id}",
        )
    )


def _owned_game(
    session: Session,
    profile: Profile,
    steam_app_id: int,
    *,
    status: str = "ready",
    links: tuple[GameIGDBMetadataTerm, ...] = (),
) -> Game:
    game = Game(
        steam_app_id=steam_app_id,
        name=f"Game {steam_app_id}",
        igdb_status=status,
    )
    game.metadata_term_links.extend(links)
    session.add(_ownership(profile, game))
    return game


def _reference(
    steam_app_id: int,
    *,
    genres: list[int] | None = None,
    themes: list[int] | None = None,
    keywords: list[int] | None = None,
    game_modes: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "steam_app_id": steam_app_id,
        "facets": {
            "genre_ids": genres or [],
            "theme_ids": themes or [],
            "keyword_ids": keywords or [],
            "game_mode_ids": game_modes or [],
        },
    }


def _preference(
    references: list[dict[str, Any]],
) -> RecommendationPreference:
    return RecommendationPreference.model_validate(
        {
            "references": references,
            "constraints": {
                "maximum_completion_minutes": None,
                "play_status": "either",
            },
        }
    )


@contextmanager
def _capture_selects(
    session: Session,
) -> Generator[list[str], None, None]:
    statements: list[str] = []

    def record_select(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = session.get_bind()
    event.listen(bind, "before_cursor_execute", record_select)

    try:
        yield statements
    finally:
        event.remove(bind, "before_cursor_execute", record_select)


def _assert_issue(
    error: PreferenceValidationError,
    *,
    code: PreferenceValidationCode,
    field: str,
    message: str,
) -> None:
    assert error.issue.code is code
    assert error.issue.field == field
    assert error.issue.message == message
    assert str(error) == message


def test_validates_complete_multi_reference_preference(
    database_session: Session,
) -> None:
    profile = _profile(1)

    shared_genre = IGDBMetadataTerm(
        kind="genre",
        igdb_id=10,
        name="Adventure",
    )
    first_game = Game(
        steam_app_id=100,
        name="First Reference",
        igdb_status="ready",
    )
    first_game.metadata_term_links.extend(
        [
            GameIGDBMetadataTerm(term=shared_genre),
            _term_link("theme", 20),
            _term_link("keyword", 30),
            _term_link("game_mode", 40),
        ]
    )
    second_game = Game(
        steam_app_id=200,
        name="Second Reference",
        igdb_status="ready",
    )
    second_game.metadata_term_links.extend(
        [
            GameIGDBMetadataTerm(term=shared_genre),
            _term_link("keyword", 50),
        ]
    )
    third_game = Game(
        steam_app_id=300,
        name="Third Reference",
        igdb_status="ready",
    )
    third_game.metadata_term_links.append(
        _term_link("theme", 60)
    )
    database_session.add_all(
        [
            _ownership(profile, first_game),
            _ownership(profile, second_game),
            _ownership(profile, third_game),
        ]
    )
    database_session.commit()

    preference = _preference(
        [
            _reference(
                100,
                genres=[10],
                themes=[20],
                keywords=[30],
                game_modes=[40],
            ),
            _reference(
                200,
                genres=[10],
                keywords=[50],
            ),
            _reference(
                300,
                themes=[60],
            ),
        ]
    )

    result = validate_preference(
        database_session,
        profile.id,
        preference,
    )

    assert isinstance(
        result,
        ValidatedRecommendationPreference,
    )
    assert result.preference is preference


def test_validated_wrapper_is_frozen(
    database_session: Session,
) -> None:
    profile = _profile(1)
    _owned_game(
        database_session,
        profile,
        100,
        links=(_term_link("genre", 10),),
    )
    database_session.commit()
    preference = _preference(
        [_reference(100, genres=[10])]
    )

    result = validate_preference(
        database_session,
        profile.id,
        preference,
    )

    with pytest.raises(FrozenInstanceError):
        result.preference = preference


@pytest.mark.parametrize(
    "profile_id",
    [
        True,
        False,
        0,
        -1,
        "1",
        None,
    ],
)
def test_rejects_invalid_profile_identity_without_querying(
    database_session: Session,
    profile_id: object,
) -> None:
    preference = _preference(
        [_reference(100, genres=[10])]
    )

    with _capture_selects(database_session) as statements:
        with pytest.raises(PreferenceValidationError) as caught:
            validate_preference(
                database_session,
                profile_id,
                preference,
            )

    assert statements == []
    _assert_issue(
        caught.value,
        code=PreferenceValidationCode.PROFILE_NOT_FOUND,
        field="profile_id",
        message="The selected profile does not exist.",
    )


def test_rejects_unknown_positive_profile(
    database_session: Session,
) -> None:
    preference = _preference(
        [_reference(100, genres=[10])]
    )

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            999,
            preference,
        )

    _assert_issue(
        caught.value,
        code=PreferenceValidationCode.PROFILE_NOT_FOUND,
        field="profile_id",
        message="The selected profile does not exist.",
    )


@pytest.mark.parametrize("reference_case", ["unknown", "unowned"])
def test_rejects_unknown_and_unowned_references_identically(
    database_session: Session,
    reference_case: str,
) -> None:
    selected_profile = _profile(1)
    database_session.add(selected_profile)

    steam_app_id = 999
    if reference_case == "unowned":
        other_profile = _profile(2)
        steam_app_id = 200
        _owned_game(
            database_session,
            other_profile,
            steam_app_id,
            links=(_term_link("genre", 10),),
        )

    database_session.commit()
    preference = _preference(
        [_reference(steam_app_id, genres=[10])]
    )

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            selected_profile.id,
            preference,
        )

    _assert_issue(
        caught.value,
        code=PreferenceValidationCode.REFERENCE_NOT_OWNED,
        field="references[0].steam_app_id",
        message=(
            "The selected reference game is not owned by this profile."
        ),
    )


def test_checks_all_ownership_before_any_readiness(
    database_session: Session,
) -> None:
    profile = _profile(1)
    _owned_game(
        database_session,
        profile,
        100,
        status="missing",
    )
    database_session.commit()
    preference = _preference(
        [
            _reference(100, genres=[10]),
            _reference(200, genres=[20]),
        ]
    )

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            profile.id,
            preference,
        )

    _assert_issue(
        caught.value,
        code=PreferenceValidationCode.REFERENCE_NOT_OWNED,
        field="references[1].steam_app_id",
        message=(
            "The selected reference game is not owned by this profile."
        ),
    )


def test_checks_readiness_in_reference_order(
    database_session: Session,
) -> None:
    profile = _profile(1)
    _owned_game(
        database_session,
        profile,
        100,
        links=(_term_link("genre", 10),),
    )
    _owned_game(
        database_session,
        profile,
        200,
        status="ambiguous",
    )
    _owned_game(
        database_session,
        profile,
        300,
        status="missing",
    )
    database_session.commit()
    preference = _preference(
        [
            _reference(100, genres=[10]),
            _reference(200, genres=[20]),
            _reference(300, genres=[30]),
        ]
    )

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            profile.id,
            preference,
        )

    _assert_issue(
        caught.value,
        code=(
            PreferenceValidationCode
            .REFERENCE_METADATA_UNAVAILABLE
        ),
        field="references[1].steam_app_id",
        message=(
            "Factual metadata is unavailable for this reference game."
        ),
    )


@pytest.mark.parametrize(
    (
        "failure_kind",
        "selected_facets",
        "expected_field",
    ),
    [
        (
            "missing",
            {"genres": [999]},
            "references[0].facets.genre_ids[0]",
        ),
        (
            "wrong_kind",
            {"themes": [10]},
            "references[0].facets.theme_ids[0]",
        ),
        (
            "wrong_reference",
            {"genres": [99]},
            "references[0].facets.genre_ids[0]",
        ),
    ],
)
def test_rejects_missing_wrong_kind_and_wrong_reference_facets(
    database_session: Session,
    failure_kind: str,
    selected_facets: dict[str, list[int]],
    expected_field: str,
) -> None:
    profile = _profile(1)
    _owned_game(
        database_session,
        profile,
        100,
        links=(_term_link("genre", 10),),
    )

    references = [
        _reference(
            100,
            genres=selected_facets.get("genres"),
            themes=selected_facets.get("themes"),
        )
    ]

    if failure_kind == "wrong_reference":
        _owned_game(
            database_session,
            profile,
            200,
            links=(_term_link("genre", 99),),
        )
        references.append(
            _reference(200, genres=[99])
        )

    database_session.commit()
    preference = _preference(references)

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            profile.id,
            preference,
        )

    _assert_issue(
        caught.value,
        code=PreferenceValidationCode.FACET_NOT_ON_REFERENCE,
        field=expected_field,
        message=(
            "The selected facet does not belong to this reference game."
        ),
    )


def test_membership_failure_uses_canonical_sorted_index(
    database_session: Session,
) -> None:
    profile = _profile(1)
    _owned_game(
        database_session,
        profile,
        100,
        links=(_term_link("genre", 12),),
    )
    database_session.commit()
    preference = _preference(
        [_reference(100, genres=[999, 12])]
    )

    assert preference.references[0].facets.genre_ids == (
        12,
        999,
    )

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            profile.id,
            preference,
        )

    _assert_issue(
        caught.value,
        code=PreferenceValidationCode.FACET_NOT_ON_REFERENCE,
        field="references[0].facets.genre_ids[1]",
        message=(
            "The selected facet does not belong to this reference game."
        ),
    )


def test_membership_checks_category_order(
    database_session: Session,
) -> None:
    profile = _profile(1)
    _owned_game(database_session, profile, 100)
    database_session.commit()
    preference = _preference(
        [
            _reference(
                100,
                genres=[400],
                themes=[300],
                keywords=[200],
                game_modes=[100],
            )
        ]
    )

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            profile.id,
            preference,
        )

    _assert_issue(
        caught.value,
        code=PreferenceValidationCode.FACET_NOT_ON_REFERENCE,
        field="references[0].facets.genre_ids[0]",
        message=(
            "The selected facet does not belong to this reference game."
        ),
    )


def test_membership_checks_reference_order(
    database_session: Session,
) -> None:
    profile = _profile(1)
    _owned_game(database_session, profile, 100)
    _owned_game(database_session, profile, 200)
    database_session.commit()
    preference = _preference(
        [
            _reference(100, genres=[999]),
            _reference(200, genres=[888]),
        ]
    )

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            profile.id,
            preference,
        )

    _assert_issue(
        caught.value,
        code=PreferenceValidationCode.FACET_NOT_ON_REFERENCE,
        field="references[0].facets.genre_ids[0]",
        message=(
            "The selected facet does not belong to this reference game."
        ),
    )


def test_checks_all_readiness_before_any_membership(
    database_session: Session,
) -> None:
    profile = _profile(1)
    _owned_game(database_session, profile, 100)
    _owned_game(
        database_session,
        profile,
        200,
        status="pending",
    )
    database_session.commit()
    preference = _preference(
        [
            _reference(100, genres=[999]),
            _reference(200, genres=[888]),
        ]
    )

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            profile.id,
            preference,
        )

    _assert_issue(
        caught.value,
        code=(
            PreferenceValidationCode
            .REFERENCE_METADATA_UNAVAILABLE
        ),
        field="references[1].steam_app_id",
        message=(
            "Factual metadata is unavailable for this reference game."
        ),
    )


def test_rechecks_keyword_limit_before_querying(
    database_session: Session,
) -> None:
    constraints = PreferenceConstraints(
        maximum_completion_minutes=None,
        play_status=PlayStatus.EITHER,
    )
    facets = SelectedFacets.model_construct(
        genre_ids=(),
        theme_ids=(),
        keyword_ids=(1, 2, 3, 4),
        game_mode_ids=(),
    )
    reference = ReferencePreference.model_construct(
        steam_app_id=100,
        facets=facets,
    )
    preference = RecommendationPreference.model_construct(
        references=(reference,),
        constraints=constraints,
    )

    with _capture_selects(database_session) as statements:
        with pytest.raises(PreferenceValidationError) as caught:
            validate_preference(
                database_session,
                1,
                preference,
            )

    assert statements == []
    _assert_issue(
        caught.value,
        code=PreferenceValidationCode.TOO_MANY_KEYWORDS,
        field="references[0].facets.keyword_ids",
        message=(
            "Select no more than three keywords per reference game."
        ),
    )


def test_successful_validation_uses_one_select(
    database_session: Session,
) -> None:
    profile = _profile(1)
    _owned_game(
        database_session,
        profile,
        100,
        links=(
            _term_link("genre", 10),
            _term_link("keyword", 20),
        ),
    )
    database_session.commit()
    preference = _preference(
        [
            _reference(
                100,
                genres=[10],
                keywords=[20],
            )
        ]
    )

    with _capture_selects(database_session) as statements:
        validate_preference(
            database_session,
            profile.id,
            preference,
        )

    assert len(statements) == 1


def test_invalid_mixed_request_never_constructs_wrapper(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile(1)
    _owned_game(
        database_session,
        profile,
        100,
        links=(_term_link("genre", 10),),
    )
    _owned_game(database_session, profile, 200)
    database_session.commit()
    preference = _preference(
        [
            _reference(100, genres=[10]),
            _reference(200, genres=[999]),
        ]
    )

    def reject_wrapper_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "A wrapper must not be constructed for invalid input."
        )

    monkeypatch.setattr(
        validation_module,
        "ValidatedRecommendationPreference",
        reject_wrapper_construction,
    )

    with pytest.raises(PreferenceValidationError):
        validate_preference(
            database_session,
            profile.id,
            preference,
        )


def test_validation_issue_is_frozen(
    database_session: Session,
) -> None:
    preference = _preference(
        [_reference(100, genres=[10])]
    )

    with pytest.raises(PreferenceValidationError) as caught:
        validate_preference(
            database_session,
            999,
            preference,
        )

    with pytest.raises(FrozenInstanceError):
        caught.value.issue.field = "changed"


def test_validation_is_read_only(
    database_session: Session,
) -> None:
    profile = _profile(1)
    _owned_game(
        database_session,
        profile,
        100,
        links=(_term_link("genre", 10),),
    )
    database_session.commit()
    preference = _preference(
        [_reference(100, genres=[10])]
    )

    transaction_events: list[str] = []

    def record_flush(
        session: Session,
        flush_context: object,
        instances: object,
    ) -> None:
        transaction_events.append("flush")

    def record_commit(session: Session) -> None:
        transaction_events.append("commit")

    def record_rollback(session: Session) -> None:
        transaction_events.append("rollback")

    event.listen(database_session, "before_flush", record_flush)
    event.listen(database_session, "after_commit", record_commit)
    event.listen(
        database_session,
        "after_rollback",
        record_rollback,
    )

    try:
        validate_preference(
            database_session,
            profile.id,
            preference,
        )
    finally:
        event.remove(
            database_session,
            "before_flush",
            record_flush,
        )
        event.remove(
            database_session,
            "after_commit",
            record_commit,
        )
        event.remove(
            database_session,
            "after_rollback",
            record_rollback,
        )

    assert transaction_events == []
    assert not database_session.new
    assert not database_session.dirty
    assert not database_session.deleted
