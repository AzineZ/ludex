import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
   validateRecommendationPreference,
   type RecommendationPreference,
} from "../api";
import {
   preferenceValidationError,
   usePreferenceValidation,
} from "../features/recommendations/usePreferenceValidation";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();
   return { ...actual, validateRecommendationPreference: vi.fn() };
});

const preference: RecommendationPreference = {
   references: [
      {
         steam_app_id: 100,
         facets: {
            genre_ids: [11],
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

const mockedValidate = vi.mocked(validateRecommendationPreference);

describe("usePreferenceValidation", () => {
   beforeEach(() => mockedValidate.mockReset());

   it("stays idle and rejects validation without a profile", async () => {
      const { result } = renderHook(() =>
         usePreferenceValidation(null, preference)
      );
      await expect(result.current.validate()).resolves.toBe(false);
      expect(result.current.status).toBe("idle");
      expect(mockedValidate).not.toHaveBeenCalled();
   });

   it("exposes validating state and the canonical validated response", async () => {
      let resolve!: (value: RecommendationPreference) => void;
      const request = new Promise<RecommendationPreference>((done) => {
         resolve = done;
      });
      mockedValidate.mockReturnValue(request);
      const { result } = renderHook(() =>
         usePreferenceValidation(7, preference)
      );
      let validation!: Promise<boolean>;
      act(() => {
         validation = result.current.validate();
      });
      expect(result.current.status).toBe("validating");
      expect(mockedValidate).toHaveBeenCalledWith(preference);

      await act(async () => {
         resolve(preference);
         await validation;
      });
      expect(result.current).toMatchObject({
         status: "valid",
         validatedPreference: preference,
         error: null,
         errorField: null,
      });
   });

   it("extracts the backend message and field for an invalid draft", () => {
      const error = Object.assign(
         new Error("Choose at least one factual facet."),
         { field: "references.0.facets" }
      );
      expect(preferenceValidationError(error)).toEqual({
         message: "Choose at least one factual facet.",
         field: "references.0.facets",
      });
   });

   it("returns to idle when the profile or draft changes", async () => {
      mockedValidate.mockResolvedValue(preference);
      const { result, rerender } = renderHook(
         ({ profileId, value }) => usePreferenceValidation(profileId, value),
         { initialProps: { profileId: 7, value: preference } }
      );
      await act(async () => {
         await result.current.validate();
      });
      expect(result.current.status).toBe("valid");

      rerender({
         profileId: 8,
         value: {
            ...preference,
            constraints: { ...preference.constraints, play_status: "unplayed" },
         },
      });
      expect(result.current.status).toBe("idle");
      expect(result.current.validatedPreference).toBeNull();
   });
});
