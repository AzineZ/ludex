export type HealthResponse = {
   status: string;
   database: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

if (!apiBaseUrl) {
   throw new Error("VITE_API_BASE_URL is not configured.");
}

/** Represents an unsuccessful response returned by the Ludex API. */
export class ApiError extends Error {
   readonly status: number;

   constructor(status: number, message: string) {
      super(message);
      this.name = "ApiError";
      this.status = status;
   }
}

/** Extracts a useful message from an unsuccessful API response. */
async function getErrorMessage(response: Response): Promise<string> {
   const fallbackMessage = `Request failed with status ${response.status}.`;
   const responseData: unknown = await response.json().catch(() => null);

   if (
      typeof responseData === "object" &&
      responseData !== null &&
      "detail" in responseData &&
      typeof responseData.detail === "string"
   ) {
      return responseData.detail;
   }

   return fallbackMessage;
}

/** Sends a request to the Ludex API and returns its decoded JSON response. */
async function requestJson<ResponseType>(
   path: string,
   options?: RequestInit
): Promise<ResponseType> {
   const response = await fetch(`${apiBaseUrl}${path}`, options);

   if (!response.ok) {
      throw new ApiError(response.status, await getErrorMessage(response));
   }

   return response.json() as Promise<ResponseType>;
}

/** Checks whether the backend and database are available. */
export function getHealth(): Promise<HealthResponse> {
   return requestJson<HealthResponse>("/health");
}

/** Represents one owned Steam game returned for a profile. */
export type OwnedGameResponse = {
   steam_app_id: number;
   name: string;
   icon_url: string | null;
   playtime_minutes: number;
   recent_playtime_minutes: number | null;
   last_played_at: string | null;
};

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
