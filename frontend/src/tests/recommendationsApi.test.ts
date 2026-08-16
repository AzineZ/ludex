import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   getReferenceDetails,
   listProfiles,
   searchReferenceGames,
   searchReferenceKeywords,
   validateRecommendationPreference,
   type OwnedGameSearchResponse,
   type RecommendationPreference,
   type ReferenceDetailsResponse,
} from "../api";


const ownedGameSearch: OwnedGameSearchResponse = {
   items: [
      {
         steam_app_id: 100,
         name: "Reference Game",
         cover_url: (
            "https://images.igdb.com/igdb/image/upload/"
            + "t_cover_big/reference-cover.jpg"
         ),
         metadata_status: "ready",
      },
      {
         steam_app_id: 200,
         name: "Unavailable Game",
         cover_url: null,
         metadata_status: "missing",
      },
   ],
};

const referenceDetails: ReferenceDetailsResponse = {
   steam_app_id: 100,
   name: "Reference Game",
   cover_url: null,
   metadata_status: "ready",
   facets: {
      genres: [{ id: 10, name: "Adventure" }],
      themes: [{ id: 20, name: "Fantasy" }],
      game_modes: [{ id: 30, name: "Single player" }],
   },
};

const preference: RecommendationPreference = {
   references: [
      {
         steam_app_id: 100,
         facets: {
            genre_ids: [10],
            theme_ids: [20],
            keyword_ids: [40],
            game_mode_ids: [30],
         },
      },
   ],
   constraints: {
      maximum_completion_minutes: 1800,
      play_status: "either",
   },
};

const fetchMock = vi.fn<typeof fetch>();

/** Creates a JSON response with the requested HTTP status. */
function jsonResponse(responseData: unknown, status = 200): Response {
   return new Response(JSON.stringify(responseData), {
      status,
      headers: {
         "Content-Type": "application/json",
      },
   });
}

describe("recommendation API", () => {
   beforeEach(() => {
      fetchMock.mockReset();
      vi.stubGlobal("fetch", fetchMock);
   });

   afterEach(() => {
      vi.unstubAllGlobals();
   });

   it("searches one profile's owned reference games", async () => {
      fetchMock.mockResolvedValue(jsonResponse(ownedGameSearch));

      await expect(
         searchReferenceGames(1, "co-op 100%_")
      ).resolves.toEqual(ownedGameSearch);

      expect(fetchMock).toHaveBeenCalledWith(
         (
            "http://localhost:8000/profiles/1/recommendations/"
            + "references?query=co-op+100%25_"
         ),
         undefined
      );
   });

   it("requests ready factual details for one reference", async () => {
      fetchMock.mockResolvedValue(jsonResponse(referenceDetails));

      await expect(getReferenceDetails(1, 100)).resolves.toEqual(
         referenceDetails
      );

      expect(fetchMock).toHaveBeenCalledWith(
         (
            "http://localhost:8000/profiles/1/recommendations/"
            + "references/100"
         ),
         undefined
      );
   });

   it("searches keywords within one exact reference", async () => {
      const response = {
         items: [
            { id: 40, name: "Farming simulation" },
         ],
      };
      fetchMock.mockResolvedValue(jsonResponse(response));

      await expect(
         searchReferenceKeywords(1, 100, "farming & life")
      ).resolves.toEqual(response);

      expect(fetchMock).toHaveBeenCalledWith(
         (
            "http://localhost:8000/profiles/1/recommendations/"
            + "references/100/keywords?query=farming+%26+life"
         ),
         undefined
      );
   });

   it("submits and returns one canonical preference", async () => {
      fetchMock.mockResolvedValue(jsonResponse(preference));

      await expect(
         validateRecommendationPreference(1, preference)
      ).resolves.toEqual(preference);

      expect(fetchMock).toHaveBeenCalledWith(
         (
            "http://localhost:8000/profiles/1/recommendations/"
            + "preferences/validate"
         ),
         {
            method: "POST",
            headers: {
               "Content-Type": "application/json",
            },
            body: JSON.stringify(preference),
         }
      );
   });

   it("preserves recommendation error code and field", async () => {
      fetchMock.mockResolvedValue(
         jsonResponse(
            {
               error: {
                  code: "reference_metadata_unavailable",
                  field: "steam_app_id",
                  message: (
                     "Factual metadata is unavailable for this "
                     + "reference game."
                  ),
               },
            },
            409
         )
      );

      const request = getReferenceDetails(1, 100);

      await expect(request).rejects.toMatchObject({
         name: "ApiError",
         status: 409,
         code: "reference_metadata_unavailable",
         field: "steam_app_id",
         message: (
            "Factual metadata is unavailable for this reference game."
         ),
      });
      await expect(request).rejects.toBeInstanceOf(ApiError);
   });

   it("keeps existing detail errors without fabricated metadata", async () => {
      fetchMock.mockResolvedValue(
         jsonResponse(
            {
               detail: "Profile not found.",
            },
            404
         )
      );

      await expect(listProfiles()).rejects.toMatchObject({
         name: "ApiError",
         status: 404,
         code: null,
         field: null,
         message: "Profile not found.",
      });
   });
});
