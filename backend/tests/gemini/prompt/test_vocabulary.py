from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.gemini.prompt.contracts import PromptConceptKind
from app.gemini.prompt.vocabulary import build_prompt_vocabulary
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
    Profile,
    ProfileGame,
)


def test_vocabulary_is_profile_scoped_curated_and_deterministic() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        selected = Profile(steam_id="1", display_name="Selected")
        other = Profile(steam_id="2", display_name="Other")
        first = Game(steam_app_id=10, name="First")
        second = Game(steam_app_id=20, name="Second")
        session.add_all([selected, other, first, second])
        session.flush()
        session.add_all(
            [
                ProfileGame(
                    profile_id=selected.id,
                    steam_app_id=first.steam_app_id,
                ),
                ProfileGame(
                    profile_id=other.id,
                    steam_app_id=second.steam_app_id,
                ),
            ]
        )
        terms = [
            IGDBMetadataTerm(kind="genre", igdb_id=12, name="RPG"),
            IGDBMetadataTerm(
                kind="keyword",
                igdb_id=30,
                name="Open world",
            ),
            IGDBMetadataTerm(
                kind="keyword",
                igdb_id=31,
                name="Uncurated detail",
            ),
            IGDBMetadataTerm(kind="theme", igdb_id=90, name="Other theme"),
        ]
        session.add_all(terms)
        session.flush()
        session.add_all(
            [
                GameIGDBMetadataTerm(
                    steam_app_id=10,
                    term_id=terms[0].id,
                ),
                GameIGDBMetadataTerm(
                    steam_app_id=10,
                    term_id=terms[1].id,
                ),
                GameIGDBMetadataTerm(
                    steam_app_id=10,
                    term_id=terms[2].id,
                ),
                GameIGDBMetadataTerm(
                    steam_app_id=20,
                    term_id=terms[3].id,
                ),
            ]
        )
        session.commit()

        vocabulary = build_prompt_vocabulary(
            session,
            profile_id=selected.id,
        )

    ids = [entry.concept_id for entry in vocabulary.entries]
    assert ids[:2] == ["genre:12", "keyword:30"]
    assert "keyword:31" not in ids
    assert "theme:90" not in ids
    assert "trait:story_focus" in ids
    assert "mood:relaxing" in ids
    assert len(ids) == len(set(ids))
    assert vocabulary.entries[0].kind is PromptConceptKind.GENRE
    engine.dispose()
