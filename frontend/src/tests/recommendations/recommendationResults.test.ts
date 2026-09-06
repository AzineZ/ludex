import { describe, expect, it } from "vitest";

import type { FinalRecommendationItemResponse } from "../../api";
import { splitRecommendationItems } from "../../features/recommendations/results/recommendationResults";


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
         text: `Why Game ${rank} matches.`,
      },
      tradeoff: null,
   };
}

describe("splitRecommendationItems", () => {
   it("places the first three ordered results in the visible set", () => {
      const items = Array.from({ length: 6 }, (_, index) => (
         recommendationItem(index + 1)
      ));

      const result = splitRecommendationItems(items);

      expect(result.visibleItems.map((item) => item.rank)).toEqual([1, 2, 3]);
   });

   it("places later ordered results in the waiting set", () => {
      const items = Array.from({ length: 6 }, (_, index) => (
         recommendationItem(index + 1)
      ));

      const result = splitRecommendationItems(items);

      expect(result.waitingItems.map((item) => item.rank)).toEqual([4, 5, 6]);
   });

   it("keeps sparse results visible without manufacturing waiting games", () => {
      const items = [recommendationItem(1), recommendationItem(2)];

      expect(splitRecommendationItems(items)).toEqual({
         visibleItems: items,
         waitingItems: [],
      });
   });

   it("returns two empty sets for an empty recommendation result", () => {
      expect(splitRecommendationItems([])).toEqual({
         visibleItems: [],
         waitingItems: [],
      });
   });

   it("does not reorder or mutate the backend result array", () => {
      const items = [
         recommendationItem(3),
         recommendationItem(1),
         recommendationItem(2),
         recommendationItem(6),
      ];
      const originalOrder = [...items];

      const result = splitRecommendationItems(items);

      expect(result.visibleItems).toEqual(items.slice(0, 3));
      expect(result.waitingItems).toEqual(items.slice(3));
      expect(items).toEqual(originalOrder);
   });
});
