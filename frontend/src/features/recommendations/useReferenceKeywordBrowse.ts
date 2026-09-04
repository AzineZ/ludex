import { useEffect, useState } from "react";

import {
   getReferenceKeywords,
   type FacetOptionResponse,
} from "../../api";

export type ReferenceKeywordBrowseStatus =
   | "idle"
   | "loading"
   | "ready"
   | "unavailable";

export type ReferenceKeywordBrowseResult = {
   status: ReferenceKeywordBrowseStatus;
   items: FacetOptionResponse[];
   truncated: boolean;
   error: string | null;
   retry: () => void;
};

type ReferenceKeywordBrowseState = Omit<
   ReferenceKeywordBrowseResult,
   "retry"
>;

type StoredKeywordBrowse = {
   sessionEpoch: number;
   steamAppId: number;
   result: ReferenceKeywordBrowseState;
};

function emptyResult(
   status: ReferenceKeywordBrowseStatus
): ReferenceKeywordBrowseState {
   return { status, items: [], truncated: false, error: null };
}

function errorMessage(error: unknown): string {
   return error instanceof Error
      ? error.message
      : "Unable to browse reference keywords.";
}

export function useReferenceKeywordBrowse(
   sessionEpoch: number | null,
   steamAppId: number | null
): ReferenceKeywordBrowseResult {
   const [storedBrowse, setStoredBrowse] =
      useState<StoredKeywordBrowse | null>(null);
   const [requestVersion, setRequestVersion] = useState(0);
   const hasReference = sessionEpoch !== null && steamAppId !== null;

   useEffect(() => {
      if (sessionEpoch === null || steamAppId === null) {
         return;
      }

      let isCurrentRequest = true;
      const requestSessionEpoch = sessionEpoch;
      const requestSteamAppId = steamAppId;

      getReferenceKeywords(requestSteamAppId)
         .then((response) => {
            if (!isCurrentRequest) {
               return;
            }
            setStoredBrowse({
               sessionEpoch: requestSessionEpoch,
               steamAppId: requestSteamAppId,
               result: {
                  status: "ready",
                  items: response.items,
                  truncated: response.truncated,
                  error: null,
               },
            });
         })
         .catch((error: unknown) => {
            if (!isCurrentRequest) {
               return;
            }
            setStoredBrowse({
               sessionEpoch: requestSessionEpoch,
               steamAppId: requestSteamAppId,
               result: {
                  ...emptyResult("unavailable"),
                  error: errorMessage(error),
               },
            });
         });

      return () => {
         isCurrentRequest = false;
      };
   }, [requestVersion, sessionEpoch, steamAppId]);

   function retry(): void {
      if (!hasReference) return;
      setStoredBrowse(null);
      setRequestVersion((currentVersion) => currentVersion + 1);
   }

   if (!hasReference) {
      return { ...emptyResult("idle"), retry };
   }
   if (
      storedBrowse === null ||
      storedBrowse.sessionEpoch !== sessionEpoch ||
      storedBrowse.steamAppId !== steamAppId
   ) {
      return { ...emptyResult("loading"), retry };
   }
   return { ...storedBrowse.result, retry };
}
