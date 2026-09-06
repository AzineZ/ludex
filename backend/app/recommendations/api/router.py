from fastapi import APIRouter

from app.recommendations.api.common import STANDARD_ERROR_RESPONSES
from app.recommendations.api.preferences import router as preferences_router
from app.recommendations.api.references import router as references_router
from app.recommendations.api.results import (
    create_final_recommendations,
    router as results_router,
)
from app.recommendations.api.schemas import FinalRecommendationResponse
from app.recommendations.api.validation import RecommendationAPIRoute


router = APIRouter(
    prefix="/recommendations",
    tags=["recommendations"],
    route_class=RecommendationAPIRoute,
)
router.add_api_route(
    "",
    create_final_recommendations,
    methods=["POST"],
    response_model=FinalRecommendationResponse,
    responses=STANDARD_ERROR_RESPONSES,
)
router.include_router(results_router)
router.include_router(references_router)
router.include_router(preferences_router)
