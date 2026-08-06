import type {
   ProfileDetailResponse,
   ProfileSummaryResponse,
} from "../api";

export const savedProfiles: ProfileSummaryResponse[] = [
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

export const profileWithGames: ProfileDetailResponse = {
   ...savedProfiles[1],
   games: [
      {
         steam_app_id: 10,
         name: "Alpha Game",
         icon_url: null,
         playtime_minutes: 120,
         recent_playtime_minutes: 30,
         last_played_at: null,
      },
      {
         steam_app_id: 20,
         name: "Beta Game",
         icon_url: null,
         playtime_minutes: 0,
         recent_playtime_minutes: null,
         last_played_at: null,
      },
   ],
};

export const importedProfile: ProfileDetailResponse = {
   ...savedProfiles[0],
   id: 3,
   display_name: "Imported Player",
   games: [],
};
