from typing import Annotated

from fastapi import Depends, Path, Query
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.recommendations.api.common import (
    REFERENCE_SEARCH_ERROR_RESPONSES,
    STANDARD_ERROR_RESPONSES,
    create_recommendation_api_router,
)
from app.recommendations.api.errors import raise_reference_read_error
from app.recommendations.api.schemas import (
    FacetOptionResponse,
    KeywordBrowseResponse,
    KeywordSearchResponse,
    OwnedGameSearchResponse,
    OwnedGameSuggestionResponse,
    ReferenceDetailsResponse,
    ReferenceFacetsResponse,
)
from app.recommendations.reference_reads import (
    FacetOption,
    InvalidSearchQueryError,
    OwnedGameSuggestion,
    ProfileNotFoundError,
    ReferenceDetails,
    ReferenceMetadataUnavailableError,
    ReferenceNotOwnedError,
    browse_reference_keywords,
    load_reference_details,
    search_owned_games,
    search_reference_keywords,
)
from app.sessions.http import require_access_session
from app.sessions.service import ActiveAccessSession


PositivePathIdentifier = Annotated[int, Path(gt=0)]
RequiredSearchQuery = Annotated[str, Query()]

router = create_recommendation_api_router()


@router.get(
    "/references",
    response_model=OwnedGameSearchResponse,
    responses=REFERENCE_SEARCH_ERROR_RESPONSES,
)
def search_references(
    query: RequiredSearchQuery,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> OwnedGameSearchResponse:
    """Search cached games owned by one selected profile."""
    try:
        suggestions = search_owned_games(
            database_session,
            access_session.profile_id,
            query,
        )
    except (InvalidSearchQueryError, ProfileNotFoundError) as error:
        raise_reference_read_error(error)

    return OwnedGameSearchResponse(
        items=tuple(
            _owned_game_suggestion_response(suggestion)
            for suggestion in suggestions
        )
    )


@router.get(
    "/references/{steam_app_id}",
    response_model=ReferenceDetailsResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
def read_reference_details(
    steam_app_id: PositivePathIdentifier,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> ReferenceDetailsResponse:
    """Return cached factual details for one ready owned reference."""
    try:
        details = load_reference_details(
            database_session,
            access_session.profile_id,
            steam_app_id,
        )
    except (
        ProfileNotFoundError,
        ReferenceNotOwnedError,
        ReferenceMetadataUnavailableError,
    ) as error:
        raise_reference_read_error(error)

    return _reference_details_response(details)


@router.get(
    "/references/{steam_app_id}/keywords",
    response_model=KeywordSearchResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
def search_keywords(
    steam_app_id: PositivePathIdentifier,
    query: RequiredSearchQuery,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> KeywordSearchResponse:
    """Search cached keywords linked to one ready owned reference."""
    try:
        keywords = search_reference_keywords(
            database_session,
            access_session.profile_id,
            steam_app_id,
            query,
        )
    except (
        InvalidSearchQueryError,
        ProfileNotFoundError,
        ReferenceNotOwnedError,
        ReferenceMetadataUnavailableError,
    ) as error:
        raise_reference_read_error(error)

    return KeywordSearchResponse(
        items=tuple(_facet_option_response(keyword) for keyword in keywords)
    )


@router.get(
    "/references/{steam_app_id}/keywords/browse",
    response_model=KeywordBrowseResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
def browse_keywords(
    steam_app_id: PositivePathIdentifier,
    access_session: Annotated[
        ActiveAccessSession,
        Depends(require_access_session),
    ],
    database_session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> KeywordBrowseResponse:
    """Return cached keywords for browsing one ready owned reference."""
    try:
        keyword_browse = browse_reference_keywords(
            database_session,
            access_session.profile_id,
            steam_app_id,
        )
    except (
        ProfileNotFoundError,
        ReferenceNotOwnedError,
        ReferenceMetadataUnavailableError,
    ) as error:
        raise_reference_read_error(error)

    return KeywordBrowseResponse(
        items=tuple(
            _facet_option_response(keyword)
            for keyword in keyword_browse.items
        ),
        truncated=keyword_browse.truncated,
    )


def _owned_game_suggestion_response(
    suggestion: OwnedGameSuggestion,
) -> OwnedGameSuggestionResponse:
    """Convert one domain suggestion into its public response."""
    return OwnedGameSuggestionResponse(
        steam_app_id=suggestion.steam_app_id,
        name=suggestion.name,
        cover_url=suggestion.cover_url,
        metadata_status=suggestion.metadata_status,
    )


def _facet_option_response(option: FacetOption) -> FacetOptionResponse:
    """Convert one domain facet option into its public response."""
    return FacetOptionResponse(id=option.id, name=option.name)


def _reference_details_response(
    details: ReferenceDetails,
) -> ReferenceDetailsResponse:
    """Convert domain reference details into their public response."""
    return ReferenceDetailsResponse(
        steam_app_id=details.steam_app_id,
        name=details.name,
        cover_url=details.cover_url,
        metadata_status=details.metadata_status,
        facets=ReferenceFacetsResponse(
            genres=tuple(
                _facet_option_response(option)
                for option in details.facets.genres
            ),
            themes=tuple(
                _facet_option_response(option)
                for option in details.facets.themes
            ),
            game_modes=tuple(
                _facet_option_response(option)
                for option in details.facets.game_modes
            ),
        ),
    )
