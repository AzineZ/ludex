import type {
   AutomaticRecommendationResponse,
   AutomaticRecommendationRowResponse,
   FinalRecommendationItemResponse,
   RecommendationPreference,
} from "../../api";

export function automaticItem(
   steamAppId: number,
   rank = 1
): FinalRecommendationItemResponse {
   return {
      rank,
      steam_app_id: steamAppId,
      title: `Game ${steamAppId}`,
      cover_url: null,
      profile_playtime_minutes: 0,
      normal_completion_seconds: null,
      factual_evidence: {
         version: "factual-overlap-v1",
         score_basis_points: 10000 - rank,
         active_budget: 100,
         contributions: [],
      },
      facet_labels: [],
      match_summary: {
         reasons: [],
         additional_match_count: 0,
         text: `Why Game ${steamAppId} matches.`,
      },
      tradeoff: null,
   };
}

export function automaticRowResponse(
   sourceSteamAppId: number,
   itemSteamAppIds: readonly number[],
   playtimeMinutes = 600
): AutomaticRecommendationRowResponse {
   return {
      source_game: {
         steam_app_id: sourceSteamAppId,
         title: `Source ${sourceSteamAppId}`,
         cover_url: null,
         playtime_minutes: playtimeMinutes,
      },
      recommendations: {
         outcome: itemSteamAppIds.length === 0
            ? "empty"
            : itemSteamAppIds.length < 6
              ? "sparse"
              : "complete",
         eligible_count: itemSteamAppIds.length,
         returned_count: itemSteamAppIds.length,
         items: itemSteamAppIds.map((steamAppId, index) =>
            automaticItem(steamAppId, index + 1)
         ),
      },
   };
}

export const AUTOMATIC_SUGGESTED_PREFERENCE: RecommendationPreference = {
   references: [101, 102, 103].map((steamAppId) => ({
      steam_app_id: steamAppId,
      facets: {
         genre_ids: [10],
         theme_ids: [],
         keyword_ids: [],
         game_mode_ids: [],
      },
   })),
   constraints: { maximum_completion_minutes: null, play_status: "unplayed" },
};

/** Three rows of six ranked games, like the backend's complete response. */
export function readyAutomaticResponse(): AutomaticRecommendationResponse {
   return {
      status: "ready",
      rows: [
         automaticRowResponse(101, [201, 202, 203, 204, 205, 206], 2520),
         automaticRowResponse(102, [207, 208, 209, 210, 211, 212], 600),
         automaticRowResponse(103, [213, 214, 215, 216, 217, 218], 95),
      ],
      suggested_preference: AUTOMATIC_SUGGESTED_PREFERENCE,
   };
}
