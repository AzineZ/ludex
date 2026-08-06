import type { ProfileSummaryResponse } from "../../api";

/** Inserts or replaces a profile while preserving display-name order. */
export function upsertProfile(
   profiles: ProfileSummaryResponse[],
   updatedProfile: ProfileSummaryResponse
): ProfileSummaryResponse[] {
   return [
      ...profiles.filter((profile) => profile.id !== updatedProfile.id),
      updatedProfile,
   ].sort(
      (firstProfile, secondProfile) =>
         firstProfile.display_name.localeCompare(secondProfile.display_name) ||
         firstProfile.id - secondProfile.id
   );
}
