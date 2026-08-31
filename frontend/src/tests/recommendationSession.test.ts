import { describe, expect, it } from "vitest";

import type {
   FinalRecommendationItemResponse,
   RecommendationPreference,
} from "../api";
import {
   acceptRecommendation,
   beginRecommendationRefinement,
   completeRecommendationRefinement,
   createRecommendationSession,
   failRecommendationRefinement,
   showAnotherRecommendation,
   startOverRecommendationSession,
   type ActiveRecommendationSession,
   type EditingRecommendationSession,
   updateRecommendationSessionDraft,
} from "../features/recommendations/recommendationSession";


const preference: RecommendationPreference = {
   references: [
      {
         steam_app_id: 100,
         facets: {
            genre_ids: [10],
            theme_ids: [],
            keyword_ids: [],
            game_mode_ids: [],
         },
      },
   ],
   constraints: {
      maximum_completion_minutes: null,
      play_status: "either",
   },
};

const refinedPreference: RecommendationPreference = {
   ...preference,
   constraints: {
      maximum_completion_minutes: 1800,
      play_status: "either",
   },
};

function recommendationItem(rank: number): FinalRecommendationItemResponse {
   return {
      rank,
      steam_app_id: 1000 + rank,
      title: `Game ${rank}`,
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
         text: `Game ${rank} matches.`,
      },
      tradeoff: null,
   };
}

function recommendationItems(
   count: number,
   steamAppIdBase = 1000
): FinalRecommendationItemResponse[] {
   return Array.from({ length: count }, (_, index) => (
      {
         ...recommendationItem(index + 1),
         steam_app_id: steamAppIdBase + index + 1,
      }
   ));
}

function assertEditing(
   state: ActiveRecommendationSession | EditingRecommendationSession
): asserts state is EditingRecommendationSession {
   expect(state.phase).toBe("editing");
}

describe("recommendation session initialization", () => {
   it("creates the complete visible and waiting queue without mutating input", () => {
      const items = recommendationItems(6);
      const originalItems = [...items];

      const state = createRecommendationSession(preference, items);

      expect(state.phase).toBe("active");
      expect(state.currentPreference).toBe(preference);
      expect(state.pendingPreference).toBeNull();
      expect(state.visibleItems.map((item) => item.rank)).toEqual([1, 2, 3]);
      expect(state.waitingItems.map((item) => item.rank)).toEqual([4, 5, 6]);
      expect(state.shownSteamAppIds).toEqual([1001, 1002, 1003]);
      expect(state.rejectedSteamAppIds).toEqual([]);
      expect(state.acceptedItem).toBeNull();
      expect(items).toEqual(originalItems);
      expect(state.visibleItems).not.toBe(items);
   });

   it("represents sparse and empty successful queues honestly", () => {
      const sparse = createRecommendationSession(
         preference,
         recommendationItems(2)
      );
      const empty = createRecommendationSession(preference, []);

      expect(sparse.visibleItems.map((item) => item.rank)).toEqual([1, 2]);
      expect(sparse.waitingItems).toEqual([]);
      expect(sparse.shownSteamAppIds).toEqual([1001, 1002]);
      expect(empty.visibleItems).toEqual([]);
      expect(empty.waitingItems).toEqual([]);
      expect(empty.shownSteamAppIds).toEqual([]);
   });

   it("rejects a backend queue containing duplicate game identities", () => {
      const duplicate = recommendationItem(2);
      duplicate.steam_app_id = 1001;

      expect(() => createRecommendationSession(
         preference,
         [recommendationItem(1), duplicate]
      )).toThrow("Recommendation queues must contain unique game IDs.");
   });

   it("rejects a backend queue larger than the fixed six-game boundary", () => {
      expect(() => createRecommendationSession(
         preference,
         recommendationItems(7)
      )).toThrow("Recommendation queues cannot contain more than six games.");
   });
});

describe("Show another", () => {
   it("rejects one visible game and consumes the waiting head in its slot", () => {
      const initial = createRecommendationSession(
         preference,
         recommendationItems(6)
      );

      const next = showAnotherRecommendation(initial, 1002);

      expect(next.visibleItems.map((item) => item.rank)).toEqual([1, 4, 3]);
      expect(next.waitingItems.map((item) => item.rank)).toEqual([5, 6]);
      expect(next.shownSteamAppIds).toEqual([1001, 1002, 1003, 1004]);
      expect(next.rejectedSteamAppIds).toEqual([1002]);
      expect(next.currentPreference).toBe(preference);
      expect(initial.visibleItems.map((item) => item.rank)).toEqual([1, 2, 3]);
      expect(initial.waitingItems.map((item) => item.rank)).toEqual([4, 5, 6]);
   });

   it("consumes each replacement at most once across repeated transitions", () => {
      const initial = createRecommendationSession(
         preference,
         recommendationItems(6)
      );

      const second = showAnotherRecommendation(initial, 1002);
      const third = showAnotherRecommendation(second, 1004);
      const exhausted = showAnotherRecommendation(third, 1005);

      expect(exhausted.visibleItems.map((item) => item.rank)).toEqual([1, 6, 3]);
      expect(exhausted.waitingItems).toEqual([]);
      expect(exhausted.shownSteamAppIds).toEqual([
         1001,
         1002,
         1003,
         1004,
         1005,
         1006,
      ]);
      expect(exhausted.rejectedSteamAppIds).toEqual([1002, 1004, 1005]);
   });

   it("does not reject a visible game after the queue is exhausted", () => {
      const initial = createRecommendationSession(
         preference,
         recommendationItems(3)
      );

      expect(showAnotherRecommendation(initial, 1002)).toBe(initial);
      expect(initial.rejectedSteamAppIds).toEqual([]);
   });

   it("rejects an impossible replacement target that is not visible", () => {
      const initial = createRecommendationSession(
         preference,
         recommendationItems(6)
      );

      expect(() => showAnotherRecommendation(initial, 1006)).toThrow(
         "Show another requires a currently visible game."
      );
   });
});

describe("Play this", () => {
   it("accepts exactly one visible game and preserves the session record", () => {
      const initial = createRecommendationSession(
         preference,
         recommendationItems(6)
      );
      const replaced = showAnotherRecommendation(initial, 1002);

      const accepted = acceptRecommendation(replaced, 1004);

      expect(accepted.phase).toBe("accepted");
      expect(accepted.acceptedItem).toBe(replaced.visibleItems[1]);
      expect(accepted.currentPreference).toBe(preference);
      expect(accepted.visibleItems).toBe(replaced.visibleItems);
      expect(accepted.waitingItems).toBe(replaced.waitingItems);
      expect(accepted.shownSteamAppIds).toEqual([1001, 1002, 1003, 1004]);
      expect(accepted.rejectedSteamAppIds).toEqual([1002]);
   });

   it("rejects an acceptance target that is not currently visible", () => {
      const initial = createRecommendationSession(
         preference,
         recommendationItems(6)
      );

      expect(() => acceptRecommendation(initial, 1006)).toThrow(
         "Play this requires a currently visible game."
      );
   });
});

describe("Start over", () => {
   it("clears every active session field while preserving no preference", () => {
      const active = showAnotherRecommendation(
         createRecommendationSession(preference, recommendationItems(6)),
         1002
      );

      const idle = startOverRecommendationSession(active);

      expect(idle).toEqual({
         phase: "idle",
         currentPreference: null,
         pendingPreference: null,
         visibleItems: [],
         waitingItems: [],
         shownSteamAppIds: [],
         rejectedSteamAppIds: [],
         acceptedItem: null,
      });
   });

   it("is the only transition that clears an accepted session", () => {
      const active = createRecommendationSession(
         preference,
         recommendationItems(3)
      );
      const accepted = acceptRecommendation(active, 1001);

      expect(startOverRecommendationSession(accepted).phase).toBe("idle");
   });
});

describe("preference editing", () => {
   it("invalidates an active queue for a different draft without discarding it", () => {
      const active = createRecommendationSession(
         preference,
         recommendationItems(6)
      );

      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);

      expect(editing.currentPreference).toBe(preference);
      expect(editing.pendingPreference).toBeNull();
      expect(editing.visibleItems).toBe(active.visibleItems);
      expect(editing.waitingItems).toBe(active.waitingItems);
   });

   it("keeps an identical draft active and restores one that is reverted", () => {
      const active = createRecommendationSession(
         preference,
         recommendationItems(6)
      );

      expect(
         updateRecommendationSessionDraft(active, structuredClone(preference))
      ).toBe(active);

      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);
      const restored = updateRecommendationSessionDraft(editing, preference);

      expect(restored.phase).toBe("active");
      expect(restored.visibleItems).toBe(active.visibleItems);
      expect(restored.waitingItems).toBe(active.waitingItems);
   });
});

describe("recommendation refinement", () => {
   it("starts only a genuine refinement and preserves rejected exclusions", () => {
      const active = showAnotherRecommendation(
         createRecommendationSession(preference, recommendationItems(6)),
         1002
      );
      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);

      const refining = beginRecommendationRefinement(
         editing,
         refinedPreference
      );

      expect(refining.phase).toBe("refining");
      expect(refining.currentPreference).toBe(preference);
      expect(refining.pendingPreference).toBe(refinedPreference);
      expect(refining.rejectedSteamAppIds).toEqual([1002]);
      expect(() => beginRecommendationRefinement(editing, preference)).toThrow(
         "Refinement requires a preference different from the current one."
      );
   });

   it("promotes a successful preference and replaces the bounded queue", () => {
      const active = showAnotherRecommendation(
         createRecommendationSession(preference, recommendationItems(6)),
         1002
      );
      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);
      const refining = beginRecommendationRefinement(
         editing,
         refinedPreference
      );
      const refinedItems = recommendationItems(5, 2000);

      const next = completeRecommendationRefinement(refining, refinedItems);

      expect(next.phase).toBe("active");
      expect(next.currentPreference).toBe(refinedPreference);
      expect(next.pendingPreference).toBeNull();
      expect(next.visibleItems.map((item) => item.steam_app_id)).toEqual([
         2001,
         2002,
         2003,
      ]);
      expect(next.waitingItems.map((item) => item.steam_app_id)).toEqual([
         2004,
         2005,
      ]);
      expect(next.shownSteamAppIds).toEqual([
         1001,
         1002,
         1003,
         1004,
         2001,
         2002,
         2003,
      ]);
      expect(next.rejectedSteamAppIds).toEqual([1002]);
      expect(refinedItems).toHaveLength(5);
   });

   it("allows an honest empty refinement while retaining session history", () => {
      const active = showAnotherRecommendation(
         createRecommendationSession(preference, recommendationItems(4)),
         1001
      );
      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);
      const refining = beginRecommendationRefinement(
         editing,
         refinedPreference
      );

      const empty = completeRecommendationRefinement(refining, []);

      expect(empty.phase).toBe("active");
      expect(empty.visibleItems).toEqual([]);
      expect(empty.waitingItems).toEqual([]);
      expect(empty.shownSteamAppIds).toEqual([1001, 1002, 1003, 1004]);
      expect(empty.rejectedSteamAppIds).toEqual([1001]);
   });

   it("rejects a refinement response containing a session-rejected game", () => {
      const active = showAnotherRecommendation(
         createRecommendationSession(preference, recommendationItems(6)),
         1002
      );
      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);
      const refining = beginRecommendationRefinement(
         editing,
         refinedPreference
      );
      const rejectedItem = recommendationItem(1);
      rejectedItem.steam_app_id = 1002;

      expect(() => completeRecommendationRefinement(
         refining,
         [rejectedItem]
      )).toThrow("Refined queues cannot contain a rejected game ID.");
   });

   it("returns a failed refinement to editing without losing prior state", () => {
      const active = showAnotherRecommendation(
         createRecommendationSession(preference, recommendationItems(6)),
         1002
      );
      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);
      const refining = beginRecommendationRefinement(
         editing,
         refinedPreference
      );

      const failed = failRecommendationRefinement(refining);

      expect(failed.phase).toBe("editing");
      expect(failed.currentPreference).toBe(preference);
      expect(failed.pendingPreference).toBeNull();
      expect(failed.visibleItems).toBe(active.visibleItems);
      expect(failed.waitingItems).toBe(active.waitingItems);
      expect(failed.shownSteamAppIds).toBe(active.shownSteamAppIds);
      expect(failed.rejectedSteamAppIds).toBe(active.rejectedSteamAppIds);
   });

   it("allows a shown non-rejected game without duplicating shown history", () => {
      const active = createRecommendationSession(
         preference,
         recommendationItems(3)
      );
      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);
      const refining = beginRecommendationRefinement(
         editing,
         refinedPreference
      );
      const repeated = recommendationItems(3, 2000);
      repeated[0] = recommendationItem(1);

      const next = completeRecommendationRefinement(refining, repeated);

      expect(next.visibleItems[0].steam_app_id).toBe(1001);
      expect(next.shownSteamAppIds).toEqual([
         1001,
         1002,
         1003,
         2002,
         2003,
      ]);
   });

   it("rejects an oversized refined queue", () => {
      const active = createRecommendationSession(
         preference,
         recommendationItems(3)
      );
      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);
      const refining = beginRecommendationRefinement(
         editing,
         refinedPreference
      );

      expect(() => completeRecommendationRefinement(
         refining,
         recommendationItems(7, 2000)
      )).toThrow("Recommendation queues cannot contain more than six games.");
   });

   it("can start over while editing or while a refinement is pending", () => {
      const active = createRecommendationSession(
         preference,
         recommendationItems(3)
      );
      const editing = updateRecommendationSessionDraft(
         active,
         refinedPreference
      );
      assertEditing(editing);
      const refining = beginRecommendationRefinement(
         editing,
         refinedPreference
      );

      expect(startOverRecommendationSession(editing).phase).toBe("idle");
      expect(startOverRecommendationSession(refining).phase).toBe("idle");
   });
});
