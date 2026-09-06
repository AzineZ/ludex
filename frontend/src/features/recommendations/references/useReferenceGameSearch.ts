import { useEffect, useState } from "react";

import {
   searchReferenceGames,
   type OwnedGameSuggestionResponse,
} from "../../../api";

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
   sessionEpoch: number;
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
   sessionEpoch: number | null,
   query: string
): ReferenceGameSearchResult {
   const [storedSearch, setStoredSearch] = useState<StoredSearchResult | null>(
      null
   );

   const hasSearch = sessionEpoch !== null && query.trim() !== "";

   useEffect(() => {
      if (sessionEpoch === null || query.trim() === "") {
         return;
      }

      let isCurrentRequest = true;
      const requestSessionEpoch = sessionEpoch;
      const requestQuery = query;

      const timeoutId = window.setTimeout(() => {
         if (!isCurrentRequest) {
            return;
         }

         setStoredSearch({
            sessionEpoch: requestSessionEpoch,
            query: requestQuery,
            result: emptyResult("loading"),
         });

         searchReferenceGames(requestQuery)
            .then((response) => {
               if (!isCurrentRequest) {
                  return;
               }

               setStoredSearch({
                  sessionEpoch: requestSessionEpoch,
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
                  sessionEpoch: requestSessionEpoch,
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
   }, [sessionEpoch, query]);

   if (!hasSearch) {
      return emptyResult("idle");
   }

   if (
      storedSearch === null ||
      storedSearch.sessionEpoch !== sessionEpoch ||
      storedSearch.query !== query
   ) {
      return emptyResult("waiting");
   }

   return storedSearch.result;
}
