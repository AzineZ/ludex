import { describe, expect, it } from "vitest";

import type {
   FinalRecommendationItemResponse,
   RecommendationPreference,
} from "../api";
import {
   createRecommendationSession,
   showAnotherRecommendation,
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

function recommendationItems(count: number): FinalRecommendationItemResponse[] {
   return Array.from({ length: count }, (_, index) => (
      recommendationItem(index + 1)
   ));
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
