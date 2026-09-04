import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   createAccessSession,
   getCurrentSessionProfile,
   refreshCurrentSessionProfile,
   type SessionProfileResponse,
} from "../api";
import AccessSessionSection from "../features/session/AccessSessionSection";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();
   return {
      ...actual,
      createAccessSession: vi.fn(),
      getCurrentSessionProfile: vi.fn(),
      refreshCurrentSessionProfile: vi.fn(),
   };
});
vi.mock("../features/recommendations/ReferenceSelectionSection", () => ({
   default: () => null,
}));

const originalProfile: SessionProfileResponse = {
   steam_id: "76561198000000001",
   display_name: "Session Player",
   profile_url: null,
   avatar_url: null,
   created_at: "2026-09-03T12:00:00Z",
   last_synced_at: "2026-09-03T12:00:00Z",
   games: [{
      steam_app_id: 620,
      name: "Portal 2",
      icon_url: null,
      playtime_minutes: 120,
      recent_playtime_minutes: null,
      last_played_at: null,
   }],
};
const refreshedProfile: SessionProfileResponse = {
   ...originalProfile,
   games: [{
      ...originalProfile.games[0],
      steam_app_id: 400,
      name: "Portal",
   }],
};
const mockedCreate = vi.mocked(createAccessSession);
const mockedGetCurrent = vi.mocked(getCurrentSessionProfile);
const mockedRefresh = vi.mocked(refreshCurrentSessionProfile);

describe("AccessSessionSection action recovery", () => {
   beforeEach(() => {
      mockedCreate.mockReset();
      mockedGetCurrent.mockReset();
      mockedRefresh.mockReset();
   });

   it("preserves the entered Steam ID and retries failed profile creation", async () => {
      mockedGetCurrent.mockRejectedValueOnce(new ApiError(401, "Required."));
      mockedCreate
         .mockRejectedValueOnce(new ApiError(503, "Steam is temporarily unavailable."))
         .mockResolvedValueOnce(originalProfile);
      render(<AccessSessionSection />);

      const input = await screen.findByRole("textbox", {
         name: "Steam ID or profile URL",
      });
      fireEvent.change(input, { target: { value: originalProfile.steam_id } });
      fireEvent.click(screen.getByRole("button", { name: "Continue with Steam" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Steam is temporarily unavailable."
      );
      expect(input).toHaveValue(originalProfile.steam_id);
      fireEvent.click(screen.getByRole("button", { name: "Continue with Steam" }));

      expect(await screen.findByText("Session Player")).toBeInTheDocument();
      expect(mockedCreate).toHaveBeenCalledTimes(2);
   });

   it("preserves the cached library and retries a failed refresh", async () => {
      mockedGetCurrent.mockResolvedValueOnce(originalProfile);
      mockedRefresh
         .mockRejectedValueOnce(new ApiError(503, "Steam is temporarily unavailable."))
         .mockResolvedValueOnce(refreshedProfile);
      render(<AccessSessionSection />);

      await screen.findByText("Portal 2");
      fireEvent.click(screen.getByRole("button", { name: "Refresh library" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Steam is temporarily unavailable."
      );
      expect(screen.getByText("Portal 2")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Refresh library" }));

      expect(await screen.findByText("Portal")).toBeInTheDocument();
      expect(screen.queryByText("Portal 2")).not.toBeInTheDocument();
      expect(mockedRefresh).toHaveBeenCalledTimes(2);
   });
});
