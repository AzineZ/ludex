import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RecommendationWorkspace from "../../features/recommendations/RecommendationWorkspace";

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

vi.mock("../../features/recommendations/references/ReferenceSelectionSection", () => ({
   default: ({
      activeView,
      onRecommendationsReady,
      onRecommendationsReset,
      sessionEpoch,
   }: {
      activeView: "preferences" | "recommendations";
      onRecommendationsReady: () => void;
      onRecommendationsReset: () => void;
      sessionEpoch: number | null;
   }) => (
      <div>
         <p>Recommendation epoch: {sessionEpoch ?? "none"}</p>
         <p>Mock workspace view: {activeView}</p>
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
   it("starts on preferences with unavailable recommendation navigation", () => {
      render(<RecommendationWorkspace sessionEpoch={4} />);

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
      fireEvent.click(screen.getByRole("button", {
         name: "Make recommendations available",
      }));

      rerender(<RecommendationWorkspace sessionEpoch={5} />);

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
