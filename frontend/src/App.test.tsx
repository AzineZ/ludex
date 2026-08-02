import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
   getHealth,
   listProfiles,
   type HealthResponse,
   type ProfileSummaryResponse,
} from "./api";

vi.mock("./api", () => ({
   getHealth: vi.fn(),
   listProfiles: vi.fn(),
}));

const mockedGetHealth = vi.mocked(getHealth);
const mockedListProfiles = vi.mocked(listProfiles);

const savedProfiles: ProfileSummaryResponse[] = [
   {
      id: 1,
      steam_id: "76561198000000000",
      display_name: "First Player",
      profile_url: null,
      avatar_url: null,
      created_at: "2026-08-01T12:00:00Z",
      last_synced_at: "2026-08-01T12:00:00Z",
   },
   {
      id: 2,
      steam_id: "76561198000000001",
      display_name: "Second Player",
      profile_url: null,
      avatar_url: null,
      created_at: "2026-08-01T13:00:00Z",
      last_synced_at: "2026-08-01T13:00:00Z",
   },
];

describe("App", () => {
   beforeEach(() => {
      mockedGetHealth.mockReset();
      mockedListProfiles.mockReset();
      mockedListProfiles.mockImplementation(() => new Promise(() => {}));
   });

   it("renders while checking the backend connection", () => {
      mockedGetHealth.mockImplementation(
         () => new Promise<HealthResponse>(() => {})
      );

      render(<App />);

      expect(
         screen.getByRole("heading", { name: "Find your next game." })
      ).toBeInTheDocument();
      expect(screen.getByText("Backend: checking")).toBeInTheDocument();
      expect(screen.getByText("Loading profiles...")).toBeInTheDocument();
   });

   it("shows connected when the health request succeeds", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });

      render(<App />);

      expect(await screen.findByText("Backend: connected")).toBeInTheDocument();
   });

   it("shows unavailable when the health request fails", async () => {
      mockedGetHealth.mockRejectedValue(new Error("Backend unavailable"));

      render(<App />);

      expect(
         await screen.findByText("Backend: unavailable")
      ).toBeInTheDocument();
   });

   it("shows an empty state when no profiles are saved", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue([]);

      render(<App />);

      expect(
         await screen.findByText("No Steam profiles have been added yet.")
      ).toBeInTheDocument();
   });

   it("shows every saved profile", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);

      render(<App />);

      expect(await screen.findByText("First Player")).toBeInTheDocument();
      expect(screen.getByText("Second Player")).toBeInTheDocument();
   });

   it("shows an error when profiles cannot be loaded", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockRejectedValue(new Error("Profiles unavailable"));

      render(<App />);

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Saved profiles are currently unavailable."
      );
   });
});
