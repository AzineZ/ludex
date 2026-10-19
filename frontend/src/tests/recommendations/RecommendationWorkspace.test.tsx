import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RecommendationPreference } from "../../api";
import RecommendationWorkspace from "../../features/recommendations/RecommendationWorkspace";

function openCustomize(): void {
   fireEvent.click(screen.getByRole("button", { name: "Customize" }));
}

vi.mock("../../features/recommendations/assistant/AssistantWorkspace", () => ({
   default: ({
      onUseGuided,
      sessionEpoch,
   }: {
      onUseGuided: () => void;
      sessionEpoch: number | null;
   }) => (
      <div>
         <p>Assistant epoch: {sessionEpoch ?? "none"}</p>
         <button type="button" onClick={onUseGuided}>
            Mock guided fallback
         </button>
      </div>
   ),
}));

const suggestedPreference: RecommendationPreference = {
   references: [
      {
         steam_app_id: 101,
         facets: {
            genre_ids: [10],
            theme_ids: [],
            keyword_ids: [],
            game_mode_ids: [],
         },
      },
   ],
   constraints: { maximum_completion_minutes: null, play_status: "unplayed" },
};

vi.mock("../../features/recommendations/automatic/AutomaticRecommendations", () => ({
   default: ({
      onCustomize,
      onUnavailable,
   }: {
      onCustomize: (preference: RecommendationPreference | null) => void;
      onUnavailable: () => void;
   }) => (
      <div>
         <p>Mock automatic suggestions</p>
         <button type="button" onClick={() => onCustomize(suggestedPreference)}>
            Customize
         </button>
         <button type="button" onClick={onUnavailable}>
            Mock suggestions unavailable
         </button>
      </div>
   ),
}));

vi.mock("../../features/recommendations/references/ReferenceSelectionSection", () => ({
   default: ({
      activeView,
      onRecommendationsReady,
      onRecommendationsReset,
      prefill,
      sessionEpoch,
   }: {
      activeView: "preferences" | "recommendations";
      onRecommendationsReady: () => void;
      onRecommendationsReset: () => void;
      prefill: RecommendationPreference | null;
      sessionEpoch: number | null;
   }) => (
      <div>
         <p>Recommendation epoch: {sessionEpoch ?? "none"}</p>
         <p>Mock workspace view: {activeView}</p>
         <p>
            Mock prefill: {prefill?.references
               .map((reference) => reference.steam_app_id)
               .join(",") ?? "none"}
         </p>
         <button type="button" onClick={onRecommendationsReady}>
            Make recommendations available
         </button>
         <button type="button" onClick={onRecommendationsReset}>
            Reset mock recommendations
         </button>
      </div>
   ),
}));

describe("RecommendationWorkspace", () => {
   it("starts on automatic suggestions with the form behind Customize", () => {
      render(<RecommendationWorkspace sessionEpoch={4} />);

      expect(screen.getByText("Mock automatic suggestions")).toBeVisible();
      expect(screen.queryByRole("button", { name: "Preferences" }))
         .not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Guided recommendations" }))
         .toHaveAttribute("aria-current", "page");
   });

   it("opens Customize prefilled and returns to the same suggestions", () => {
      render(<RecommendationWorkspace sessionEpoch={4} />);

      openCustomize();
      expect(screen.getByText("Mock prefill: 101")).toBeVisible();
      expect(screen.getByText("Mock automatic suggestions")).not.toBeVisible();

      fireEvent.click(screen.getByRole("button", {
         name: "← Back to suggestions",
      }));
      expect(screen.getByText("Mock automatic suggestions")).toBeVisible();
      expect(screen.queryByRole("button", { name: "Preferences" }))
         .not.toBeInTheDocument();
   });

   it("falls back to the form with an explanation when suggestions are unavailable", () => {
      render(<RecommendationWorkspace sessionEpoch={4} />);

      fireEvent.click(screen.getByRole("button", {
         name: "Mock suggestions unavailable",
      }));

      expect(screen.getByText(/Choose reference games below instead\./))
         .toBeVisible();
      expect(screen.queryByRole("button", { name: "← Back to suggestions" }))
         .not.toBeInTheDocument();
      expect(screen.getByText("Mock prefill: none")).toBeVisible();
   });

   it("starts Customize on preferences with unavailable recommendation navigation", () => {
      render(<RecommendationWorkspace sessionEpoch={4} />);
      openCustomize();

      expect(screen.getByText("Recommendation epoch: 4")).toBeInTheDocument();
      expect(screen.getByText("Mock workspace view: preferences"))
         .toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Preferences" }))
         .toHaveAttribute("aria-current", "page");
      expect(screen.getByRole("button", { name: "Guided results" }))
         .toBeDisabled();
      expect(screen.getByRole("button", { name: "Guided recommendations" }))
         .toHaveAttribute("aria-current", "page");
   });

   it("opens the optional assistant and returns through its guided fallback", () => {
      render(<RecommendationWorkspace sessionEpoch={4} />);

      fireEvent.click(screen.getByRole("button", { name: "Ask Ludex AI" }));
      expect(screen.getByText("Assistant epoch: 4")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Ask Ludex AI" }))
         .toHaveAttribute("aria-current", "page");
      expect(screen.queryByRole("button", { name: "Preferences" }))
         .not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Mock guided fallback" }));
      expect(screen.getByRole("button", { name: "Guided recommendations" }))
         .toHaveAttribute("aria-current", "page");
      expect(screen.getByRole("button", { name: "Preferences" }))
         .toBeInTheDocument();
   });

   it("opens completed recommendations and preserves access after returning to preferences", () => {
      render(<RecommendationWorkspace sessionEpoch={4} />);
      openCustomize();

      fireEvent.click(screen.getByRole("button", {
         name: "Make recommendations available",
      }));
      expect(screen.getByRole("button", { name: "Guided results" }))
         .toHaveAttribute("aria-current", "page");
      expect(screen.getByText("Mock workspace view: recommendations"))
         .toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Preferences" }));
      expect(screen.getByText("Mock workspace view: preferences"))
         .toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Guided results" }))
         .toBeEnabled();
   });

   it("returns to a locked preference view after reset", () => {
      render(<RecommendationWorkspace sessionEpoch={4} />);
      openCustomize();
      fireEvent.click(screen.getByRole("button", {
         name: "Make recommendations available",
      }));

      fireEvent.click(screen.getByRole("button", {
         name: "Reset mock recommendations",
      }));

      expect(screen.getByRole("button", { name: "Preferences" }))
         .toHaveAttribute("aria-current", "page");
      expect(screen.getByRole("button", { name: "Guided results" }))
         .toBeDisabled();
      expect(screen.getByText("Mock workspace view: preferences"))
         .toBeInTheDocument();
   });

   it("drops navigation state when the authorized session changes", async () => {
      const { rerender } = render(<RecommendationWorkspace sessionEpoch={4} />);
      openCustomize();
      fireEvent.click(screen.getByRole("button", {
         name: "Make recommendations available",
      }));

      rerender(<RecommendationWorkspace sessionEpoch={5} />);

      await waitFor(() => {
         expect(screen.getByText("Mock automatic suggestions")).toBeVisible();
      });
      openCustomize();
      await waitFor(() => {
         expect(screen.getByRole("button", { name: "Preferences" }))
            .toHaveAttribute("aria-current", "page");
         expect(screen.getByRole("button", { name: "Guided results" }))
            .toBeDisabled();
      });
      expect(screen.getByText("Recommendation epoch: 5")).toBeInTheDocument();
   });

   it("renders one navigation bar in normal document flow", () => {
      const { container } = render(<RecommendationWorkspace sessionEpoch={4} />);
      openCustomize();

      expect(screen.getByRole("navigation", {
         name: "Recommendation workspace",
      })).toBeVisible();
      expect(container.querySelectorAll(
         'nav[aria-label="Recommendation workspace"]'
      )).toHaveLength(1);
      expect(container.querySelector(".app__workspace-nav--side")).toBeNull();
      expect(container.querySelector(".app__workspace-nav-anchor")).toBeNull();
   });
});
