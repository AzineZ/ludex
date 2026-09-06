import { describe, expect, it } from "vitest";

import type { PreferenceConstraints } from "../../api";
import { serializeRecommendationPreference } from "../../features/recommendations/preferences/preferenceSerialization";
import type { SelectedReference } from "../../features/recommendations/references/useReferenceSelection";

const constraints: PreferenceConstraints = {
   maximum_completion_minutes: 1800,
   play_status: "unplayed",
};

const references: SelectedReference[] = [
   {
      details: {
         steam_app_id: 100,
         name: "First Game",
         cover_url: null,
         metadata_status: "ready",
         facets: { genres: [], themes: [], game_modes: [] },
      },
      selectedFacets: {
         genres: [{ id: 11, name: "Role-playing" }],
         themes: [{ id: 21, name: "Fantasy" }],
         keywords: [
            { id: 42, name: "Choices" },
            { id: 41, name: "Exploration" },
         ],
         gameModes: [{ id: 31, name: "Single player" }],
      },
   },
   {
      details: {
         steam_app_id: 200,
         name: "Second Game",
         cover_url: null,
         metadata_status: "ready",
         facets: { genres: [], themes: [], game_modes: [] },
      },
      selectedFacets: {
         genres: [],
         themes: [],
         keywords: [],
         gameModes: [],
      },
   },
];

describe("serializeRecommendationPreference", () => {
   it("maps the ordered reference draft and facet objects to API ID arrays", () => {
      expect(serializeRecommendationPreference(references, constraints)).toEqual({
         references: [
            {
               steam_app_id: 100,
               facets: {
                  genre_ids: [11],
                  theme_ids: [21],
                  keyword_ids: [42, 41],
                  game_mode_ids: [31],
               },
            },
            {
               steam_app_id: 200,
               facets: {
                  genre_ids: [],
                  theme_ids: [],
                  keyword_ids: [],
                  game_mode_ids: [],
               },
            },
         ],
         constraints,
      });
   });

   it("supports an empty draft and unset completion maximum", () => {
      expect(
         serializeRecommendationPreference([], {
            maximum_completion_minutes: null,
            play_status: "either",
         })
      ).toEqual({
         references: [],
         constraints: {
            maximum_completion_minutes: null,
            play_status: "either",
         },
      });
   });

   it("returns new arrays and does not mutate the selection draft", () => {
      const preference = serializeRecommendationPreference(references, constraints);
      preference.references[0].facets.genre_ids.push(999);

      expect(references[0].selectedFacets.genres).toEqual([
         { id: 11, name: "Role-playing" },
      ]);
      expect(preference.constraints).not.toBe(constraints);
   });
});
