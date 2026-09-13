from decimal import Decimal

from app.gemini.client import (
    GeminiAPIError,
    GeminiStructuredContent,
    GeminiUnavailableError,
)
from app.gemini.traits.classifier import (
    ClassifiedGameTrait,
    GameTraitBatchClassification,
)
from app.gemini.traits.contracts import (
    NUMERIC_TRAIT_FIELDS,
    DerivedMood,
    DerivedNumericTrait,
    EvidenceCitation,
    GameTraitBatchRequestItem,
    GameTraitFacts,
    GameTraitResponse,
)
from app.gemini.traits.evaluation import (
    TRAIT_EVALUATION_BATCH_SIZE,
    TRAIT_EVALUATION_MAX_CALLS,
    TRAIT_EVALUATION_REFERENCES,
    TRAIT_EVALUATION_VERSION,
    TraitEvaluationGame,
    run_trait_evaluation,
)


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0

    def clock(self) -> float:
        self.value += 0.01
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _games() -> tuple[TraitEvaluationGame, ...]:
    return tuple(
        TraitEvaluationGame(
            reference=reference,
            request_item=GameTraitBatchRequestItem(
                steam_app_id=reference.steam_app_id,
                facts=GameTraitFacts(
                    name=reference.name,
                    summary="Fixture fact.",
                    genres=(),
                    themes=(),
                    keywords=(),
                    game_modes=(),
                    time_to_beat=(),
                    release_information=(),
                ),
            ),
        )
        for reference in TRAIT_EVALUATION_REFERENCES
    )


def _response(game: TraitEvaluationGame) -> GameTraitResponse:
    evidence = (
        EvidenceCitation(
            field="summary",
            value="Fixture fact.",
            reason="The fixture supports this rating.",
        ),
    )
    traits = {}
    for field, target in zip(
        NUMERIC_TRAIT_FIELDS,
        game.reference.numeric_targets,
        strict=True,
    ):
        traits[field] = (
            DerivedNumericTrait(
                value=None,
                confidence=Decimal("0"),
                evidence=(),
            )
            if target is None
            else DerivedNumericTrait(
                value=target,
                confidence=Decimal("0.80"),
                evidence=evidence,
            )
        )
    moods = (
        (
            DerivedMood(
                label=game.reference.defensible_moods[0],
                confidence=Decimal("0.80"),
                evidence=evidence,
            ),
        )
        if game.reference.defensible_moods
        else ()
    )
    return GameTraitResponse(**traits, moods=moods)


def _classification(
    items: tuple[GameTraitBatchRequestItem, ...],
    games_by_id: dict[int, TraitEvaluationGame],
) -> tuple[GameTraitBatchClassification, GeminiStructuredContent]:
    successes = tuple(
        ClassifiedGameTrait(
            steam_app_id=item.steam_app_id,
            response=_response(games_by_id[item.steam_app_id]),
        )
        for item in items
    )
    return (
        GameTraitBatchClassification(successes, (), ()),
        GeminiStructuredContent(
            content={},
            input_tokens=1_000,
            output_tokens=500,
            total_tokens=1_500,
        ),
    )


def test_fixture_has_eighteen_games_and_two_game_call_plan() -> None:
    assert len(TRAIT_EVALUATION_REFERENCES) == 18
    assert len({item.steam_app_id for item in TRAIT_EVALUATION_REFERENCES}) == 18
    assert all(len(item.numeric_targets) == 6 for item in TRAIT_EVALUATION_REFERENCES)
    assert TRAIT_EVALUATION_VERSION == "trait-evaluation-v2-two-game"
    assert TRAIT_EVALUATION_BATCH_SIZE == 2
    assert TRAIT_EVALUATION_MAX_CALLS == 11


def test_perfect_results_pass_all_trait_quality_gates() -> None:
    games = _games()
    games_by_id = {game.reference.steam_app_id: game for game in games}
    requested_ids = []

    def classify(client, *, model_id, items):
        requested_ids.append(tuple(item.steam_app_id for item in items))
        return _classification(items, games_by_id)

    fake_time = FakeTime()
    report = run_trait_evaluation(
        object(),
        model_id="test-model",
        games=games,
        requests_per_minute=10,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
        classifier=classify,
    )

    assert report.call_count == 10
    assert report.call_budget == TRAIT_EVALUATION_MAX_CALLS
    assert len(report.batches) == 10
    assert all(len(batch) == TRAIT_EVALUATION_BATCH_SIZE for batch in requested_ids)
    assert requested_ids[-1] == requested_ids[0]
    assert report.numeric_agreement_basis_points == 10_000
    assert report.unsupported_assertion_basis_points == 0
    assert report.mood_agreement_basis_points == 10_000
    assert report.evidence_verification_pass is True
    assert report.repeat_consistency_pass is True
    assert report.overall_pass is True


def test_one_transport_retry_uses_eleventh_call_without_repeating_results() -> None:
    games = _games()
    games_by_id = {game.reference.steam_app_id: game for game in games}
    failed_once = False

    def classify(client, *, model_id, items):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise GeminiUnavailableError("unavailable")
        return _classification(items, games_by_id)

    fake_time = FakeTime()
    report = run_trait_evaluation(
        object(),
        model_id="test-model",
        games=games,
        requests_per_minute=10,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
        classifier=classify,
    )

    assert report.call_count == 11
    assert len(report.batches) == 10
    assert report.batches[0].attempts == 2
    assert report.stopped_early is False
    assert report.overall_pass is True


def test_second_transport_failure_stops_without_exceeding_cap() -> None:
    games = _games()

    def unavailable(*args, **kwargs):
        raise GeminiUnavailableError("unavailable")

    fake_time = FakeTime()
    report = run_trait_evaluation(
        object(),
        model_id="test-model",
        games=games,
        requests_per_minute=10,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
        classifier=unavailable,
    )

    assert report.call_count == 2
    assert report.batches[0].error_code == "unavailable"
    assert report.stopped_early is True
    assert report.overall_pass is False


def test_reduced_call_budget_stops_before_an_unapproved_tenth_call() -> None:
    games = _games()
    games_by_id = {game.reference.steam_app_id: game for game in games}

    def classify(client, *, model_id, items):
        return _classification(items, games_by_id)

    fake_time = FakeTime()
    report = run_trait_evaluation(
        object(),
        model_id="test-model",
        games=games,
        requests_per_minute=10,
        maximum_calls=9,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
        classifier=classify,
    )

    assert report.call_budget == 9
    assert report.call_count == 9
    assert len(report.batches) == 9
    assert report.stopped_early is True
    assert report.overall_pass is False


def test_sanitizes_provider_http_status_and_stops() -> None:
    games = _games()

    def rejected(*args, **kwargs):
        raise GeminiAPIError(
            "rejected",
            status_code=400,
            reason_code="schema_nesting_depth",
        )

    fake_time = FakeTime()
    report = run_trait_evaluation(
        object(),
        model_id="test-model",
        games=games,
        requests_per_minute=10,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
        classifier=rejected,
    )

    assert report.call_count == 1
    assert report.batches[0].error_code == (
        "provider_http_400_schema_nesting_depth"
    )
    assert report.stopped_early is True
    assert report.overall_pass is False
