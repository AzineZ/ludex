export { ApiError } from "./client";
export { getHealth, type HealthResponse } from "./health";
export {
   createProfile,
   getProfile,
   listProfiles,
   refreshProfile,
   type OwnedGameResponse,
   type ProfileDetailResponse,
   type ProfileSummaryResponse,
} from "./profiles";
export {
   getReferenceDetails,
   searchReferenceGames,
   searchReferenceKeywords,
   validateRecommendationPreference,
   type FacetOptionResponse,
   type KeywordSearchResponse,
   type MetadataStatus,
   type OwnedGameSearchResponse,
   type OwnedGameSuggestionResponse,
   type PlayStatus,
   type PreferenceConstraints,
   type RecommendationErrorCode,
   type RecommendationPreference,
   type ReferenceDetailsResponse,
   type ReferenceFacetsResponse,
   type ReferencePreference,
   type SelectedFacets,
} from "./recommendations";
