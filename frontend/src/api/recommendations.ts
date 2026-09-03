import { requestJson } from "./client";

export type MetadataStatus = "pending" | "ready" | "missing" | "ambiguous";

export type PlayStatus = "unplayed" | "previously_played" | "either";

export type RecommendationErrorCode =
   | "missing_field"
   | "unexpected_field"
   | "invalid_type"
   | "invalid_value"
   | "invalid_reference_count"
   | "duplicate_reference"
   | "duplicate_facet"
   | "empty_reference_facets"
   | "too_many_keywords"
   | "duplicate_rejected_game"
   | "too_many_rejected_games"
   | "invalid_query"
   | "profile_not_found"
   | "reference_not_owned"
   | "reference_metadata_unavailable"
   | "facet_not_on_reference";

export type OwnedGameSuggestionResponse = {
   steam_app_id: number;
   name: string;
   cover_url: string | null;
   metadata_status: MetadataStatus;
};

export type OwnedGameSearchResponse = {
   items: OwnedGameSuggestionResponse[];
};

export type FacetOptionResponse = {
   id: number;
   name: string;
};

export type KeywordSearchResponse = {
   items: FacetOptionResponse[];
};

export type KeywordBrowseResponse = {
   items: FacetOptionResponse[];
   truncated: boolean;
};

export type ReferenceFacetsResponse = {
   genres: FacetOptionResponse[];
   themes: FacetOptionResponse[];
   game_modes: FacetOptionResponse[];
};

export type ReferenceDetailsResponse = {
   steam_app_id: number;
   name: string;
   cover_url: string | null;
   metadata_status: MetadataStatus;
   facets: ReferenceFacetsResponse;
};

export type SelectedFacets = {
   genre_ids: number[];
   theme_ids: number[];
   keyword_ids: number[];
   game_mode_ids: number[];
};

export type ReferencePreference = {
   steam_app_id: number;
   facets: SelectedFacets;
};

export type PreferenceConstraints = {
   maximum_completion_minutes: number | null;
   play_status: PlayStatus;
};

export type RecommendationPreference = {
   references: ReferencePreference[];
   constraints: PreferenceConstraints;
};

export type FacetKind = "genre" | "theme" | "keyword" | "game_mode";

export type FacetMatchState = "matched" | "not_matched" | "unknown";

export type RecommendationOutcome = "complete" | "sparse" | "empty";

export type FactualContributionResponse = {
   reference_steam_app_id: number;
   facet_kind: FacetKind;
   facet_igdb_id: number;
   match_state: FacetMatchState;
   points_numerator: number;
   points_denominator: number;
};

export type FactualScoreEvidenceResponse = {
   version: string;
   score_basis_points: number;
   active_budget: number;
   contributions: FactualContributionResponse[];
};

export type FacetLabelResponse = {
   facet_kind: FacetKind;
   facet_igdb_id: number;
   name: string;
};

export type MatchReasonResponse = FacetLabelResponse & {
   reference_steam_app_ids: number[];
   points_numerator: number;
   points_denominator: number;
};

export type MatchSummaryResponse = {
   reasons: MatchReasonResponse[];
   additional_match_count: number;
   text: string;
};

export type UnmatchedPreferenceReasonResponse = FacetLabelResponse & {
   reference_steam_app_ids: number[];
};

export type UnknownPreferenceMetadataTradeoffResponse = {
   type: "unknown_preference_metadata";
   facet_kinds: FacetKind[];
   text: string;
};

export type UnmatchedPreferenceTradeoffResponse = {
   type: "unmatched_preference";
   reason: UnmatchedPreferenceReasonResponse;
   text: string;
};

export type UnknownCompletionTimeTradeoffResponse = {
   type: "unknown_completion_time";
   text: string;
};

export type RecommendationTradeoffResponse =
   | UnknownPreferenceMetadataTradeoffResponse
   | UnmatchedPreferenceTradeoffResponse
   | UnknownCompletionTimeTradeoffResponse;

export type FinalRecommendationItemResponse = {
   rank: number;
   steam_app_id: number;
   title: string;
   cover_url: string | null;
   profile_playtime_minutes: number;
   normal_completion_seconds: number | null;
   factual_evidence: FactualScoreEvidenceResponse;
   facet_labels: FacetLabelResponse[];
   match_summary: MatchSummaryResponse;
   tradeoff: RecommendationTradeoffResponse | null;
};

export type FinalRecommendationResponse = {
   outcome: RecommendationOutcome;
   eligible_count: number;
   returned_count: number;
   items: FinalRecommendationItemResponse[];
};

export type RecommendationRefinementRequest = {
   preference: RecommendationPreference;
   rejected_steam_app_ids: number[];
};

const recommendationPath = "/recommendations";

function queryString(query: string): string {
   return new URLSearchParams({ query }).toString();
}

export function searchReferenceGames(
   query: string
): Promise<OwnedGameSearchResponse> {
   return requestJson<OwnedGameSearchResponse>(
      `${recommendationPath}/references?${queryString(query)}`
   );
}

export function getReferenceDetails(
   steamAppId: number
): Promise<ReferenceDetailsResponse> {
   return requestJson<ReferenceDetailsResponse>(
      `${recommendationPath}/references/${steamAppId}`
   );
}

export function searchReferenceKeywords(
   steamAppId: number,
   query: string
): Promise<KeywordSearchResponse> {
   return requestJson<KeywordSearchResponse>(
      `${recommendationPath}/references/${steamAppId}` +
         `/keywords?${queryString(query)}`
   );
}

export function getReferenceKeywords(
   steamAppId: number
): Promise<KeywordBrowseResponse> {
   return requestJson<KeywordBrowseResponse>(
      `${recommendationPath}/references/${steamAppId}` +
         "/keywords/browse"
   );
}

export function validateRecommendationPreference(
   preference: RecommendationPreference
): Promise<RecommendationPreference> {
   return requestJson<RecommendationPreference>(
      `${recommendationPath}/preferences/validate`,
      {
         method: "POST",
         headers: {
            "Content-Type": "application/json",
         },
         body: JSON.stringify(preference),
      }
   );
}

export function getFinalRecommendations(
   preference: RecommendationPreference
): Promise<FinalRecommendationResponse> {
   return requestJson<FinalRecommendationResponse>(
      recommendationPath,
      {
         method: "POST",
         headers: {
            "Content-Type": "application/json",
         },
         body: JSON.stringify(preference),
      }
   );
}

export function refineFinalRecommendations(
   preference: RecommendationPreference,
   rejectedSteamAppIds: readonly number[]
): Promise<FinalRecommendationResponse> {
   const refinement: RecommendationRefinementRequest = {
      preference,
      rejected_steam_app_ids: [...rejectedSteamAppIds],
   };
   return requestJson<FinalRecommendationResponse>(
      `${recommendationPath}/refine`,
      {
         method: "POST",
         headers: {
            "Content-Type": "application/json",
         },
         body: JSON.stringify(refinement),
      }
   );
}
