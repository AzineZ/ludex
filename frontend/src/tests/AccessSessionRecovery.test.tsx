import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   createAccessSession,
   getCurrentSessionProfile,
   type SessionProfileResponse,
} from "../api";
import AccessSessionSection from "../features/session/AccessSessionSection";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();
   return {
      ...actual,
      createAccessSession: vi.fn(),
      getCurrentSessionProfile: vi.fn(),
   };
});
vi.mock("../features/session/SessionGameLibrary", () => ({ default: () => null }));
vi.mock("../features/recommendations/ReferenceSelectionSection", () => ({
   default: () => null,
}));

type Deferred<Value> = {
   promise: Promise<Value>;
   resolve: (value: Value) => void;
};

function deferred<Value>(): Deferred<Value> {
   let resolve!: (value: Value) => void;
   const promise = new Promise<Value>((resolvePromise) => {
      resolve = resolvePromise;
   });
   return { promise, resolve };
}

function profile(displayName: string, steamId: string): SessionProfileResponse {
   return {
      steam_id: steamId,
      display_name: displayName,
      profile_url: null,
      avatar_url: null,
      created_at: "2026-09-03T12:00:00Z",
      last_synced_at: null,
      games: [],
   };
}

const restoredProfile = profile("Restored Player", "76561198000000001");
const enteredProfile = profile("Entered Player", "76561198000000002");
const mockedCreate = vi.mocked(createAccessSession);
const mockedGetCurrent = vi.mocked(getCurrentSessionProfile);

describe("AccessSessionSection startup recovery", () => {
   beforeEach(() => {
      mockedCreate.mockReset();
      mockedGetCurrent.mockReset();
   });

   it("keeps the Steam-ID form usable beside one safe startup error and retry action", async () => {
      mockedGetCurrent.mockRejectedValueOnce(
         new Error("connect ECONNREFUSED private-session-host:8000")
      );
      mockedCreate.mockResolvedValueOnce(enteredProfile);

      render(<AccessSessionSection />);

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Your saved session could not be checked."
      );
      expect(screen.getAllByRole("alert")).toHaveLength(1);
      expect(screen.queryByText(/private-session-host/)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();

      const identifier = screen.getByRole("textbox", {
         name: "Steam ID or profile URL",
      });
      fireEvent.change(identifier, { target: { value: enteredProfile.steam_id } });
      fireEvent.click(screen.getByRole("button", { name: "Continue with Steam" }));

      expect(
         await screen.findByText(`Current Steam profile:`, { exact: false })
      ).toHaveTextContent(enteredProfile.display_name);
   });

   it("recovers an unavailable startup check to the authorized profile", async () => {
      mockedGetCurrent
         .mockRejectedValueOnce(new Error("offline"))
         .mockResolvedValueOnce(restoredProfile);

      render(<AccessSessionSection />);
      fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

      expect(
         await screen.findByText(`Current Steam profile:`, { exact: false })
      ).toHaveTextContent(restoredProfile.display_name);
      expect(mockedGetCurrent).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
   });

   it("recovers a retry 401 to the ordinary signed-out state", async () => {
      mockedGetCurrent
         .mockRejectedValueOnce(new Error("offline"))
         .mockRejectedValueOnce(new ApiError(401, "Steam access session required."));

      render(<AccessSessionSection />);
      fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

      await waitFor(() => {
         expect(screen.queryByRole("alert")).not.toBeInTheDocument();
         expect(
            screen.queryByRole("button", { name: "Try again" })
         ).not.toBeInTheDocument();
      });
      expect(
         screen.getByRole("textbox", { name: "Steam ID or profile URL" })
      ).toBeEnabled();
   });

   it("does not let an older restoration response replace a newly started session", async () => {
      const olderRetry = deferred<SessionProfileResponse>();
      mockedGetCurrent
         .mockRejectedValueOnce(new Error("offline"))
         .mockReturnValueOnce(olderRetry.promise);
      mockedCreate.mockResolvedValueOnce(enteredProfile);

      render(<AccessSessionSection />);
      fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

      const identifier = screen.getByRole("textbox", {
         name: "Steam ID or profile URL",
      });
      fireEvent.change(identifier, { target: { value: enteredProfile.steam_id } });
      fireEvent.click(screen.getByRole("button", { name: "Continue with Steam" }));
      expect(
         await screen.findByText(`Current Steam profile:`, { exact: false })
      ).toHaveTextContent(enteredProfile.display_name);

      await act(async () => olderRetry.resolve(restoredProfile));

      expect(screen.getByText(`Current Steam profile:`, { exact: false })).toHaveTextContent(
         enteredProfile.display_name
      );
      expect(screen.queryByText(restoredProfile.display_name)).not.toBeInTheDocument();
   });
});
