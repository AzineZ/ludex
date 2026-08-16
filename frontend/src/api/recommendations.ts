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

function recommendationPath(profileId: number): string {
   return `/profiles/${profileId}/recommendations`;
}

function queryString(query: string): string {
   return new URLSearchParams({ query }).toString();
}

export function searchReferenceGames(
   profileId: number,
   query: string
): Promise<OwnedGameSearchResponse> {
   return requestJson<OwnedGameSearchResponse>(
      `${recommendationPath(profileId)}/references?${queryString(query)}`
   );
}

export function getReferenceDetails(
   profileId: number,
   steamAppId: number
): Promise<ReferenceDetailsResponse> {
   return requestJson<ReferenceDetailsResponse>(
      `${recommendationPath(profileId)}/references/${steamAppId}`
   );
}

export function searchReferenceKeywords(
   profileId: number,
   steamAppId: number,
   query: string
): Promise<KeywordSearchResponse> {
   return requestJson<KeywordSearchResponse>(
      `${recommendationPath(profileId)}/references/${steamAppId}` +
         `/keywords?${queryString(query)}`
   );
}

export function validateRecommendationPreference(
   profileId: number,
   preference: RecommendationPreference
): Promise<RecommendationPreference> {
   return requestJson<RecommendationPreference>(
      `${recommendationPath(profileId)}/preferences/validate`,
      {
         method: "POST",
         headers: {
            "Content-Type": "application/json",
         },
         body: JSON.stringify(preference),
      }
   );
}
