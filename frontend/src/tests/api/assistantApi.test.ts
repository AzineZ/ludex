import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
   getAssistantFilterOptions,
   getAssistantGenres,
   getAssistantRecommendations,
   type AssistantFilterContextRequest,
   type AssistantRecommendationSubmission,
} from "../../api";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(data: unknown): Response {
   return new Response(JSON.stringify(data), {
      status: 200,
      headers: { "Content-Type": "application/json" },
   });
}

describe("assistant API", () => {
   beforeEach(() => {
      fetchMock.mockReset();
      vi.stubGlobal("fetch", fetchMock);
   });

   afterEach(() => {
      vi.unstubAllGlobals();
   });

   it("loads genres from the authorized cached library", async () => {
      const response = {
         items: [{ igdb_id: 31, name: "Adventure", eligible_count: 12 }],
      };
      fetchMock.mockResolvedValue(jsonResponse(response));

      await expect(getAssistantGenres()).resolves.toEqual(response);
      expect(fetchMock).toHaveBeenCalledWith(
         "http://localhost:8000/recommendations/assistant/genres",
         { credentials: "include" }
      );
   });

   it("loads provider-free filter options with the exact context", async () => {
      const request: AssistantFilterContextRequest = {
         selected_genre_id: 31,
         play_status: "unplayed",
         maximum_completion_minutes: 600,
         theme_ids: [17],
         game_mode_ids: [1],
         rejected_steam_app_ids: [101],
      };
      const response = {
         eligible_count: 4,
         candidate_limit: 400,
         themes: [],
         game_modes: [],
      };
      fetchMock.mockResolvedValue(jsonResponse(response));

      await expect(getAssistantFilterOptions(request)).resolves.toEqual(response);
      expect(fetchMock).toHaveBeenCalledWith(
         "http://localhost:8000/recommendations/assistant/filters",
         {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(request),
            credentials: "include",
         }
      );
   });

   it("submits the bounded assistant request without profile identity", async () => {
      const request: AssistantRecommendationSubmission = {
         prompt: "Something relaxing",
         selected_genre_id: 31,
         filters: {
            play_status: "either",
            maximum_completion_minutes: null,
            theme_ids: [17],
            game_mode_ids: [],
         },
         rejected_steam_app_ids: [],
      };
      const response = {
         status: "no_match",
         eligible_count: 4,
         candidate_limit: 400,
         items: [],
         message: "No close fit was found.",
         guided_fallback_available: true,
      };
      fetchMock.mockResolvedValue(jsonResponse(response));

      await expect(getAssistantRecommendations(request)).resolves.toEqual(response);
      expect(fetchMock).toHaveBeenCalledWith(
         "http://localhost:8000/recommendations/assistant",
         {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(request),
            credentials: "include",
         }
      );
   });
});
