import { waitFor, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
   ApiError,
   createProfile,
   getHealth,
   getProfile,
   listProfiles,
   refreshProfile,
   type HealthResponse,
   type ProfileDetailResponse,
} from "./api";
import {
   importedProfile,
   profileWithGames,
   savedProfiles,
} from "./tests/profileFixtures";

vi.mock("./api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("./api")>();

   return {
      ...actual,
      createProfile: vi.fn(),
      getHealth: vi.fn(),
      getProfile: vi.fn(),
      listProfiles: vi.fn(),
      refreshProfile: vi.fn(),
   };
});

const mockedCreateProfile = vi.mocked(createProfile);
const mockedGetHealth = vi.mocked(getHealth);
const mockedGetProfile = vi.mocked(getProfile);
const mockedListProfiles = vi.mocked(listProfiles);
const mockedRefreshProfile = vi.mocked(refreshProfile);

describe("App", () => {
   beforeEach(() => {
      window.localStorage.clear();
      mockedCreateProfile.mockReset();
      mockedGetHealth.mockReset();
      mockedListProfiles.mockReset();
      mockedListProfiles.mockImplementation(() => new Promise(() => {}));
      mockedGetProfile.mockReset();
      mockedGetProfile.mockImplementation(() => new Promise(() => {}));
      mockedRefreshProfile.mockReset();
   });

   it("renders while checking the backend connection", () => {
      mockedGetHealth.mockImplementation(
         () => new Promise<HealthResponse>(() => {})
      );

      render(<App />);

      expect(
         screen.getByRole("heading", {
            name: "Ludex — Your next game awaits",
         })
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

   it("adds a submitted Steam profile to the visible list", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue([]);
      mockedCreateProfile.mockResolvedValue(importedProfile);

      render(<App />);

      const identifierInput = screen.getByLabelText("Steam ID or profile URL");

      fireEvent.change(identifierInput, {
         target: {
            value: "  example-profile  ",
         },
      });
      fireEvent.click(
         screen.getByRole("button", {
            name: "Add profile",
         })
      );

      expect(mockedCreateProfile).toHaveBeenCalledWith("example-profile");
      expect(await screen.findByText("Imported Player")).toBeInTheDocument();
      expect(identifierInput).toHaveValue("");
   });

   it("disables the form while a profile is being added", () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue([]);
      mockedCreateProfile.mockImplementation(() => new Promise(() => {}));

      render(<App />);

      const identifierInput = screen.getByLabelText("Steam ID or profile URL");

      fireEvent.change(identifierInput, {
         target: {
            value: "example-profile",
         },
      });
      fireEvent.click(
         screen.getByRole("button", {
            name: "Add profile",
         })
      );

      expect(identifierInput).toBeDisabled();
      expect(
         screen.getByRole("button", {
            name: "Adding profile...",
         })
      ).toBeDisabled();
   });

   it("shows the backend message when adding a profile fails", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue([]);
      mockedCreateProfile.mockRejectedValue(
         new ApiError(422, "This Steam library is private or unavailable.")
      );

      render(<App />);

      const identifierInput = screen.getByLabelText("Steam ID or profile URL");

      fireEvent.change(identifierInput, {
         target: {
            value: "private-profile",
         },
      });
      fireEvent.click(
         screen.getByRole("button", {
            name: "Add profile",
         })
      );

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "This Steam library is private or unavailable."
      );
      expect(identifierInput).toHaveValue("private-profile");
      expect(identifierInput).not.toBeDisabled();
   });

   it("updates an existing profile without duplicating it", async () => {
      const updatedProfile = {
         ...savedProfiles[0],
         display_name: "Updated First Player",
         games: [],
      };

      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);
      mockedCreateProfile.mockResolvedValue(updatedProfile);

      render(<App />);

      await screen.findByText("First Player");

      const identifierInput = screen.getByLabelText("Steam ID or profile URL");

      fireEvent.change(identifierInput, {
         target: {
            value: savedProfiles[0].steam_id,
         },
      });
      fireEvent.click(
         screen.getByRole("button", {
            name: "Add profile",
         })
      );

      expect(
         await screen.findByText("Updated First Player")
      ).toBeInTheDocument();
      expect(screen.queryByText("First Player")).not.toBeInTheDocument();
      expect(screen.getAllByText("Updated First Player")).toHaveLength(1);
      expect(screen.getByText("Second Player")).toBeInTheDocument();
   });

   it("selects one saved profile", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);

      render(<App />);

      const firstProfileButton = await screen.findByRole("button", {
         name: "First Player",
      });
      const secondProfileButton = screen.getByRole("button", {
         name: "Second Player",
      });

      expect(firstProfileButton).toHaveAttribute("aria-pressed", "false");
      expect(secondProfileButton).toHaveAttribute("aria-pressed", "false");

      fireEvent.click(secondProfileButton);

      expect(firstProfileButton).toHaveAttribute("aria-pressed", "false");
      expect(secondProfileButton).toHaveAttribute("aria-pressed", "true");
      expect(
         screen.getByText("Second Player", {
            selector: "strong",
         })
      ).toBeInTheDocument();
   });

   it("stores the selected profile ID in browser storage", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);

      render(<App />);

      const secondProfileButton = await screen.findByRole("button", {
         name: "Second Player",
      });

      fireEvent.click(secondProfileButton);

      await waitFor(() => {
         expect(window.localStorage.getItem("ludex.selectedProfileId")).toBe(
            "2"
         );
      });
   });

   it("restores a previously selected profile", async () => {
      window.localStorage.setItem("ludex.selectedProfileId", "2");
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);

      render(<App />);

      const secondProfileButton = await screen.findByRole("button", {
         name: "Second Player",
      });

      expect(secondProfileButton).toHaveAttribute("aria-pressed", "true");
      expect(
         screen.getByText("Second Player", {
            selector: "strong",
         })
      ).toBeInTheDocument();
   });

   it("discards a stored profile ID that no longer exists", async () => {
      window.localStorage.setItem("ludex.selectedProfileId", "999");
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);

      render(<App />);

      await screen.findByText("First Player");

      await waitFor(() => {
         expect(
            window.localStorage.getItem("ludex.selectedProfileId")
         ).toBeNull();
      });

      expect(screen.queryByText(/Selected profile:/)).not.toBeInTheDocument();
   });

   it("loads and displays the selected profile library", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);
      mockedGetProfile.mockResolvedValue(profileWithGames);

      render(<App />);

      fireEvent.click(
         await screen.findByRole("button", {
            name: "Second Player",
         })
      );

      expect(mockedGetProfile).toHaveBeenCalledWith(2);
      expect(
         await screen.findByRole("heading", {
            name: "Game library",
         })
      ).toBeInTheDocument();
      expect(screen.getByText("2 games")).toBeInTheDocument();
      expect(screen.getByText("Alpha Game")).toBeInTheDocument();
      expect(screen.getByText("Beta Game")).toBeInTheDocument();
      expect(screen.getByText(/120 minutes played/)).toBeInTheDocument();
   });

   it("shows loading while retrieving a selected library", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);

      render(<App />);

      fireEvent.click(
         await screen.findByRole("button", {
            name: "First Player",
         })
      );

      expect(screen.getByText("Loading game library...")).toBeInTheDocument();
   });

   it("shows an error when a selected library cannot load", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);
      mockedGetProfile.mockRejectedValue(
         new ApiError(404, "Profile not found.")
      );

      render(<App />);

      fireEvent.click(
         await screen.findByRole("button", {
            name: "First Player",
         })
      );

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Profile not found."
      );
   });

   it("shows an empty selected library", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);
      mockedGetProfile.mockResolvedValue({
         ...savedProfiles[0],
         games: [],
      });

      render(<App />);

      fireEvent.click(
         await screen.findByRole("button", {
            name: "First Player",
         })
      );

      expect(
         await screen.findByText("This Steam library is empty.")
      ).toBeInTheDocument();
      expect(screen.getByText("0 games")).toBeInTheDocument();
   });

   it("disables the refresh action while the library is refreshing", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);
      mockedGetProfile.mockResolvedValue(profileWithGames);
      mockedRefreshProfile.mockImplementation(() => new Promise(() => {}));

      render(<App />);

      fireEvent.click(
         await screen.findByRole("button", {
            name: "Second Player",
         })
      );

      const refreshButton = await screen.findByRole("button", {
         name: "Refresh library",
      });

      fireEvent.click(refreshButton);

      expect(mockedRefreshProfile).toHaveBeenCalledWith(2);
      expect(
         screen.getByRole("button", {
            name: "Refreshing library...",
         })
      ).toBeDisabled();
      expect(screen.getByText("Alpha Game")).toBeInTheDocument();
   });

   it("updates the selected profile after a successful refresh", async () => {
      const refreshedProfile: ProfileDetailResponse = {
         ...profileWithGames,
         display_name: "Refreshed Second Player",
         last_synced_at: "2026-08-04T12:00:00Z",
         games: [
            ...profileWithGames.games,
            {
               steam_app_id: 30,
               name: "Gamma Game",
               icon_url: null,
               playtime_minutes: 45,
               recent_playtime_minutes: null,
               last_played_at: null,
            },
         ],
      };

      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);
      mockedGetProfile.mockResolvedValue(profileWithGames);
      mockedRefreshProfile.mockResolvedValue(refreshedProfile);

      render(<App />);

      fireEvent.click(
         await screen.findByRole("button", {
            name: "Second Player",
         })
      );

      fireEvent.click(
         await screen.findByRole("button", {
            name: "Refresh library",
         })
      );

      expect(await screen.findByRole("status")).toHaveTextContent(
         "Steam library refreshed."
      );
      expect(screen.getByText("3 games")).toBeInTheDocument();
      expect(screen.getByText("Gamma Game")).toBeInTheDocument();
      expect(
         screen.getByRole("button", {
            name: "Refreshed Second Player",
         })
      ).toBeInTheDocument();
      expect(
         screen.getByText("Refreshed Second Player", {
            selector: "strong",
         })
      ).toBeInTheDocument();
   });

   it("preserves the cached library when a refresh fails", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });
      mockedListProfiles.mockResolvedValue(savedProfiles);
      mockedGetProfile.mockResolvedValue(profileWithGames);
      mockedRefreshProfile.mockRejectedValue(
         new ApiError(503, "Steam is currently unavailable.")
      );

      render(<App />);

      fireEvent.click(
         await screen.findByRole("button", {
            name: "Second Player",
         })
      );

      fireEvent.click(
         await screen.findByRole("button", {
            name: "Refresh library",
         })
      );

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Steam is currently unavailable."
      );
      expect(screen.getByText("2 games")).toBeInTheDocument();
      expect(screen.getByText("Alpha Game")).toBeInTheDocument();
      expect(screen.getByText("Beta Game")).toBeInTheDocument();
      expect(
         screen.getByRole("button", {
            name: "Refresh library",
         })
      ).not.toBeDisabled();
   });
});
