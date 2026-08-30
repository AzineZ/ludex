import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
   getFinalRecommendations,
   validateRecommendationPreference,
   type FinalRecommendationResponse,
   type RecommendationPreference,
} from "../api";
import PreferenceValidationPanel from "../features/recommendations/PreferenceValidationPanel";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();

   return {
      ...actual,
      getFinalRecommendations: vi.fn(),
      validateRecommendationPreference: vi.fn(),
   };
});

type Deferred<Value> = {
   promise: Promise<Value>;
   resolve: (value: Value) => void;
};

const draft: RecommendationPreference = {
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

const canonicalPreference: RecommendationPreference = {
   ...draft,
   constraints: {
      maximum_completion_minutes: 1800,
      play_status: "unplayed",
   },
};

const response: FinalRecommendationResponse = {
   outcome: "sparse",
   eligible_count: 1,
   returned_count: 1,
   items: [
      {
         rank: 1,
         steam_app_id: 620,
         title: "Portal 2",
         cover_url: null,
         profile_playtime_minutes: 0,
         normal_completion_seconds: null,
         factual_evidence: {
            version: "factual-overlap-v1",
            score_basis_points: 8000,
            active_budget: 100,
            contributions: [],
         },
         facet_labels: [],
         match_summary: {
            reasons: [],
            additional_match_count: 0,
            text: "Matches your Puzzle preference.",
         },
         tradeoff: null,
      },
   ],
};

const mockedValidate = vi.mocked(validateRecommendationPreference);
const mockedGetRecommendations = vi.mocked(getFinalRecommendations);

function deferred<Value>(): Deferred<Value> {
   let resolve!: (value: Value) => void;
   const promise = new Promise<Value>((resolvePromise) => {
      resolve = resolvePromise;
   });

   return { promise, resolve };
}

async function completeWorkflow(): Promise<void> {
   fireEvent.click(
      screen.getByRole("button", { name: "Validate preferences" })
   );
   await screen.findByText("Preference is valid.");
   fireEvent.click(
      screen.getByRole("button", { name: "Get recommendations" })
   );
   await screen.findByRole("article", { name: "Portal 2" });
}

describe("preference recommendation workflow", () => {
   beforeEach(() => {
      mockedValidate.mockReset();
      mockedGetRecommendations.mockReset();
      mockedValidate.mockResolvedValue(canonicalPreference);
      mockedGetRecommendations.mockResolvedValue(response);
   });

   it("submits only the canonical preference and renders its result", async () => {
      render(<PreferenceValidationPanel profileId={7} preference={draft} />);

      expect(
         screen.getByRole("button", { name: "Get recommendations" })
      ).toBeDisabled();

      await completeWorkflow();

      expect(mockedValidate).toHaveBeenCalledWith(7, draft);
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
      expect(mockedGetRecommendations).toHaveBeenCalledWith(
         7,
         canonicalPreference
      );
      expect(screen.getByText("1 recommendation found.")).toBeInTheDocument();
   });

   it("locks and announces recommendation submission while it is pending", async () => {
      const pendingRequest = deferred<FinalRecommendationResponse>();
      mockedGetRecommendations.mockReturnValue(pendingRequest.promise);
      render(<PreferenceValidationPanel profileId={7} preference={draft} />);

      fireEvent.click(
         screen.getByRole("button", { name: "Validate preferences" })
      );
      await screen.findByText("Preference is valid.");
      fireEvent.click(
         screen.getByRole("button", { name: "Get recommendations" })
      );

      expect(
         screen.getByRole("button", { name: "Finding recommendations…" })
      ).toBeDisabled();
      expect(
         screen.getByText("Finding recommendations in your cached library…")
      ).toHaveAttribute("role", "status");
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();

      pendingRequest.resolve(response);
      await screen.findByRole("article", { name: "Portal 2" });
   });

   it("invalidates validation and results when the draft changes", async () => {
      const { rerender } = render(
         <PreferenceValidationPanel profileId={7} preference={draft} />
      );
      await completeWorkflow();

      rerender(
         <PreferenceValidationPanel
            profileId={7}
            preference={{
               ...draft,
               constraints: {
                  ...draft.constraints,
                  play_status: "previously_played",
               },
            }}
         />
      );

      await waitFor(() => {
         expect(screen.queryByText("Preference is valid.")).not.toBeInTheDocument();
      });
      expect(screen.queryByRole("article", { name: "Portal 2" })).toBeNull();
      expect(
         screen.getByRole("button", { name: "Get recommendations" })
      ).toBeDisabled();
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
   });

   it("invalidates validation and results when the profile changes", async () => {
      const { rerender } = render(
         <PreferenceValidationPanel profileId={7} preference={draft} />
      );
      await completeWorkflow();

      rerender(
         <PreferenceValidationPanel profileId={8} preference={draft} />
      );

      await waitFor(() => {
         expect(screen.queryByRole("article", { name: "Portal 2" })).toBeNull();
      });
      expect(screen.queryByText("Preference is valid.")).not.toBeInTheDocument();
      expect(
         screen.getByRole("button", { name: "Get recommendations" })
      ).toBeDisabled();
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
   });
});
