import { useEffect, useState } from "react";

import {
   ApiError,
   createAccessSession,
   deleteAccessSession,
   getCurrentSessionProfile,
   refreshCurrentSessionProfile,
   type SessionProfileResponse,
} from "../../api";

export type AccessSessionStatus =
   | "loading"
   | "signed_out"
   | "ready"
   | "unavailable";

function errorMessage(error: unknown, fallback: string): string {
   return error instanceof ApiError ? error.message : fallback;
}

/** Owns this tab's view of the browser access session. */
export function useAccessSession() {
   const [status, setStatus] = useState<AccessSessionStatus>("loading");
   const [profile, setProfile] = useState<SessionProfileResponse | null>(null);
   const [sessionEpoch, setSessionEpoch] = useState(0);
   const [startupError, setStartupError] = useState<string | null>(null);
   const [isStarting, setIsStarting] = useState(false);
   const [startError, setStartError] = useState<string | null>(null);
   const [isRefreshing, setIsRefreshing] = useState(false);
   const [refreshError, setRefreshError] = useState<string | null>(null);
   const [isEnding, setIsEnding] = useState(false);
   const [endError, setEndError] = useState<string | null>(null);

   useEffect(() => {
      let requestIsCurrent = true;

      getCurrentSessionProfile()
         .then((currentProfile) => {
            if (!requestIsCurrent) return;
            setProfile(currentProfile);
            setStatus("ready");
         })
         .catch((error: unknown) => {
            if (!requestIsCurrent) return;
            setProfile(null);
            if (error instanceof ApiError && error.status === 401) {
               setStatus("signed_out");
               setStartupError(null);
               return;
            }
            setStatus("unavailable");
            setStartupError(
               errorMessage(error, "Your saved session could not be checked.")
            );
         });

      return () => {
         requestIsCurrent = false;
      };
   }, []);

   function handleSessionUnauthorized(): void {
      setProfile(null);
      setStatus("signed_out");
      setSessionEpoch((currentEpoch) => currentEpoch + 1);
   }

   async function startSession(identifier: string): Promise<boolean> {
      const normalizedIdentifier = identifier.trim();
      if (!normalizedIdentifier || isStarting) return false;

      setIsStarting(true);
      setStartError(null);
      try {
         const nextProfile = await createAccessSession(normalizedIdentifier);
         setProfile(nextProfile);
         setStatus("ready");
         setStartupError(null);
         setSessionEpoch((currentEpoch) => currentEpoch + 1);
         return true;
      } catch (error) {
         setStartError(
            errorMessage(error, "The Steam profile could not be loaded.")
         );
         return false;
      } finally {
         setIsStarting(false);
      }
   }

   async function refreshSessionProfile(): Promise<boolean> {
      if (profile === null || isRefreshing) return false;

      setIsRefreshing(true);
      setRefreshError(null);
      try {
         const refreshedProfile = await refreshCurrentSessionProfile();
         setProfile(refreshedProfile);
         return true;
      } catch (error) {
         if (error instanceof ApiError && error.status === 401) {
            handleSessionUnauthorized();
         } else {
            setRefreshError(
               errorMessage(error, "The Steam library could not be refreshed.")
            );
         }
         return false;
      } finally {
         setIsRefreshing(false);
      }
   }

   async function endSession(): Promise<boolean> {
      if (profile === null || isEnding) return false;

      setIsEnding(true);
      setEndError(null);
      try {
         await deleteAccessSession();
         setProfile(null);
         setStatus("signed_out");
         setSessionEpoch((currentEpoch) => currentEpoch + 1);
         return true;
      } catch (error) {
         if (error instanceof ApiError && error.status === 401) {
            handleSessionUnauthorized();
            return true;
         }
         setEndError(errorMessage(error, "The session could not be ended."));
         return false;
      } finally {
         setIsEnding(false);
      }
   }

   return {
      endError,
      endSession,
      handleSessionUnauthorized,
      isEnding,
      isRefreshing,
      isStarting,
      profile,
      refreshError,
      refreshSessionProfile,
      sessionEpoch,
      startError,
      startSession,
      startupError,
      status,
   };
}
