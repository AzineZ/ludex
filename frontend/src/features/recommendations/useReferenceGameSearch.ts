import { useEffect, useState } from "react";

import {
   searchReferenceGames,
   type OwnedGameSuggestionResponse,
} from "../../api";

export type ReferenceGameSearchStatus =
   | "idle"
   | "waiting"
   | "loading"
   | "ready"
   | "unavailable";

export type ReferenceGameSearchResult = {
   status: ReferenceGameSearchStatus;
   items: OwnedGameSuggestionResponse[];
   error: string | null;
};

type StoredSearchResult = {
   profileId: number;
   query: string;
   result: ReferenceGameSearchResult;
};

const SEARCH_DELAY_MILLISECONDS = 250;

function emptyResult(
   status: ReferenceGameSearchStatus
): ReferenceGameSearchResult {
   return {
      status,
      items: [],
      error: null,
   };
}

function errorMessage(error: unknown): string {
   if (error instanceof Error) {
      return error.message;
   }

   return "Unable to search owned games.";
}

export function useReferenceGameSearch(
   profileId: number | null,
   query: string
): ReferenceGameSearchResult {
   const [storedSearch, setStoredSearch] = useState<StoredSearchResult | null>(
      null
   );

   const hasSearch = profileId !== null && query.trim() !== "";

   useEffect(() => {
      if (profileId === null || query.trim() === "") {
         return;
      }

      let isCurrentRequest = true;
      const requestProfileId = profileId;
      const requestQuery = query;

      const timeoutId = window.setTimeout(() => {
         if (!isCurrentRequest) {
            return;
         }

         setStoredSearch({
            profileId: requestProfileId,
            query: requestQuery,
            result: emptyResult("loading"),
         });

         searchReferenceGames(requestQuery)
            .then((response) => {
               if (!isCurrentRequest) {
                  return;
               }

               setStoredSearch({
                  profileId: requestProfileId,
                  query: requestQuery,
                  result: {
                     status: "ready",
                     items: response.items,
                     error: null,
                  },
               });
            })
            .catch((error: unknown) => {
               if (!isCurrentRequest) {
                  return;
               }

               setStoredSearch({
                  profileId: requestProfileId,
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
   }, [profileId, query]);

   if (!hasSearch) {
      return emptyResult("idle");
   }

   if (
      storedSearch === null ||
      storedSearch.profileId !== profileId ||
      storedSearch.query !== query
   ) {
      return emptyResult("waiting");
   }

   return storedSearch.result;
}
