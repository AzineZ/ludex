import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RecommendationPreference } from "../api";
import PreferenceValidationPanel from "../features/recommendations/PreferenceValidationPanel";
import {
   usePreferenceValidation,
   type PreferenceValidationResult,
} from "../features/recommendations/usePreferenceValidation";

vi.mock(
   "../features/recommendations/usePreferenceValidation",
   async (importOriginal) => {
      const actual = await importOriginal<
         typeof import("../features/recommendations/usePreferenceValidation")
      >();
      return { ...actual, usePreferenceValidation: vi.fn() };
   }
);

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

const mockedUseValidation = vi.mocked(usePreferenceValidation);

function validationResult(
   overrides: Partial<PreferenceValidationResult> = {}
): PreferenceValidationResult {
   return {
      status: "idle",
      validatedPreference: null,
      error: null,
      errorField: null,
      validate: vi.fn().mockResolvedValue(true),
      ...overrides,
   };
}

describe("PreferenceValidationPanel", () => {
   beforeEach(() => mockedUseValidation.mockReset());

   it("shows the outgoing draft and starts validation on request", () => {
      const validation = validationResult();
      mockedUseValidation.mockReturnValue(validation);
      render(<PreferenceValidationPanel sessionEpoch={7} preference={preference} />);

      expect(mockedUseValidation).toHaveBeenCalledWith(7, preference);
      expect(screen.getByTestId("preference-draft")).toHaveTextContent(
         '"steam_app_id": 100'
      );
      fireEvent.click(screen.getByRole("button", { name: "Validate preferences" }));
      expect(validation.validate).toHaveBeenCalledOnce();
   });

   it("disables repeated validation while the request is running", () => {
      mockedUseValidation.mockReturnValue(
         validationResult({ status: "validating" })
      );
      render(<PreferenceValidationPanel sessionEpoch={7} preference={preference} />);

      expect(screen.getByRole("button", { name: "Validating preferences…" })).toBeDisabled();
      expect(screen.getByRole("status")).toHaveTextContent(
         "Checking this preference with Ludex…"
      );
   });

   it("shows the canonical validated preference", () => {
      mockedUseValidation.mockReturnValue(
         validationResult({
            status: "valid",
            validatedPreference: preference,
         })
      );
      render(<PreferenceValidationPanel sessionEpoch={7} preference={preference} />);

      expect(screen.getByRole("status")).toHaveTextContent(
         "Preference is valid."
      );
      expect(screen.getByTestId("validated-preference")).toHaveTextContent(
         '"genre_ids"'
      );
   });

   it("shows the backend field and message for an invalid preference", () => {
      mockedUseValidation.mockReturnValue(
         validationResult({
            status: "invalid",
            error: "Choose at least one factual facet.",
            errorField: "references.0.facets",
         })
      );
      render(<PreferenceValidationPanel sessionEpoch={7} preference={preference} />);

      expect(screen.getByRole("alert")).toHaveTextContent(
         "references.0.facets: Choose at least one factual facet."
      );
   });
});
