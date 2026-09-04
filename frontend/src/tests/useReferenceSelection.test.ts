import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   getReferenceDetails,
   type OwnedGameSuggestionResponse,
   type ReferenceDetailsResponse,
} from "../api";
import {
   useReferenceSelection,
   type ReferenceSelectionResult,
} from "../features/recommendations/useReferenceSelection";


vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();

   return {
      ...actual,
      getReferenceDetails: vi.fn(),
   };
});

type Deferred<Value> = {
   promise: Promise<Value>;
   resolve: (value: Value) => void;
   reject: (reason: unknown) => void;
};

const suggestions: OwnedGameSuggestionResponse[] = [
   {
      steam_app_id: 100,
      name: "First Game",
      cover_url: null,
      metadata_status: "ready",
   },
   {
      steam_app_id: 200,
      name: "Second Game",
      cover_url: null,
      metadata_status: "ready",
   },
   {
      steam_app_id: 300,
      name: "Third Game",
      cover_url: null,
      metadata_status: "ready",
   },
   {
      steam_app_id: 400,
      name: "Fourth Game",
      cover_url: null,
      metadata_status: "ready",
   },
];

function detailsFor(
   suggestion: OwnedGameSuggestionResponse
): ReferenceDetailsResponse {
   return {
      steam_app_id: suggestion.steam_app_id,
      name: suggestion.name,
      cover_url: suggestion.cover_url,
      metadata_status: "ready",
      facets: {
         genres: [{ id: suggestion.steam_app_id + 1, name: "Genre" }],
         themes: [{ id: suggestion.steam_app_id + 2, name: "Theme" }],
         game_modes: [
            { id: suggestion.steam_app_id + 3, name: "Single player" },
         ],
      },
   };
}

const mockedGetReferenceDetails = vi.mocked(getReferenceDetails);

function deferred<Value>(): Deferred<Value> {
   let resolve!: (value: Value) => void;
   let reject!: (reason: unknown) => void;
   const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
      resolve = resolvePromise;
      reject = rejectPromise;
   });

   return {
      promise,
      resolve,
      reject,
   };
}

async function addReference(
   result: { current: ReferenceSelectionResult },
   suggestion: OwnedGameSuggestionResponse
): Promise<boolean> {
   let added = false;

   await act(async () => {
      added = await result.current.addReference(suggestion);
   });

   return added;
}

describe("useReferenceSelection", () => {
   beforeEach(() => {
      mockedGetReferenceDetails.mockReset();
   });

   it("starts empty and rejects selection without a profile", async () => {
      const { result } = renderHook(() => useReferenceSelection(null));

      expect(result.current).toMatchObject({
         references: [],
         pendingSteamAppId: null,
         error: null,
      });

      await expect(
         addReference(result, suggestions[0])
      ).resolves.toBe(false);
      expect(mockedGetReferenceDetails).not.toHaveBeenCalled();
   });

   it("loads details before adding an empty ordered draft", async () => {
      const details = detailsFor(suggestions[0]);
      mockedGetReferenceDetails.mockResolvedValue(details);
      const { result } = renderHook(() => useReferenceSelection(1));

      await expect(
         addReference(result, suggestions[0])
      ).resolves.toBe(true);

      expect(mockedGetReferenceDetails).toHaveBeenCalledOnce();
      expect(mockedGetReferenceDetails).toHaveBeenCalledWith(100);
      expect(result.current).toMatchObject({
         references: [
            {
               details,
               selectedFacets: {
                  genres: [],
                  themes: [],
                  keywords: [],
                  gameModes: [],
               },
            },
         ],
         pendingSteamAppId: null,
         error: null,
      });
   });

   it("preserves selection order and rejects a duplicate", async () => {
      mockedGetReferenceDetails.mockImplementation(
         async (steamAppId) => {
            const suggestion = suggestions.find(
               (item) => item.steam_app_id === steamAppId
            );

            if (suggestion === undefined) {
               throw new Error("Unexpected game.");
            }

            return detailsFor(suggestion);
         }
      );
      const { result } = renderHook(() => useReferenceSelection(1));

      await addReference(result, suggestions[1]);
      await addReference(result, suggestions[0]);
      const duplicateAdded = await addReference(
         result,
         suggestions[1]
      );

      expect(duplicateAdded).toBe(false);
      expect(mockedGetReferenceDetails).toHaveBeenCalledTimes(2);
      expect(
         result.current.references.map(
            (reference) => reference.details.steam_app_id
         )
      ).toEqual([200, 100]);
   });

   it("rejects a fourth reference without another request", async () => {
      mockedGetReferenceDetails.mockImplementation(
         async (steamAppId) => {
            const suggestion = suggestions.find(
               (item) => item.steam_app_id === steamAppId
            );

            if (suggestion === undefined) {
               throw new Error("Unexpected game.");
            }

            return detailsFor(suggestion);
         }
      );
      const { result } = renderHook(() => useReferenceSelection(1));

      await addReference(result, suggestions[0]);
      await addReference(result, suggestions[1]);
      await addReference(result, suggestions[2]);
      const fourthAdded = await addReference(
         result,
         suggestions[3]
      );

      expect(fourthAdded).toBe(false);
      expect(mockedGetReferenceDetails).toHaveBeenCalledTimes(3);
      expect(result.current.references).toHaveLength(3);
   });

   it("allows only one detail request at a time", async () => {
      const request = deferred<ReferenceDetailsResponse>();
      mockedGetReferenceDetails.mockReturnValue(request.promise);
      const { result } = renderHook(() => useReferenceSelection(1));
      let firstAddition!: Promise<boolean>;

      act(() => {
         firstAddition = result.current.addReference(suggestions[0]);
      });

      expect(result.current.pendingSteamAppId).toBe(100);

      await expect(
         addReference(result, suggestions[1])
      ).resolves.toBe(false);
      expect(mockedGetReferenceDetails).toHaveBeenCalledOnce();

      await act(async () => {
         request.resolve(detailsFor(suggestions[0]));
         await firstAddition;
      });

      expect(result.current.pendingSteamAppId).toBeNull();
      expect(result.current.references).toHaveLength(1);
   });

   it("keeps the draft unchanged and exposes a detail error", async () => {
      mockedGetReferenceDetails.mockRejectedValue(
         new ApiError(
            409,
            "Factual metadata is unavailable for this reference game."
         )
      );
      const { result } = renderHook(() => useReferenceSelection(1));

      await expect(
         addReference(result, suggestions[0])
      ).resolves.toBe(false);

      expect(result.current).toMatchObject({
         references: [],
         pendingSteamAppId: null,
         error: (
            "Factual metadata is unavailable for this reference game."
         ),
      });
   });

   it("retries failed details without replacing existing reference choices", async () => {
      mockedGetReferenceDetails
         .mockResolvedValueOnce(detailsFor(suggestions[0]))
         .mockRejectedValueOnce(new ApiError(503, "Details unavailable."))
         .mockResolvedValueOnce(detailsFor(suggestions[1]));
      const { result } = renderHook(() => useReferenceSelection(1));
      await addReference(result, suggestions[0]);
      act(() => {
         result.current.toggleDirectFacet(
            100,
            "genres",
            detailsFor(suggestions[0]).facets.genres[0]
         );
      });

      await expect(addReference(result, suggestions[1])).resolves.toBe(false);
      expect(result.current.references[0].selectedFacets.genres).toHaveLength(1);

      await act(async () => {
         await expect(result.current.retryReference()).resolves.toBe(true);
      });

      expect(result.current.references.map((item) => item.details.steam_app_id))
         .toEqual([100, 200]);
      expect(result.current.references[0].selectedFacets.genres).toHaveLength(1);
      expect(mockedGetReferenceDetails).toHaveBeenCalledTimes(3);
   });

   it("removes one reference immediately", async () => {
      mockedGetReferenceDetails.mockImplementation(
         async (steamAppId) => {
            const suggestion = suggestions.find(
               (item) => item.steam_app_id === steamAppId
            );

            if (suggestion === undefined) {
               throw new Error("Unexpected game.");
            }

            return detailsFor(suggestion);
         }
      );
      const { result } = renderHook(() => useReferenceSelection(1));
      await addReference(result, suggestions[0]);
      await addReference(result, suggestions[1]);

      act(() => {
         result.current.removeReference(100);
      });

      expect(
         result.current.references.map(
            (reference) => reference.details.steam_app_id
         )
      ).toEqual([200]);
   });

   it("toggles canonical direct facets without changing other facet groups", async () => {
      const details = detailsFor(suggestions[0]);
      mockedGetReferenceDetails.mockResolvedValue(details);
      const { result } = renderHook(() => useReferenceSelection(1));
      await addReference(result, suggestions[0]);

      act(() => {
         result.current.toggleDirectFacet(
            100,
            "genres",
            { id: 101, name: "Invented genre name" }
         );
         result.current.toggleDirectFacet(
            100,
            "themes",
            details.facets.themes[0]
         );
         result.current.toggleDirectFacet(
            100,
            "gameModes",
            details.facets.game_modes[0]
         );
      });

      expect(result.current.references[0].selectedFacets).toEqual({
         genres: [details.facets.genres[0]],
         themes: [details.facets.themes[0]],
         keywords: [],
         gameModes: [details.facets.game_modes[0]],
      });
   });

   it("removes a selected direct facet when toggled again", async () => {
      const details = detailsFor(suggestions[0]);
      mockedGetReferenceDetails.mockResolvedValue(details);
      const { result } = renderHook(() => useReferenceSelection(1));
      await addReference(result, suggestions[0]);

      act(() => {
         result.current.toggleDirectFacet(
            100,
            "genres",
            details.facets.genres[0]
         );
      });
      expect(result.current.references[0].selectedFacets.genres).toEqual([
         details.facets.genres[0],
      ]);

      act(() => {
         result.current.toggleDirectFacet(
            100,
            "genres",
            details.facets.genres[0]
         );
      });
      expect(result.current.references[0].selectedFacets.genres).toEqual([]);
   });

   it("rejects direct facets for an unknown reference or option", async () => {
      const details = detailsFor(suggestions[0]);
      mockedGetReferenceDetails.mockResolvedValue(details);
      const { result } = renderHook(() => useReferenceSelection(1));
      await addReference(result, suggestions[0]);

      let unknownReferenceChanged = true;
      let unknownOptionChanged = true;
      act(() => {
         unknownReferenceChanged = result.current.toggleDirectFacet(
            999,
            "genres",
            details.facets.genres[0]
         );
         unknownOptionChanged = result.current.toggleDirectFacet(
            100,
            "genres",
            { id: 999, name: "Invented" }
         );
      });

      expect(unknownReferenceChanged).toBe(false);
      expect(unknownOptionChanged).toBe(false);
      expect(result.current.references[0].selectedFacets.genres).toEqual([]);
   });

   it("adds and removes exact keyword suggestions", async () => {
      mockedGetReferenceDetails.mockResolvedValue(detailsFor(suggestions[0]));
      const { result } = renderHook(() => useReferenceSelection(1));
      await addReference(result, suggestions[0]);
      const keyword = { id: 401, name: "Exploration" };

      act(() => {
         result.current.toggleKeyword(100, keyword);
      });
      expect(result.current.references[0].selectedFacets.keywords).toEqual([
         keyword,
      ]);

      act(() => {
         result.current.toggleKeyword(100, keyword);
      });
      expect(result.current.references[0].selectedFacets.keywords).toEqual([]);
   });

   it("limits each reference to three unique keywords", async () => {
      mockedGetReferenceDetails.mockResolvedValue(detailsFor(suggestions[0]));
      const { result } = renderHook(() => useReferenceSelection(1));
      await addReference(result, suggestions[0]);
      const keywords = [
         { id: 401, name: "Exploration" },
         { id: 402, name: "Choices" },
         { id: 403, name: "Crafting" },
         { id: 404, name: "Mystery" },
      ];
      let fourthChanged = true;

      act(() => {
         keywords.slice(0, 3).forEach((keyword) => {
            result.current.toggleKeyword(100, keyword);
         });
         fourthChanged = result.current.toggleKeyword(100, keywords[3]);
      });

      expect(fourthChanged).toBe(false);
      expect(result.current.references[0].selectedFacets.keywords).toEqual(
         keywords.slice(0, 3)
      );
   });

   it("rejects a keyword for an unknown reference", async () => {
      mockedGetReferenceDetails.mockResolvedValue(detailsFor(suggestions[0]));
      const { result } = renderHook(() => useReferenceSelection(1));
      await addReference(result, suggestions[0]);

      let changed = true;
      act(() => {
         changed = result.current.toggleKeyword(999, {
            id: 401,
            name: "Exploration",
         });
      });

      expect(changed).toBe(false);
      expect(result.current.references[0].selectedFacets.keywords).toEqual([]);
   });

   it("clears state and ignores late details after a profile change", async () => {
      const request = deferred<ReferenceDetailsResponse>();
      mockedGetReferenceDetails.mockReturnValue(request.promise);
      const { result, rerender } = renderHook(
         ({ sessionEpoch }) => useReferenceSelection(sessionEpoch),
         {
            initialProps: { sessionEpoch: 1 as number | null },
         }
      );
      let addition!: Promise<boolean>;

      act(() => {
         addition = result.current.addReference(suggestions[0]);
      });
      expect(result.current.pendingSteamAppId).toBe(100);

      rerender({ sessionEpoch: 2 });
      expect(result.current).toMatchObject({
         references: [],
         pendingSteamAppId: null,
         error: null,
      });

      let added = true;
      await act(async () => {
         request.resolve(detailsFor(suggestions[0]));
         added = await addition;
      });

      expect(added).toBe(false);
      expect(result.current.references).toEqual([]);
   });
});
