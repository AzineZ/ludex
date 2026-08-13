from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.game_trait_service as service
from app.database import Base
from app.game_traits import GameTraitResponse
from app.gemini_client import GeminiClient
from app.models import (
    Game,
    GameIGDBMetadataTerm,
    IGDBMetadataTerm,
)


def test_closes_fact_read_transaction_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finish the database read before invoking Gemini orchestration."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    client = MagicMock(spec=GeminiClient)
    expected_response = MagicMock(spec=GameTraitResponse)

    with Session(engine) as session:
        game = Game(
            steam_app_id=440,
            name="Example Adventure",
            summary="A story-driven adventure.",
        )
        game.metadata_term_links.append(
            GameIGDBMetadataTerm(
                term=IGDBMetadataTerm(
                    kind="genre",
                    igdb_id=31,
                    name="Adventure",
                )
            )
        )
        session.add(game)
        session.commit()

        def generate(
            generation_session: Session,
            generation_client: GeminiClient,
            **arguments: object,
        ) -> GameTraitResponse:
            """Verify generation begins outside the read transaction."""
            assert generation_session is session
            assert generation_client is client
            assert session.in_transaction() is False

            facts = arguments["facts"]

            assert facts.name == "Example Adventure"
            assert facts.summary == "A story-driven adventure."
            assert facts.genres == ("Adventure",)

            return expected_response

        generation_mock = MagicMock(side_effect=generate)

        monkeypatch.setattr(
            service,
            "generate_game_traits",
            generation_mock,
        )

        result = service.generate_saved_game_traits(
            session,
            client,
            steam_app_id=440,
            operation_id=(
                "11111111-1111-1111-1111-111111111111"
            ),
        )

        assert result is expected_response
        assert generation_mock.call_count == 1
        assert (
            generation_mock.call_args.kwargs["steam_app_id"]
            == 440
        )
        assert (
            generation_mock.call_args.kwargs["operation_id"]
            == "11111111-1111-1111-1111-111111111111"
        )

    engine.dispose()


def test_missing_saved_game_never_calls_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject an unknown game before any Gemini request can begin."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    client = MagicMock(spec=GeminiClient)
    generation_mock = MagicMock()

    monkeypatch.setattr(
        service,
        "generate_game_traits",
        generation_mock,
    )

    with Session(engine) as session:
        with pytest.raises(
            ValueError,
            match="saved Steam game",
        ):
            service.generate_saved_game_traits(
                session,
                client,
                steam_app_id=440,
                operation_id=(
                    "11111111-1111-1111-1111-111111111111"
                ),
            )

        assert session.in_transaction() is False
        generation_mock.assert_not_called()

    engine.dispose()
