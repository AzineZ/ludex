import { useEffect, useRef, useState } from "react";
import {
   ApiError,
   createProfile,
   getProfile,
   listProfiles,
   refreshProfile as requestProfileRefresh,
   type ProfileDetailResponse,
   type ProfileSummaryResponse,
} from "../../api";
import { getStoredProfileId, storeProfileId } from "./profileStorage";
import { upsertProfile } from "./profileUtils";
import type {
   ProfileDetailState,
   ProfileListState,
   RefreshState,
} from "./types";

type ProfileDetailResult = {
   profileId: number;
   profile: ProfileDetailResponse | null;
   error: string | null;
};

/** Owns profile import, selection, cached-library, and refresh behavior. */
export function useProfiles() {
   const [profileListState, setProfileListState] =
      useState<ProfileListState>("loading");
   const [profiles, setProfiles] = useState<ProfileSummaryResponse[]>([]);
   const [selectedProfileId, setSelectedProfileId] = useState<number | null>(
      getStoredProfileId
   );
   const selectedProfileIdRef = useRef(selectedProfileId);
   const [profileDetailResult, setProfileDetailResult] =
      useState<ProfileDetailResult | null>(null);
   const [isAddingProfile, setIsAddingProfile] = useState(false);
   const [addProfileError, setAddProfileError] = useState<string | null>(null);
   const [refreshState, setRefreshState] = useState<RefreshState>("idle");
   const [refreshError, setRefreshError] = useState<string | null>(null);

   useEffect(() => {
      listProfiles()
         .then((savedProfiles) => {
            setProfiles(savedProfiles);
            setSelectedProfileId((currentProfileId) => {
               if (currentProfileId === null) {
                  return null;
               }

               const profileStillExists = savedProfiles.some(
                  (profile) => profile.id === currentProfileId
               );

               return profileStillExists ? currentProfileId : null;
            });
            setProfileListState("ready");
         })
         .catch(() => {
            setProfileListState("unavailable");
         });
   }, []);

   useEffect(() => {
      selectedProfileIdRef.current = selectedProfileId;
      storeProfileId(selectedProfileId);
   }, [selectedProfileId]);

   useEffect(() => {
      if (profileListState !== "ready" || selectedProfileId === null) {
         return;
      }

      let requestIsCurrent = true;

      getProfile(selectedProfileId)
         .then((profile) => {
            if (!requestIsCurrent) {
               return;
            }

            setProfileDetailResult({
               profileId: selectedProfileId,
               profile,
               error: null,
            });
         })
         .catch((error) => {
            if (!requestIsCurrent) {
               return;
            }

            setProfileDetailResult({
               profileId: selectedProfileId,
               profile: null,
               error:
                  error instanceof ApiError
                     ? error.message
                     : "The game library could not be loaded.",
            });
         });

      return () => {
         requestIsCurrent = false;
      };
   }, [profileListState, selectedProfileId]);

   const currentProfileDetailResult =
      profileDetailResult?.profileId === selectedProfileId
         ? profileDetailResult
         : null;
   const selectedProfileDetail = currentProfileDetailResult?.profile ?? null;
   const profileDetailError = currentProfileDetailResult?.error ?? null;

   let profileDetailState: ProfileDetailState = "idle";

   if (profileListState === "ready" && selectedProfileId !== null) {
      if (selectedProfileDetail !== null) {
         profileDetailState = "ready";
      } else if (profileDetailError !== null) {
         profileDetailState = "unavailable";
      } else {
         profileDetailState = "loading";
      }
   }

   const selectedProfileSummary =
      profiles.find((profile) => profile.id === selectedProfileId) ?? null;

   /** Imports a Steam profile submitted through the form. */
   async function addProfile(identifier: string): Promise<boolean> {
      const normalizedIdentifier = identifier.trim();

      if (!normalizedIdentifier || isAddingProfile) {
         return false;
      }

      setIsAddingProfile(true);
      setAddProfileError(null);

      try {
         const importedProfile = await createProfile(normalizedIdentifier);

         setProfiles((currentProfiles) =>
            upsertProfile(currentProfiles, importedProfile)
         );
         setProfileListState("ready");
         return true;
      } catch (error) {
         setAddProfileError(
            error instanceof ApiError
               ? error.message
               : "The profile could not be added."
         );
         return false;
      } finally {
         setIsAddingProfile(false);
      }
   }

   /** Refreshes the selected profile and its Steam library. */
   async function refreshSelectedProfile(): Promise<void> {
      if (selectedProfileId === null || refreshState === "refreshing") {
         return;
      }

      const refreshingProfileId = selectedProfileId;

      setRefreshState("refreshing");
      setRefreshError(null);

      try {
         const refreshedProfile = await requestProfileRefresh(
            refreshingProfileId
         );

         setProfiles((currentProfiles) =>
            upsertProfile(currentProfiles, refreshedProfile)
         );

         if (selectedProfileIdRef.current !== refreshingProfileId) {
            return;
         }

         setProfileDetailResult({
            profileId: refreshingProfileId,
            profile: refreshedProfile,
            error: null,
         });
         setRefreshState("succeeded");
      } catch (error) {
         if (selectedProfileIdRef.current !== refreshingProfileId) {
            return;
         }

         setRefreshError(
            error instanceof ApiError
               ? error.message
               : "The Steam library could not be refreshed."
         );
         setRefreshState("failed");
      }
   }

   function selectProfile(profileId: number): void {
      selectedProfileIdRef.current = profileId;
      setSelectedProfileId(profileId);
      setRefreshState("idle");
      setRefreshError(null);
   }

   return {
      addProfile,
      addProfileError,
      isAddingProfile,
      profileDetailError,
      profileDetailState,
      profileListState,
      profiles,
      refreshError,
      refreshSelectedProfile,
      refreshState,
      selectedProfileDetail,
      selectedProfileId,
      selectedProfileSummary,
      selectProfile,
   };
}
