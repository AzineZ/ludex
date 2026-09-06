import type {
   FinalRecommendationItemResponse,
   RecommendationPreference,
} from "../../../api";

const INITIAL_VISIBLE_COUNT = 3;
const MAX_RECOMMENDATION_COUNT = 6;

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

export type AcceptedRecommendationSession = Omit<
   ActiveRecommendationSession,
   "phase" | "acceptedItem"
> & {
   phase: "accepted";
   acceptedItem: FinalRecommendationItemResponse;
};

export type EditingRecommendationSession = Omit<
   ActiveRecommendationSession,
   "phase"
> & {
   phase: "editing";
};

export type RefiningRecommendationSession = Omit<
   ActiveRecommendationSession,
   "phase" | "pendingPreference"
> & {
   phase: "refining";
   pendingPreference: RecommendationPreference;
};

export type IdleRecommendationSession = {
   phase: "idle";
   currentPreference: null;
   pendingPreference: null;
   visibleItems: readonly FinalRecommendationItemResponse[];
   waitingItems: readonly FinalRecommendationItemResponse[];
   shownSteamAppIds: readonly number[];
   rejectedSteamAppIds: readonly number[];
   acceptedItem: null;
};

export type RecommendationSessionState =
   | IdleRecommendationSession
   | ActiveRecommendationSession
   | AcceptedRecommendationSession
   | EditingRecommendationSession
   | RefiningRecommendationSession;

export function createIdleRecommendationSession(): IdleRecommendationSession {
   return {
      phase: "idle",
      currentPreference: null,
      pendingPreference: null,
      visibleItems: [],
      waitingItems: [],
      shownSteamAppIds: [],
      rejectedSteamAppIds: [],
      acceptedItem: null,
   };
}

function assertValidQueue(
   items: readonly FinalRecommendationItemResponse[]
): void {
   if (items.length > MAX_RECOMMENDATION_COUNT) {
      throw new Error(
         "Recommendation queues cannot contain more than six games."
      );
   }
   const uniqueIds = new Set(items.map((item) => item.steam_app_id));
   if (uniqueIds.size !== items.length) {
      throw new Error("Recommendation queues must contain unique game IDs.");
   }
}

function preferencesAreEqual(
   first: RecommendationPreference,
   second: RecommendationPreference
): boolean {
   return JSON.stringify(first) === JSON.stringify(second);
}

function appendUniqueIds(
   existingIds: readonly number[],
   addedIds: readonly number[]
): number[] {
   const result = [...existingIds];
   const knownIds = new Set(existingIds);
   for (const addedId of addedIds) {
      if (!knownIds.has(addedId)) {
         result.push(addedId);
         knownIds.add(addedId);
      }
   }
   return result;
}

export function createRecommendationSession(
   preference: RecommendationPreference,
   items: readonly FinalRecommendationItemResponse[]
): ActiveRecommendationSession {
   assertValidQueue(items);

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

export function acceptRecommendation(
   state: ActiveRecommendationSession,
   acceptedSteamAppId: number
): AcceptedRecommendationSession {
   const acceptedItem = state.visibleItems.find(
      (item) => item.steam_app_id === acceptedSteamAppId
   );
   if (acceptedItem === undefined) {
      throw new Error("Play this requires a currently visible game.");
   }

   return {
      ...state,
      phase: "accepted",
      acceptedItem,
   };
}

export function startOverRecommendationSession(
   state: RecommendationSessionState
): IdleRecommendationSession {
   void state;
   return createIdleRecommendationSession();
}

export function updateRecommendationSessionDraft(
   state: ActiveRecommendationSession | EditingRecommendationSession,
   draftPreference: RecommendationPreference
): ActiveRecommendationSession | EditingRecommendationSession {
   const matchesCurrentPreference = preferencesAreEqual(
      state.currentPreference,
      draftPreference
   );
   if (matchesCurrentPreference && state.phase === "active") {
      return state;
   }
   if (!matchesCurrentPreference && state.phase === "editing") {
      return state;
   }

   return {
      ...state,
      phase: matchesCurrentPreference ? "active" : "editing",
   };
}

export function beginRecommendationRefinement(
   state: EditingRecommendationSession,
   validatedPreference: RecommendationPreference
): RefiningRecommendationSession {
   if (preferencesAreEqual(state.currentPreference, validatedPreference)) {
      throw new Error(
         "Refinement requires a preference different from the current one."
      );
   }

   return {
      ...state,
      phase: "refining",
      pendingPreference: validatedPreference,
   };
}

export function completeRecommendationRefinement(
   state: RefiningRecommendationSession,
   items: readonly FinalRecommendationItemResponse[]
): ActiveRecommendationSession {
   assertValidQueue(items);
   const rejectedIds = new Set(state.rejectedSteamAppIds);
   if (items.some((item) => rejectedIds.has(item.steam_app_id))) {
      throw new Error("Refined queues cannot contain a rejected game ID.");
   }

   const visibleItems = items.slice(0, INITIAL_VISIBLE_COUNT);
   return {
      phase: "active",
      currentPreference: state.pendingPreference,
      pendingPreference: null,
      visibleItems,
      waitingItems: items.slice(INITIAL_VISIBLE_COUNT),
      shownSteamAppIds: appendUniqueIds(
         state.shownSteamAppIds,
         visibleItems.map((item) => item.steam_app_id)
      ),
      rejectedSteamAppIds: state.rejectedSteamAppIds,
      acceptedItem: null,
   };
}

export function failRecommendationRefinement(
   state: RefiningRecommendationSession
): EditingRecommendationSession {
   return {
      ...state,
      phase: "editing",
      pendingPreference: null,
   };
}
