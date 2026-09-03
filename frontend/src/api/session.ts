import { requestJson, requestNoContent } from "./client";

export type OwnedGameResponse = {
   steam_app_id: number;
   name: string;
   icon_url: string | null;
   playtime_minutes: number;
   recent_playtime_minutes: number | null;
   last_played_at: string | null;
};

/** The cached Steam profile authorized by this browser's session cookie. */
export type SessionProfileResponse = {
   steam_id: string;
   display_name: string;
   profile_url: string | null;
   avatar_url: string | null;
   created_at: string;
   last_synced_at: string | null;
   games: OwnedGameResponse[];
};

export function createAccessSession(
   identifier: string
): Promise<SessionProfileResponse> {
   return requestJson<SessionProfileResponse>("/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier }),
   });
}

export function getCurrentSessionProfile(): Promise<SessionProfileResponse> {
   return requestJson<SessionProfileResponse>("/session/profile");
}

export function refreshCurrentSessionProfile(): Promise<SessionProfileResponse> {
   return requestJson<SessionProfileResponse>("/session/profile/refresh", {
      method: "POST",
   });
}

export function deleteAccessSession(): Promise<void> {
   return requestNoContent("/session", { method: "DELETE" });
}
