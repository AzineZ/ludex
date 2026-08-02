import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
   ApiError,
   createProfile,
   getProfile,
   listProfiles,
   refreshProfile,
   type ProfileDetailResponse,
   type ProfileSummaryResponse,
} from "./api";

const profileSummary: ProfileSummaryResponse = {
   id: 1,
   steam_id: "76561198000000000",
   display_name: "Test Player",
   profile_url: "https://steamcommunity.com/profiles/test/",
   avatar_url: null,
   created_at: "2026-08-01T12:00:00Z",
   last_synced_at: "2026-08-01T12:00:00Z",
};

const profileDetail: ProfileDetailResponse = {
   ...profileSummary,
   games: [],
};

const fetchMock = vi.fn<typeof fetch>();

/** Creates a JSON response with the requested HTTP status. */
function jsonResponse(responseData: unknown, status = 200): Response {
   return new Response(JSON.stringify(responseData), {
      status,
      headers: {
         "Content-Type": "application/json",
      },
   });
}

describe("profile API", () => {
   beforeEach(() => {
      fetchMock.mockReset();
      vi.stubGlobal("fetch", fetchMock);
   });

   afterEach(() => {
      vi.unstubAllGlobals();
   });

   it("requests the saved profile list", async () => {
      fetchMock.mockResolvedValue(jsonResponse([profileSummary]));

      await expect(listProfiles()).resolves.toEqual([profileSummary]);

      expect(fetchMock).toHaveBeenCalledWith(
         "http://localhost:8000/profiles",
         undefined
      );
   });

   it("submits a Steam identifier to create a profile", async () => {
      fetchMock.mockResolvedValue(jsonResponse(profileDetail));

      await expect(createProfile(profileSummary.steam_id)).resolves.toEqual(
         profileDetail
      );

      expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/profiles", {
         method: "POST",
         headers: {
            "Content-Type": "application/json",
         },
         body: JSON.stringify({
            identifier: profileSummary.steam_id,
         }),
      });
   });
   it("requests one cached profile and its library", async () => {
      fetchMock.mockResolvedValue(jsonResponse(profileDetail));

      await expect(getProfile(profileSummary.id)).resolves.toEqual(
         profileDetail
      );

      expect(fetchMock).toHaveBeenCalledWith(
         "http://localhost:8000/profiles/1",
         undefined
      );
   });

   it("requests a Steam refresh for one profile", async () => {
      fetchMock.mockResolvedValue(jsonResponse(profileDetail));

      await expect(refreshProfile(profileSummary.id)).resolves.toEqual(
         profileDetail
      );

      expect(fetchMock).toHaveBeenCalledWith(
         "http://localhost:8000/profiles/1/refresh",
         {
            method: "POST",
         }
      );
   });
   it("preserves the backend error status and message", async () => {
      fetchMock.mockImplementation(async () =>
         jsonResponse(
            {
               detail: "Steam is currently unavailable.",
            },
            503
         )
      );

      await expect(listProfiles()).rejects.toMatchObject({
         name: "ApiError",
         status: 503,
         message: "Steam is currently unavailable.",
      });

      await expect(listProfiles()).rejects.toBeInstanceOf(ApiError);
   });

   it("uses a fallback message when an error response is invalid", async () => {
      fetchMock.mockResolvedValue(
         new Response("not-json", {
            status: 502,
         })
      );

      await expect(listProfiles()).rejects.toMatchObject({
         name: "ApiError",
         status: 502,
         message: "Request failed with status 502.",
      });
   });
});
