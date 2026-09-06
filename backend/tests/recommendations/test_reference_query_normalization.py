import pytest

from app.recommendations.reference_reads import (
    InvalidSearchQueryError,
    normalize_search_query,
)


def test_normalizes_surrounding_and_internal_unicode_whitespace() -> None:
    assert normalize_search_query(
        " \tStardew\u2003  Valley\n"
    ) == "Stardew Valley"

def test_preserves_case_punctuation_accents_and_wildcards() -> None:
    assert normalize_search_query(
        "  100%_ Café: Édition  "
    ) == "100%_ Café: Édition"

@pytest.mark.parametrize(
    "query",
    [
        "Q",
        "x" * 100,
    ],
)
def test_accepts_query_length_boundaries(query: str) -> None:
    assert normalize_search_query(query) == query

@pytest.mark.parametrize(
    "query",
    [
        "",
        " \t\u2003\n",
        "x" * 101,
    ],
)
def test_rejects_query_outside_length_boundaries(query: str) -> None:
    with pytest.raises(InvalidSearchQueryError) as caught:
        normalize_search_query(query)

    assert caught.value.code == "invalid_query"
    assert caught.value.field == "query"
    assert str(caught.value) == (
        "Search query must contain between 1 and 100 characters."
    )

@pytest.mark.parametrize("query", [None, True, 10])
def test_rejects_nonstring_queries(query: object) -> None:
    with pytest.raises(InvalidSearchQueryError):
        normalize_search_query(query)
