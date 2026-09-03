import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccessSessionSection from "../features/session/AccessSessionSection";
import { useAccessSession } from "../features/session/useAccessSession";

vi.mock("../features/session/useAccessSession", () => ({
   useAccessSession: vi.fn(),
}));
vi.mock("../features/session/SteamSessionForm", () => ({ default: () => null }));
vi.mock("../features/session/SessionGameLibrary", () => ({ default: () => null }));
vi.mock("../features/recommendations/ReferenceSelectionSection", () => ({
   default: ({ sessionEpoch }: { sessionEpoch: number | null }) => (
      <p>Recommendation epoch: {sessionEpoch ?? "none"}</p>
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
      expect(screen.queryByText(/Recommendation epoch:/)).not.toBeInTheDocument();
   });

   it("passes the in-memory session epoch instead of a profile ID", () => {
      mockedUseAccessSession.mockReturnValue(sessionResult("ready", 4));
      render(<AccessSessionSection />);
      expect(screen.getByText("Recommendation epoch: 4")).toBeInTheDocument();
   });
});
