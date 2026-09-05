import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccessSessionSection from "../features/session/AccessSessionSection";
import { useAccessSession } from "../features/session/useAccessSession";

vi.mock("../features/session/useAccessSession", () => ({
   useAccessSession: vi.fn(),
}));
vi.mock("../features/session/SteamSessionForm", () => ({ default: () => null }));
vi.mock("../features/session/SessionGameLibrary", () => ({ default: () => null }));
vi.mock("../features/recommendations/ReferenceSelectionSection", () => ({
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

const mockedUseAccessSession = vi.mocked(useAccessSession);

function sessionResult(
   status: "loading" | "signed_out" | "ready" | "unavailable",
   sessionEpoch = 0
): ReturnType<typeof useAccessSession> {
   return {
      endError: null,
      endSession: vi.fn(),
      handleSessionUnauthorized: vi.fn(),
      isEnding: false,
      isRefreshing: false,
      isRestoringSession: false,
      isStarting: false,
      profile: status === "ready" ? {
         steam_id: "76561198000000001",
         display_name: "Session Player",
         profile_url: null,
         avatar_url: null,
         created_at: "2026-08-01T13:00:00Z",
         last_synced_at: null,
         games: [],
      } : null,
      refreshError: null,
      refreshSucceeded: false,
      refreshSessionProfile: vi.fn(),
      retrySessionRestore: vi.fn(),
      sessionEpoch,
      startError: null,
      startSession: vi.fn(),
      startupError: null,
      status,
   };
}

describe("AccessSessionSection composition", () => {
   beforeEach(() => mockedUseAccessSession.mockReset());

   it("does not mount recommendations without an authorized session", () => {
      mockedUseAccessSession.mockReturnValue(sessionResult("signed_out"));
      render(<AccessSessionSection />);
      expect(screen.getByRole("heading", { name: "Connect your Steam library" }))
         .toBeInTheDocument();
      expect(screen.queryByText(/Recommendation epoch:/)).not.toBeInTheDocument();
   });

   it("passes the in-memory session epoch instead of a profile ID", () => {
      mockedUseAccessSession.mockReturnValue(sessionResult("ready", 4));
      render(<AccessSessionSection />);
      expect(screen.getByRole("heading", { name: "What should you play next?" }))
         .toBeInTheDocument();
      expect(screen.getByText("Step 1 of 3 · Steam connected"))
         .toBeInTheDocument();
      expect(screen.getByText("Recommendation epoch: 4")).toBeInTheDocument();
   });

   it("navigates between preferences and available recommendations", () => {
      mockedUseAccessSession.mockReturnValue(sessionResult("ready", 4));
      render(<AccessSessionSection />);

      expect(screen.getByRole("button", { name: "Preferences" }))
         .toHaveAttribute("aria-current", "page");
      expect(screen.getByRole("button", { name: "Recommendations" }))
         .toBeDisabled();

      fireEvent.click(screen.getByRole("button", {
         name: "Make recommendations available",
      }));
      expect(screen.getByRole("button", { name: "Recommendations" }))
         .toHaveAttribute("aria-current", "page");
      expect(screen.getByText("Mock workspace view: recommendations"))
         .toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Preferences" }));
      expect(screen.getByText("Mock workspace view: preferences"))
         .toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Recommendations" }))
         .toBeEnabled();
   });

   it("keeps one workspace navigation in normal document flow", () => {
      mockedUseAccessSession.mockReturnValue(sessionResult("ready", 4));
      const { container } = render(<AccessSessionSection />);

      const navigation = screen.getByRole("navigation", {
         name: "Recommendation workspace",
      });
      expect(navigation).toBeVisible();
      expect(container.querySelectorAll(
         'nav[aria-label="Recommendation workspace"]'
      )).toHaveLength(1);
      expect(container.querySelector(".app__workspace-nav--side")).toBeNull();
      expect(container.querySelector(".app__workspace-nav-anchor")).toBeNull();
   });

   it("resets workspace navigation for reset recommendations and a new session", async () => {
      mockedUseAccessSession.mockReturnValue(sessionResult("ready", 4));
      const { rerender } = render(<AccessSessionSection />);
      fireEvent.click(screen.getByRole("button", {
         name: "Make recommendations available",
      }));

      fireEvent.click(screen.getByRole("button", {
         name: "Reset mock recommendations",
      }));
      expect(screen.getByRole("button", { name: "Preferences" }))
         .toHaveAttribute("aria-current", "page");
      expect(screen.getByRole("button", { name: "Recommendations" }))
         .toBeDisabled();

      fireEvent.click(screen.getByRole("button", {
         name: "Make recommendations available",
      }));
      mockedUseAccessSession.mockReturnValue(sessionResult("ready", 5));
      rerender(<AccessSessionSection />);

      await waitFor(() => {
         expect(screen.getByRole("button", { name: "Preferences" }))
            .toHaveAttribute("aria-current", "page");
         expect(screen.getByRole("button", { name: "Recommendations" }))
            .toBeDisabled();
      });
   });
});
