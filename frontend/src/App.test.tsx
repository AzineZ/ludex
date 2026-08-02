import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
   ApiError,
   createProfile,
   getHealth,
   listProfiles,
   type HealthResponse,
   type ProfileSummaryResponse,
} from "./api";

vi.mock("./api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("./api")>();

   return {
      ...actual,
      createProfile: vi.fn(),
      getHealth: vi.fn(),
      listProfiles: vi.fn(),
   };
});

const mockedCreateProfile = vi.mocked(createProfile);
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

const importedProfile = {
   ...savedProfiles[0],
   id: 3,
   display_name: "Imported Player",
   games: [],
};

describe("App", () => {
   beforeEach(() => {
      mockedCreateProfile.mockReset();
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
});
