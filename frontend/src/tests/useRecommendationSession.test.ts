import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
   FinalRecommendationItemResponse,
   RecommendationPreference,
} from "../api";
import { useRecommendationSession } from "../features/recommendations/useRecommendationSession";


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
      maximum_completion_minutes: 1200,
      play_status: "either",
   },
};

function recommendationItems(
   count: number,
   steamAppIdBase = 1000
): FinalRecommendationItemResponse[] {
   return Array.from({ length: count }, (_, index) => ({
      rank: index + 1,
      steam_app_id: steamAppIdBase + index + 1,
      title: `Game ${index + 1}`,
      cover_url: null,
      profile_playtime_minutes: 0,
      normal_completion_seconds: null,
      factual_evidence: {
         version: "factual-overlap-v1",
         score_basis_points: 10000 - index,
         active_budget: 100,
         contributions: [],
      },
      facet_labels: [],
      match_summary: {
         reasons: [],
         additional_match_count: 0,
         text: `Game ${index + 1} matches.`,
      },
      tradeoff: null,
   }));
}

describe("useRecommendationSession", () => {
   it("owns initialization and the local Show another transition", () => {
      const { result } = renderHook(() => useRecommendationSession(7));

      expect(result.current.state.phase).toBe("idle");

      act(() => result.current.initialize(preference, recommendationItems(6)));
      expect(result.current.state.phase).toBe("active");
      expect(result.current.state.visibleItems.map((item) => item.steam_app_id))
         .toEqual([1001, 1002, 1003]);
      expect(result.current.state.waitingItems.map((item) => item.steam_app_id))
         .toEqual([1004, 1005, 1006]);

      act(() => result.current.showAnother(1002));
      expect(result.current.state.visibleItems.map((item) => item.steam_app_id))
         .toEqual([1001, 1004, 1003]);
      expect(result.current.state.rejectedSteamAppIds).toEqual([1002]);
   });

   it("owns terminal acceptance and a complete Start over reset", () => {
      const { result } = renderHook(() => useRecommendationSession(7));

      act(() => result.current.initialize(preference, recommendationItems(3)));
      act(() => result.current.playThis(1003));

      expect(result.current.state.phase).toBe("accepted");
      expect(result.current.state.acceptedItem?.steam_app_id).toBe(1003);

      act(() => result.current.startOver());
      expect(result.current.state).toEqual({
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

   it("clears recommendation state when the access-session epoch changes", () => {
      const { result, rerender } = renderHook(
         ({ sessionEpoch }) => useRecommendationSession(sessionEpoch),
         { initialProps: { sessionEpoch: 7 } }
      );
      act(() => result.current.initialize(preference, recommendationItems(3)));

      rerender({ sessionEpoch: 8 });

      expect(result.current.state.phase).toBe("idle");
      expect(result.current.state.visibleItems).toEqual([]);
   });

   it("owns editing and atomically promotes a successful refinement", () => {
      const { result } = renderHook(() => useRecommendationSession(7));
      act(() => result.current.initialize(preference, recommendationItems(6)));
      act(() => result.current.showAnother(1002));

      act(() => result.current.updateDraft(refinedPreference));
      expect(result.current.state.phase).toBe("editing");

      act(() => result.current.beginRefinement(refinedPreference));
      expect(result.current.state.phase).toBe("refining");
      expect(result.current.state.pendingPreference).toEqual(refinedPreference);

      act(() => result.current.completeRefinement(recommendationItems(3, 2000)));
      expect(result.current.state.phase).toBe("active");
      expect(result.current.state.currentPreference).toEqual(refinedPreference);
      expect(result.current.state.visibleItems.map((item) => item.steam_app_id))
         .toEqual([2001, 2002, 2003]);
      expect(result.current.state.rejectedSteamAppIds).toEqual([1002]);
   });

   it("returns a failed refinement to editing without losing its queue", () => {
      const { result } = renderHook(() => useRecommendationSession(7));
      act(() => result.current.initialize(preference, recommendationItems(6)));
      act(() => result.current.showAnother(1002));
      act(() => result.current.updateDraft(refinedPreference));
      act(() => result.current.beginRefinement(refinedPreference));

      act(() => result.current.failRefinement());

      expect(result.current.state.phase).toBe("editing");
      expect(result.current.state.pendingPreference).toBeNull();
      expect(result.current.state.visibleItems.map((item) => item.steam_app_id))
         .toEqual([1001, 1004, 1003]);
      expect(result.current.state.waitingItems.map((item) => item.steam_app_id))
         .toEqual([1005, 1006]);
      expect(result.current.state.rejectedSteamAppIds).toEqual([1002]);
   });
});
