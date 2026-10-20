import { useEffect, useRef, useState } from "react";

import {
   getAutomaticRecommendations,
   getMoreLikeThisRecommendations,
   type PreferenceConstraints,
   type RecommendationPreference,
} from "../../../api";
import {
   MAX_REJECTED_GAMES,
   addMoreLikeRow,
   createAutomaticRow,
   shownSteamAppIds,
   showAnotherInRow,
   type AutomaticRow,
} from "./automaticRows";

export const DEFAULT_AUTOMATIC_CONSTRAINTS: PreferenceConstraints = {
   maximum_completion_minutes: null,
   play_status: "unplayed",
};
export const PREPARING_RETRY_DELAY_MS = 3_000;
export const MAX_PREPARING_RETRIES = 10;

export type AutomaticRecommendationStatus =
   | "loading"
   | "preparing"
   | "ready"
   | "unavailable"
   | "error";

type AutomaticRecommendationState = {
   status: AutomaticRecommendationStatus;
   rows: AutomaticRow[];
   moreLikeRows: AutomaticRow[];
   suggestedPreference: RecommendationPreference | null;
   rejectedSteamAppIds: number[];
   isRefreshing: boolean;
   error: string | null;
   pendingMoreLikeSteamAppId: number | null;
   announcement: string | null;
   focusRowKey: string | null;
};

export type AutomaticRecommendationsResult = AutomaticRecommendationState & {
   constraints: PreferenceConstraints;
   canShowAnother: boolean;
   changeConstraints: (constraints: PreferenceConstraints) => void;
   retry: () => void;
   showAnother: (rowKey: string, steamAppId: number) => void;
   moreLikeThis: (item: { steam_app_id: number; title: string }) => void;
};

const INITIAL_STATE: AutomaticRecommendationState = {
   status: "loading",
   rows: [],
   moreLikeRows: [],
   suggestedPreference: null,
   rejectedSteamAppIds: [],
   isRefreshing: false,
   error: null,
   pendingMoreLikeSteamAppId: null,
   announcement: null,
   focusRowKey: null,
};

function requestErrorMessage(error: unknown, fallback: string): string {
   return error instanceof Error && error.message !== ""
      ? error.message
      : fallback;
}

/**
 * Loads one row per top played game, waits briefly while those games are
 * still being enriched, and keeps rows, toggles, and "More like this" rows
 * browser-local for the current access session.
 */
export function useAutomaticRecommendations(
   onUnavailable: () => void
): AutomaticRecommendationsResult {
   const [state, setState] =
      useState<AutomaticRecommendationState>(INITIAL_STATE);
   const [constraints, setConstraints] = useState<PreferenceConstraints>(
      DEFAULT_AUTOMATIC_CONSTRAINTS
   );
   const generationRef = useRef(0);
   const moreLikeGenerationRef = useRef(0);
   const moreLikeCounterRef = useRef(0);
   const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
   const onUnavailableRef = useRef(onUnavailable);

   useEffect(() => {
      onUnavailableRef.current = onUnavailable;
   }, [onUnavailable]);

   function clearRetryTimer(): void {
      if (retryTimerRef.current !== null) {
         clearTimeout(retryTimerRef.current);
         retryTimerRef.current = null;
      }
   }

   function fetchRows(
      requestConstraints: PreferenceConstraints,
      rejectedSteamAppIds: readonly number[],
      attempt: number
   ): void {
      clearRetryTimer();
      generationRef.current += 1;
      moreLikeGenerationRef.current += 1;
      const generation = generationRef.current;

      getAutomaticRecommendations({
         constraints: requestConstraints,
         rejected_steam_app_ids: [...rejectedSteamAppIds],
         wait_for_pending: attempt <= MAX_PREPARING_RETRIES,
      })
         .then((response) => {
            if (generation !== generationRef.current) {
               return;
            }
            if (response.status === "preparing") {
               setState((current) => ({ ...current, status: "preparing" }));
               retryTimerRef.current = setTimeout(() => {
                  fetchRows(requestConstraints, rejectedSteamAppIds, attempt + 1);
               }, PREPARING_RETRY_DELAY_MS);
               return;
            }
            if (response.status === "unavailable") {
               setState((current) => ({
                  ...current,
                  status: "unavailable",
                  rows: [],
                  moreLikeRows: [],
                  suggestedPreference: null,
                  isRefreshing: false,
               }));
               onUnavailableRef.current();
               return;
            }
            setState((current) => ({
               ...current,
               status: "ready",
               rows: response.rows.map((row) =>
                  createAutomaticRow(
                     row,
                     "played",
                     `played-${row.source_game.steam_app_id}`
                  )
               ),
               moreLikeRows: [],
               suggestedPreference: response.suggested_preference,
               isRefreshing: false,
               error: null,
               pendingMoreLikeSteamAppId: null,
               announcement: null,
            }));
         })
         .catch((error: unknown) => {
            if (generation !== generationRef.current) {
               return;
            }
            setState((current) => ({
               ...current,
               status: current.rows.length > 0 ? current.status : "error",
               isRefreshing: false,
               error: requestErrorMessage(
                  error,
                  "Unable to load recommendations from your library."
               ),
            }));
         });
   }

   useEffect(() => {
      fetchRows(DEFAULT_AUTOMATIC_CONSTRAINTS, [], 0);
      return () => {
         clearRetryTimer();
         generationRef.current += 1;
         moreLikeGenerationRef.current += 1;
      };
      // The first load runs once; later loads are started by handlers.
      // eslint-disable-next-line react-hooks/exhaustive-deps
   }, []);

   function changeConstraints(nextConstraints: PreferenceConstraints): void {
      setConstraints(nextConstraints);
      setState((current) => ({
         ...current,
         isRefreshing: true,
         error: null,
         moreLikeRows: [],
         pendingMoreLikeSteamAppId: null,
         announcement: null,
      }));
      fetchRows(nextConstraints, state.rejectedSteamAppIds, 0);
   }

   function retry(): void {
      setState((current) => ({
         ...current,
         status: current.rows.length > 0 ? current.status : "loading",
         isRefreshing: current.rows.length > 0,
         error: null,
      }));
      fetchRows(constraints, state.rejectedSteamAppIds, 0);
   }

   const canShowAnother =
      !state.isRefreshing
      && state.rejectedSteamAppIds.length < MAX_REJECTED_GAMES;

   function showAnother(rowKey: string, steamAppId: number): void {
      if (!canShowAnother) {
         return;
      }
      const allRows = [...state.moreLikeRows, ...state.rows];
      const result = showAnotherInRow(allRows, rowKey, steamAppId);
      if (result === null) {
         return;
      }
      setState((current) => ({
         ...current,
         moreLikeRows: result.rows.filter((row) => row.kind === "more-like"),
         rows: result.rows.filter((row) => row.kind === "played"),
         rejectedSteamAppIds: current.rejectedSteamAppIds.includes(steamAppId)
            ? current.rejectedSteamAppIds
            : [...current.rejectedSteamAppIds, steamAppId],
         announcement: null,
      }));
   }

   function moreLikeThis(item: { steam_app_id: number; title: string }): void {
      if (state.isRefreshing || state.pendingMoreLikeSteamAppId !== null) {
         return;
      }
      moreLikeGenerationRef.current += 1;
      const generation = moreLikeGenerationRef.current;
      const excluded = shownSteamAppIds(
         [...state.moreLikeRows, ...state.rows],
         state.rejectedSteamAppIds
      );
      setState((current) => ({
         ...current,
         pendingMoreLikeSteamAppId: item.steam_app_id,
         error: null,
         announcement: `Finding more games like ${item.title}…`,
      }));

      getMoreLikeThisRecommendations({
         steam_app_id: item.steam_app_id,
         constraints,
         excluded_steam_app_ids: excluded,
      })
         .then((response) => {
            if (generation !== moreLikeGenerationRef.current) {
               return;
            }
            if (response.recommendations.items.length === 0) {
               setState((current) => ({
                  ...current,
                  pendingMoreLikeSteamAppId: null,
                  announcement:
                     `No other games like ${item.title} match these filters.`,
               }));
               return;
            }
            moreLikeCounterRef.current += 1;
            const row = createAutomaticRow(
               response,
               "more-like",
               `more-${item.steam_app_id}-${moreLikeCounterRef.current}`
            );
            setState((current) => ({
               ...current,
               moreLikeRows: addMoreLikeRow(current.moreLikeRows, row),
               pendingMoreLikeSteamAppId: null,
               focusRowKey: row.key,
               announcement: `Added more games like ${item.title}.`,
            }));
         })
         .catch((error: unknown) => {
            if (generation !== moreLikeGenerationRef.current) {
               return;
            }
            setState((current) => ({
               ...current,
               pendingMoreLikeSteamAppId: null,
               announcement: null,
               error: requestErrorMessage(
                  error,
                  `Unable to find more games like ${item.title}.`
               ),
            }));
         });
   }

   return {
      ...state,
      constraints,
      canShowAnother,
      changeConstraints,
      retry,
      showAnother,
      moreLikeThis,
   };
}
