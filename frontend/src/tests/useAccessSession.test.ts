import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   createAccessSession,
   deleteAccessSession,
   getCurrentSessionProfile,
   refreshCurrentSessionProfile,
   type SessionProfileResponse,
} from "../api";
import { useAccessSession } from "../features/session/useAccessSession";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();
   return {
      ...actual,
      createAccessSession: vi.fn(),
      deleteAccessSession: vi.fn(),
      getCurrentSessionProfile: vi.fn(),
      refreshCurrentSessionProfile: vi.fn(),
   };
});

const profile: SessionProfileResponse = {
   steam_id: "76561198000000000",
   display_name: "Test Player",
   profile_url: null,
   avatar_url: null,
   created_at: "2026-08-01T12:00:00Z",
   last_synced_at: null,
   games: [],
};

const refreshedProfile = { ...profile, display_name: "Updated Player" };
const mockedCreate = vi.mocked(createAccessSession);
const mockedDelete = vi.mocked(deleteAccessSession);
const mockedGetCurrent = vi.mocked(getCurrentSessionProfile);
const mockedRefresh = vi.mocked(refreshCurrentSessionProfile);

describe("useAccessSession", () => {
   beforeEach(() => {
      mockedCreate.mockReset();
      mockedDelete.mockReset();
      mockedGetCurrent.mockReset();
      mockedRefresh.mockReset();
   });

   afterEach(() => {
      vi.useRealTimers();
   });

   it("restores the cookie-authorized profile on startup", async () => {
      mockedGetCurrent.mockResolvedValue(profile);
      const { result } = renderHook(() => useAccessSession());

      expect(result.current.status).toBe("loading");
      await waitFor(() => expect(result.current.status).toBe("ready"));
      expect(result.current.profile).toEqual(profile);
      expect(result.current.sessionEpoch).toBe(0);
   });

   it("treats a startup 401 as an ordinary signed-out browser", async () => {
      mockedGetCurrent.mockRejectedValue(
         new ApiError(401, "Steam access session required.")
      );
      const { result } = renderHook(() => useAccessSession());

      await waitFor(() => expect(result.current.status).toBe("signed_out"));
      expect(result.current.profile).toBeNull();
      expect(result.current.startupError).toBeNull();
   });

   it("keeps a non-authentication startup failure visible", async () => {
      mockedGetCurrent.mockRejectedValue(new ApiError(503, "Try again later."));
      const { result } = renderHook(() => useAccessSession());

      await waitFor(() => expect(result.current.status).toBe("unavailable"));
      expect(result.current.startupError).toBe("Try again later.");
   });

   it("creates a trimmed session and advances the recommendation epoch", async () => {
      mockedGetCurrent.mockRejectedValue(new ApiError(401, "Required."));
      mockedCreate.mockResolvedValue(profile);
      const { result } = renderHook(() => useAccessSession());
      await waitFor(() => expect(result.current.status).toBe("signed_out"));

      await act(async () => {
         await expect(
            result.current.startSession(`  ${profile.steam_id}  `)
         ).resolves.toBe(true);
      });

      expect(mockedCreate).toHaveBeenCalledWith(profile.steam_id);
      expect(result.current).toMatchObject({
         status: "ready",
         profile,
         sessionEpoch: 1,
         startError: null,
      });
   });

   it("retains the current profile when starting another session fails", async () => {
      mockedGetCurrent.mockResolvedValue(profile);
      mockedCreate.mockRejectedValue(new ApiError(404, "Profile not found."));
      const { result } = renderHook(() => useAccessSession());
      await waitFor(() => expect(result.current.status).toBe("ready"));

      await act(async () => {
         await expect(result.current.startSession("missing")).resolves.toBe(
            false
         );
      });

      expect(result.current.profile).toEqual(profile);
      expect(result.current.startError).toBe("Profile not found.");
      expect(result.current.sessionEpoch).toBe(0);
   });

   it("refreshes the same session without invalidating recommendations", async () => {
      mockedGetCurrent.mockResolvedValue(profile);
      mockedRefresh.mockResolvedValue(refreshedProfile);
      const { result } = renderHook(() => useAccessSession());
      await waitFor(() => expect(result.current.status).toBe("ready"));

      await act(async () => result.current.refreshSessionProfile());

      expect(result.current.profile).toEqual(refreshedProfile);
      expect(result.current.sessionEpoch).toBe(0);
      expect(result.current.refreshError).toBeNull();
   });

   it("clears the successful refresh confirmation after one second", async () => {
      mockedGetCurrent.mockResolvedValue(profile);
      mockedRefresh.mockResolvedValue(refreshedProfile);
      const { result } = renderHook(() => useAccessSession());
      await waitFor(() => expect(result.current.status).toBe("ready"));
      vi.useFakeTimers();

      await act(async () => result.current.refreshSessionProfile());

      expect(result.current.refreshSucceeded).toBe(true);
      act(() => vi.advanceTimersByTime(999));
      expect(result.current.refreshSucceeded).toBe(true);
      act(() => vi.advanceTimersByTime(1));
      expect(result.current.refreshSucceeded).toBe(false);
   });

   it("ends the session and advances the recommendation epoch", async () => {
      mockedGetCurrent.mockResolvedValue(profile);
      mockedDelete.mockResolvedValue(undefined);
      const { result } = renderHook(() => useAccessSession());
      await waitFor(() => expect(result.current.status).toBe("ready"));

      await act(async () => {
         await expect(result.current.endSession()).resolves.toBe(true);
      });

      expect(result.current).toMatchObject({
         status: "signed_out",
         profile: null,
         sessionEpoch: 1,
         endError: null,
      });
   });

   it("retains the current profile when ending the session fails", async () => {
      mockedGetCurrent.mockResolvedValue(profile);
      mockedDelete.mockRejectedValue(new ApiError(503, "Try again later."));
      const { result } = renderHook(() => useAccessSession());
      await waitFor(() => expect(result.current.status).toBe("ready"));

      await act(async () => {
         await expect(result.current.endSession()).resolves.toBe(false);
      });

      expect(result.current.profile).toEqual(profile);
      expect(result.current.endError).toBe("Try again later.");
      expect(result.current.sessionEpoch).toBe(0);
   });

   it("clears stale state when a protected request reports 401", async () => {
      mockedGetCurrent.mockResolvedValue(profile);
      const { result } = renderHook(() => useAccessSession());
      await waitFor(() => expect(result.current.status).toBe("ready"));

      act(() => result.current.handleSessionUnauthorized());

      expect(result.current).toMatchObject({
         status: "signed_out",
         profile: null,
         sessionEpoch: 1,
      });
   });
});
