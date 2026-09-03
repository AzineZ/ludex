import { requestJson } from "./client";
import type { OwnedGameResponse } from "./session";

/** Represents a saved profile without its game library. */
export type ProfileSummaryResponse = {
   id: number;
   steam_id: string;
   display_name: string;
   profile_url: string | null;
   avatar_url: string | null;
   created_at: string;
   last_synced_at: string | null;
};

/** Represents a saved profile and its cached game library. */
export type ProfileDetailResponse = ProfileSummaryResponse & {
   games: OwnedGameResponse[];
};

/** Returns summaries for every profile saved in Ludex. */
export function listProfiles(): Promise<ProfileSummaryResponse[]> {
   return requestJson<ProfileSummaryResponse[]>("/profiles");
}

/** Imports or re-imports a Steam profile and its owned games. */
export function createProfile(
   identifier: string
): Promise<ProfileDetailResponse> {
   return requestJson<ProfileDetailResponse>("/profiles", {
      method: "POST",
      headers: {
         "Content-Type": "application/json",
      },
      body: JSON.stringify({ identifier }),
   });
}

/** Returns one saved profile and its cached game library. */
export function getProfile(profileId: number): Promise<ProfileDetailResponse> {
   return requestJson<ProfileDetailResponse>(`/profiles/${profileId}`);
}

/** Refreshes one saved profile and its game library from Steam. */
export function refreshProfile(
   profileId: number
): Promise<ProfileDetailResponse> {
   return requestJson<ProfileDetailResponse>(`/profiles/${profileId}/refresh`, {
      method: "POST",
   });
}
