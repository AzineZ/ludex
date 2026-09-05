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

   it("hides the technical payload and validates from the recommendation action", () => {
      const validation = validationResult();
      mockedUseValidation.mockReturnValue(validation);
      const { container } = render(
         <PreferenceValidationPanel sessionEpoch={7} preference={preference} />
      );

      expect(mockedUseValidation).toHaveBeenCalledWith(7, preference);
      expect(screen.getByRole("heading", { name: "Find your next game" }))
         .toBeInTheDocument();
      expect(screen.queryByText(/step 3 of 3/i)).not.toBeInTheDocument();
      expect(container.querySelector("pre")).toBeNull();
      expect(screen.queryByText(/steam_app_id/)).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Get recommendations" }));
      expect(validation.validate).toHaveBeenCalledOnce();
   });

   it("explains and enforces the minimum local preference before validation", () => {
      const validation = validationResult();
      mockedUseValidation.mockReturnValue(validation);
      const emptyPreference: RecommendationPreference = {
         ...preference,
         references: [],
      };
      const { rerender } = render(
         <PreferenceValidationPanel
            sessionEpoch={7}
            preference={emptyPreference}
         />
      );

      expect(screen.getByText("Choose at least one reference game to continue."))
         .toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Get recommendations" }))
         .toBeDisabled();

      rerender(
         <PreferenceValidationPanel
            sessionEpoch={7}
            preference={{
               ...preference,
               references: [{
                  ...preference.references[0],
                  facets: {
                     genre_ids: [],
                     theme_ids: [],
                     keyword_ids: [],
                     game_mode_ids: [],
                  },
               }],
            }}
         />
      );

      expect(screen.getByText(
         "Select at least one trait from every reference game to continue."
      )).toBeInTheDocument();
      expect(validation.validate).not.toHaveBeenCalled();
   });

   it("disables repeated validation while the request is running", () => {
      mockedUseValidation.mockReturnValue(
         validationResult({ status: "validating" })
      );
      render(<PreferenceValidationPanel sessionEpoch={7} preference={preference} />);

      expect(screen.getByRole("button", { name: "Checking preferences…" })).toBeDisabled();
      expect(screen.getByRole("status")).toHaveTextContent(
         "Checking this preference with Ludex…"
      );
   });

   it("does not expose the canonical validated preference", () => {
      mockedUseValidation.mockReturnValue(
         validationResult({
            status: "valid",
            validatedPreference: preference,
         })
      );
      const { container } = render(
         <PreferenceValidationPanel sessionEpoch={7} preference={preference} />
      );

      expect(container.querySelector("pre")).toBeNull();
      expect(screen.queryByText(/genre_ids/)).toBeNull();
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
         "Choose at least one factual facet."
      );
      expect(screen.getByRole("alert")).not.toHaveTextContent(
         "references.0.facets"
      );
   });
});
