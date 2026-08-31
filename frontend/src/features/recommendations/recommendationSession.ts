import type {
   FinalRecommendationItemResponse,
   RecommendationPreference,
} from "../../api";


const INITIAL_VISIBLE_COUNT = 3;

export type ActiveRecommendationSession = {
   phase: "active";
   currentPreference: RecommendationPreference;
   pendingPreference: null;
   visibleItems: readonly FinalRecommendationItemResponse[];
   waitingItems: readonly FinalRecommendationItemResponse[];
   shownSteamAppIds: readonly number[];
   rejectedSteamAppIds: readonly number[];
   acceptedItem: null;
};

function assertUniqueGameIds(
   items: readonly FinalRecommendationItemResponse[]
): void {
   const uniqueIds = new Set(items.map((item) => item.steam_app_id));
   if (uniqueIds.size !== items.length) {
      throw new Error("Recommendation queues must contain unique game IDs.");
   }
}

export function createRecommendationSession(
   preference: RecommendationPreference,
   items: readonly FinalRecommendationItemResponse[]
): ActiveRecommendationSession {
   assertUniqueGameIds(items);

   const visibleItems = items.slice(0, INITIAL_VISIBLE_COUNT);
   return {
      phase: "active",
      currentPreference: preference,
      pendingPreference: null,
      visibleItems,
      waitingItems: items.slice(INITIAL_VISIBLE_COUNT),
      shownSteamAppIds: visibleItems.map((item) => item.steam_app_id),
      rejectedSteamAppIds: [],
      acceptedItem: null,
   };
}

export function showAnotherRecommendation(
   state: ActiveRecommendationSession,
   rejectedSteamAppId: number
): ActiveRecommendationSession {
   if (state.waitingItems.length === 0) {
      return state;
   }

   const rejectedIndex = state.visibleItems.findIndex(
      (item) => item.steam_app_id === rejectedSteamAppId
   );
   if (rejectedIndex < 0) {
      throw new Error("Show another requires a currently visible game.");
   }

   const replacement = state.waitingItems[0];
   const visibleItems = [...state.visibleItems];
   visibleItems[rejectedIndex] = replacement;

   return {
      ...state,
      visibleItems,
      waitingItems: state.waitingItems.slice(1),
      shownSteamAppIds: [
         ...state.shownSteamAppIds,
         replacement.steam_app_id,
      ],
      rejectedSteamAppIds: [
         ...state.rejectedSteamAppIds,
         rejectedSteamAppId,
      ],
   };
}
