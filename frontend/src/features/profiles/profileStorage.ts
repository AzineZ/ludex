const SELECTED_PROFILE_STORAGE_KEY = "ludex.selectedProfileId";

/** Reads and validates the previously selected local profile ID. */
export function getStoredProfileId(): number | null {
   const storedProfileId = window.localStorage.getItem(
      SELECTED_PROFILE_STORAGE_KEY
   );

   if (storedProfileId === null) {
      return null;
   }

   const profileId = Number(storedProfileId);

   return Number.isSafeInteger(profileId) && profileId > 0 ? profileId : null;
}

/** Persists a selected profile ID or clears an obsolete selection. */
export function storeProfileId(profileId: number | null): void {
   if (profileId === null) {
      window.localStorage.removeItem(SELECTED_PROFILE_STORAGE_KEY);
      return;
   }

   window.localStorage.setItem(SELECTED_PROFILE_STORAGE_KEY, String(profileId));
}
