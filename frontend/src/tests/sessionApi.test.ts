import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   createAccessSession,
   deleteAccessSession,
   getCurrentSessionProfile,
   refreshCurrentSessionProfile,
   type SessionProfileResponse,
} from "../api";

const sessionProfile: SessionProfileResponse = {
   steam_id: "76561198000000000",
   display_name: "Test Player",
   profile_url: "https://steamcommunity.com/profiles/test/",
   avatar_url: null,
   created_at: "2026-08-01T12:00:00Z",
   last_synced_at: "2026-08-01T12:00:00Z",
   games: [],
};

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(responseData: unknown, status = 200): Response {
   return new Response(JSON.stringify(responseData), {
      status,
      headers: { "Content-Type": "application/json" },
   });
}

describe("session API", () => {
   beforeEach(() => {
      fetchMock.mockReset();
      vi.stubGlobal("fetch", fetchMock);
   });

   afterEach(() => vi.unstubAllGlobals());

   it("creates an access session from a Steam identifier", async () => {
      fetchMock.mockResolvedValue(jsonResponse(sessionProfile, 201));

      await expect(
         createAccessSession(sessionProfile.steam_id)
      ).resolves.toEqual(sessionProfile);

      expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/session", {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({ identifier: sessionProfile.steam_id }),
         credentials: "include",
      });
   });

   it("loads only the profile authorized by the browser cookie", async () => {
      fetchMock.mockResolvedValue(jsonResponse(sessionProfile));

      await expect(getCurrentSessionProfile()).resolves.toEqual(sessionProfile);

      expect(fetchMock).toHaveBeenCalledWith(
         "http://localhost:8000/session/profile",
         { credentials: "include" }
      );
   });

   it("refreshes the current session profile without an exposed ID", async () => {
      fetchMock.mockResolvedValue(jsonResponse(sessionProfile));

      await expect(refreshCurrentSessionProfile()).resolves.toEqual(
         sessionProfile
      );

      expect(fetchMock).toHaveBeenCalledWith(
         "http://localhost:8000/session/profile/refresh",
         { method: "POST", credentials: "include" }
      );
   });

   it("ends the session without trying to decode the empty response", async () => {
      fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

      await expect(deleteAccessSession()).resolves.toBeUndefined();

      expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/session", {
         method: "DELETE",
         credentials: "include",
      });
   });

   it("preserves backend errors for session requests", async () => {
      fetchMock.mockResolvedValue(
         jsonResponse({ detail: "Steam access session required." }, 401)
      );

      const request = getCurrentSessionProfile();
      await expect(request).rejects.toMatchObject({
         name: "ApiError",
         status: 401,
         message: "Steam access session required.",
      });
      await expect(request).rejects.toBeInstanceOf(ApiError);
   });

   it("uses a fallback message when an error response is invalid", async () => {
      fetchMock.mockResolvedValue(new Response("not-json", { status: 502 }));

      await expect(getCurrentSessionProfile()).rejects.toMatchObject({
         name: "ApiError",
         status: 502,
         message: "Request failed with status 502.",
      });
   });
});
