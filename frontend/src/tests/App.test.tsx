import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import {
   ApiError,
   createAccessSession,
   deleteAccessSession,
   getCurrentSessionProfile,
   getHealth,
   refreshCurrentSessionProfile,
   SESSION_UNAUTHORIZED_EVENT,
   type HealthResponse,
   type SessionProfileResponse,
} from "../api";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();
   return {
      ...actual,
      createAccessSession: vi.fn(),
      deleteAccessSession: vi.fn(),
      getCurrentSessionProfile: vi.fn(),
      getHealth: vi.fn(),
      refreshCurrentSessionProfile: vi.fn(),
   };
});

const sessionProfile: SessionProfileResponse = {
   steam_id: "76561198000000001",
   display_name: "Session Player",
   profile_url: null,
   avatar_url: null,
   created_at: "2026-08-01T13:00:00Z",
   last_synced_at: "2026-08-01T13:00:00Z",
   games: [
      {
         steam_app_id: 10,
         name: "Alpha Game",
         icon_url: null,
         cover_url: null,
         playtime_minutes: 120,
         recent_playtime_minutes: 30,
         last_played_at: null,
      },
      {
         steam_app_id: 20,
         name: "Beta Game",
         icon_url: null,
         cover_url: null,
         playtime_minutes: 0,
         recent_playtime_minutes: null,
         last_played_at: null,
      },
   ],
};

const mockedCreate = vi.mocked(createAccessSession);
const mockedDelete = vi.mocked(deleteAccessSession);
const mockedGetCurrent = vi.mocked(getCurrentSessionProfile);
const mockedGetHealth = vi.mocked(getHealth);
const mockedRefresh = vi.mocked(refreshCurrentSessionProfile);

describe("App session experience", () => {
   beforeEach(() => {
      mockedCreate.mockReset();
      mockedDelete.mockReset();
      mockedGetCurrent.mockReset();
      mockedGetHealth.mockReset();
      mockedRefresh.mockReset();
      mockedGetHealth.mockImplementation(
         () => new Promise<HealthResponse>(() => {})
      );
      mockedGetCurrent.mockImplementation(() => new Promise(() => {}));
   });

   it("renders while checking backend and browser session state", () => {
      render(<App />);
      expect(
         screen.getByRole("heading", { name: "Ludex — Your next game awaits" })
      ).toBeInTheDocument();
      expect(screen.getByText("Server: pending")).toBeInTheDocument();
      expect(screen.getByText("Checking your Steam session…")).toHaveAttribute(
         "role",
         "status"
      );
   });

   it("shows Steam ID entry when no browser session exists", async () => {
      mockedGetCurrent.mockRejectedValue(new ApiError(401, "Required."));
      render(<App />);
      expect(await screen.findByLabelText("Steam ID or profile URL"))
         .toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Continue with Steam" }))
         .toBeDisabled();
      expect(screen.queryByText(/saved profiles/i)).not.toBeInTheDocument();
   });

   it("shows a recoverable message when session startup is unavailable", async () => {
      mockedGetCurrent.mockRejectedValue(new ApiError(503, "Try again later."));
      render(<App />);
      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Try again later."
      );
      expect(screen.getByLabelText("Steam ID or profile URL"))
         .toBeInTheDocument();
   });

   it("restores only the cookie-authorized profile and its library", async () => {
      mockedGetCurrent.mockResolvedValue(sessionProfile);
      render(<App />);
      expect(await screen.findByText("Session Player")).toBeInTheDocument();
      expect(screen.getByText("2 games in your library")).toBeInTheDocument();
      expect(screen.getAllByText("Alpha Game").length).toBeGreaterThan(0);
      expect(screen.queryByText("120 minutes played")).toBeNull();
      const profileActions = screen.getByRole("button", {
         name: "Use another Steam ID",
      }).closest(".app__profile-actions");
      expect(profileActions).toContainElement(
         screen.getByRole("button", { name: "Refresh library" })
      );
      expect(profileActions).toContainElement(
         screen.getByRole("button", { name: "Pause background" })
      );
      expect(screen.getByRole("heading", { name: "Choose reference games" }))
         .toBeInTheDocument();
      expect(screen.queryByText(/saved profiles/i)).not.toBeInTheDocument();
   });

   it("starts a session with the trimmed submitted identifier", async () => {
      mockedGetCurrent.mockRejectedValue(new ApiError(401, "Required."));
      mockedCreate.mockResolvedValue(sessionProfile);
      render(<App />);
      const input = await screen.findByLabelText("Steam ID or profile URL");
      fireEvent.change(input, { target: { value: "  example-profile  " } });
      fireEvent.click(screen.getByRole("button", { name: "Continue with Steam" }));
      expect(mockedCreate).toHaveBeenCalledWith("example-profile");
      expect(await screen.findByText("Session Player")).toBeInTheDocument();
      expect(screen.queryByLabelText("Steam ID or profile URL"))
         .not.toBeInTheDocument();
   });

   it("keeps the identifier available when session creation fails", async () => {
      mockedGetCurrent.mockRejectedValue(new ApiError(401, "Required."));
      mockedCreate.mockRejectedValue(
         new ApiError(422, "This Steam library is private or unavailable.")
      );
      render(<App />);
      const input = await screen.findByLabelText("Steam ID or profile URL");
      fireEvent.change(input, { target: { value: "private-profile" } });
      fireEvent.click(screen.getByRole("button", { name: "Continue with Steam" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(
         "This Steam library is private or unavailable."
      );
      expect(input).toHaveValue("private-profile");
      expect(input).not.toBeDisabled();
   });

   it("disables duplicate submission while starting a session", async () => {
      mockedGetCurrent.mockRejectedValue(new ApiError(401, "Required."));
      mockedCreate.mockImplementation(() => new Promise(() => {}));
      render(<App />);
      const input = await screen.findByLabelText("Steam ID or profile URL");
      fireEvent.change(input, { target: { value: "example-profile" } });
      fireEvent.click(screen.getByRole("button", { name: "Continue with Steam" }));
      expect(input).toBeDisabled();
      expect(screen.getByRole("button", { name: "Loading Steam profile…" }))
         .toBeDisabled();
   });

   it("updates the current library after refresh without changing sessions", async () => {
      mockedGetCurrent.mockResolvedValue(sessionProfile);
      mockedRefresh.mockResolvedValue({
         ...sessionProfile,
         games: [
            ...sessionProfile.games,
            {
               steam_app_id: 30,
               name: "Gamma Game",
               icon_url: null,
               cover_url: null,
               playtime_minutes: 45,
               recent_playtime_minutes: null,
               last_played_at: null,
            },
         ],
      });
      render(<App />);
      fireEvent.click(await screen.findByRole("button", { name: "Refresh library" }));
      expect(await screen.findByRole("status", { name: "refresh-result" }))
         .toHaveTextContent("Steam library refreshed.");
      expect(screen.getByText("3 games in your library")).toBeInTheDocument();
      expect(screen.getAllByText("Gamma Game").length).toBeGreaterThan(0);
   });

   it("preserves the current profile when refresh fails", async () => {
      mockedGetCurrent.mockResolvedValue(sessionProfile);
      mockedRefresh.mockRejectedValue(new ApiError(503, "Steam unavailable."));
      render(<App />);
      fireEvent.click(await screen.findByRole("button", { name: "Refresh library" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Steam unavailable."
      );
      expect(screen.getAllByText("Alpha Game").length).toBeGreaterThan(0);
   });

   it("revokes the current session before showing another-ID entry", async () => {
      mockedGetCurrent.mockResolvedValue(sessionProfile);
      mockedDelete.mockResolvedValue(undefined);
      render(<App />);
      fireEvent.click(
         await screen.findByRole("button", { name: "Use another Steam ID" })
      );
      await waitFor(() => expect(mockedDelete).toHaveBeenCalledOnce());
      expect(await screen.findByLabelText("Steam ID or profile URL"))
         .toBeInTheDocument();
      expect(screen.queryByText("Alpha Game")).not.toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Choose reference games" }))
         .not.toBeInTheDocument();
   });

   it("keeps the current profile visible when revocation fails", async () => {
      mockedGetCurrent.mockResolvedValue(sessionProfile);
      mockedDelete.mockRejectedValue(new ApiError(503, "Could not end session."));
      render(<App />);
      fireEvent.click(
         await screen.findByRole("button", { name: "Use another Steam ID" })
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Could not end session."
      );
      expect(screen.getByText("Session Player")).toBeInTheDocument();
      expect(screen.queryByLabelText("Steam ID or profile URL"))
         .not.toBeInTheDocument();
   });

   it("returns to Steam ID entry when a protected request loses authority", async () => {
      mockedGetCurrent.mockResolvedValue(sessionProfile);
      render(<App />);
      await screen.findByText("Session Player");

      window.dispatchEvent(new Event(SESSION_UNAUTHORIZED_EVENT));

      expect(await screen.findByLabelText("Steam ID or profile URL"))
         .toBeInTheDocument();
      expect(screen.queryByText("Alpha Game")).not.toBeInTheDocument();
   });
});
