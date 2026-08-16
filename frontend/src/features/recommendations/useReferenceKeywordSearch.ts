import { useEffect, useState } from "react";

import {
   searchReferenceKeywords,
   type FacetOptionResponse,
} from "../../api";

export type ReferenceKeywordSearchStatus =
   | "idle"
   | "waiting"
   | "loading"
   | "ready"
   | "unavailable";

export type ReferenceKeywordSearchResult = {
   status: ReferenceKeywordSearchStatus;
   items: FacetOptionResponse[];
   error: string | null;
};

type StoredKeywordSearch = {
   profileId: number;
   steamAppId: number;
   query: string;
   result: ReferenceKeywordSearchResult;
};

const SEARCH_DELAY_MILLISECONDS = 250;

function emptyResult(
   status: ReferenceKeywordSearchStatus
): ReferenceKeywordSearchResult {
   return { status, items: [], error: null };
}

function errorMessage(error: unknown): string {
   return error instanceof Error
      ? error.message
      : "Unable to search reference keywords.";
}

export function useReferenceKeywordSearch(
   profileId: number | null,
   steamAppId: number | null,
   query: string
): ReferenceKeywordSearchResult {
   const [storedSearch, setStoredSearch] =
      useState<StoredKeywordSearch | null>(null);
   const hasSearch =
      profileId !== null && steamAppId !== null && query.trim() !== "";

   useEffect(() => {
      if (profileId === null || steamAppId === null || query.trim() === "") {
         return;
      }

      let isCurrentRequest = true;
      const requestProfileId = profileId;
      const requestSteamAppId = steamAppId;
      const requestQuery = query;
      const timeoutId = window.setTimeout(() => {
         if (!isCurrentRequest) {
            return;
         }

         setStoredSearch({
            profileId: requestProfileId,
            steamAppId: requestSteamAppId,
            query: requestQuery,
            result: emptyResult("loading"),
         });

         searchReferenceKeywords(
            requestProfileId,
            requestSteamAppId,
            requestQuery
         )
            .then((response) => {
               if (!isCurrentRequest) {
                  return;
               }
               setStoredSearch({
                  profileId: requestProfileId,
                  steamAppId: requestSteamAppId,
                  query: requestQuery,
                  result: { status: "ready", items: response.items, error: null },
               });
            })
            .catch((error: unknown) => {
               if (!isCurrentRequest) {
                  return;
               }
               setStoredSearch({
                  profileId: requestProfileId,
                  steamAppId: requestSteamAppId,
                  query: requestQuery,
                  result: {
                     status: "unavailable",
                     items: [],
                     error: errorMessage(error),
                  },
               });
            });
      }, SEARCH_DELAY_MILLISECONDS);

      return () => {
         isCurrentRequest = false;
         window.clearTimeout(timeoutId);
      };
   }, [profileId, steamAppId, query]);

   if (!hasSearch) {
      return emptyResult("idle");
   }
   if (
      storedSearch === null ||
      storedSearch.profileId !== profileId ||
      storedSearch.steamAppId !== steamAppId ||
      storedSearch.query !== query
   ) {
      return emptyResult("waiting");
   }
   return storedSearch.result;
}
