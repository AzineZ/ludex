import { useRef, useState } from "react";

import {
   getAssistantFilterOptions,
   getAssistantGenres,
   getAssistantRecommendations,
   type AssistantOptionResponse,
   type AssistantRecommendationItemResponse,
   type PreferenceConstraints,
} from "../../../api";
import {
   createReplacementQueue,
   replaceVisibleItem,
} from "../results/replacementQueue";

export const MAX_ASK_LUDEX_ROWS = 3;
export const MAX_ASK_LUDEX_PROMPT_CHARACTERS = 500;
const MAX_REJECTED = 30;
const MAX_EXCLUDED = 60;

export type AskLudexRow = {
   key: string;
   prompt: string;
   visible: readonly AssistantRecommendationItemResponse[];
   waiting: readonly AssistantRecommendationItemResponse[];
};

export type AskLudexStep = "prompt" | "genre" | "refine";

type AskLudexState = {
   isAsking: boolean;
   step: AskLudexStep;
   message: string | null;
   error: string | null;
   rows: AskLudexRow[];
   genres: readonly AssistantOptionResponse[];
   genreId: number | null;
   themes: readonly AssistantOptionResponse[];
   gameModes: readonly AssistantOptionResponse[];
   themeIds: number[];
   gameModeIds: number[];
   rejectedSteamAppIds: number[];
   focusRowKey: string | null;
};

const INITIAL_STATE: AskLudexState = {
   isAsking: false,
   step: "prompt",
   message: null,
   error: null,
   rows: [],
   genres: [],
   genreId: null,
   themes: [],
   gameModes: [],
   themeIds: [],
   gameModeIds: [],
   rejectedSteamAppIds: [],
   focusRowKey: null,
};

function errorMessage(error: unknown, fallback: string): string {
   return error instanceof Error && error.message ? error.message : fallback;
}

function toggle(values: readonly number[], value: number): number[] {
   return values.includes(value)
      ? values.filter((item) => item !== value)
      : [...values, value];
}

/**
 * Asks Gemini about the visitor's library from one prompt.
 *
 * The whole library is considered first; the server answers `needs_genre`
 * only when more than 2,000 games are eligible, and `needs_refinement` when a
 * genre still leaves more than 2,000. Each ranked answer becomes a row; the
 * newest three are kept.
 */
export function useAskLudex() {
   const [prompt, setPrompt] = useState("");
   const [state, setState] = useState<AskLudexState>(INITIAL_STATE);
   const generationRef = useRef(0);
   const rowCounterRef = useRef(0);

   function ask(
      constraints: PreferenceConstraints,
      excludedSteamAppIds: readonly number[],
      overrides: Partial<
         Pick<AskLudexState, "genreId" | "themeIds" | "gameModeIds">
      > = {},
   ): void {
      // The prompt stays in the box until an answer arrives, so the genre and
      // narrowing steps reuse it.
      const text = prompt.trim();
      if (
         text.length === 0
         || text.length > MAX_ASK_LUDEX_PROMPT_CHARACTERS
         || state.isAsking
      ) {
         return;
      }
      const genreId =
         overrides.genreId !== undefined ? overrides.genreId : state.genreId;
      const themeIds = overrides.themeIds ?? state.themeIds;
      const gameModeIds = overrides.gameModeIds ?? state.gameModeIds;
      generationRef.current += 1;
      const generation = generationRef.current;
      setState((current) => ({
         ...current,
         isAsking: true,
         message: null,
         error: null,
         genreId,
         themeIds,
         gameModeIds,
      }));

      void getAssistantRecommendations({
         prompt: text,
         ...(genreId === null ? {} : { selected_genre_id: genreId }),
         filters: {
            play_status: constraints.play_status,
            maximum_completion_minutes: constraints.maximum_completion_minutes,
            theme_ids: [...themeIds].sort((a, b) => a - b),
            game_mode_ids: [...gameModeIds].sort((a, b) => a - b),
         },
         rejected_steam_app_ids: state.rejectedSteamAppIds.slice(-MAX_REJECTED),
         excluded_steam_app_ids: [...excludedSteamAppIds].slice(0, MAX_EXCLUDED),
      }).then(
         async (response) => {
            if (generation !== generationRef.current) {
               return;
            }
            if (response.status === "ranked" && response.items.length > 0) {
               rowCounterRef.current += 1;
               const queue = createReplacementQueue(response.items);
               const row: AskLudexRow = {
                  key: `ask-${rowCounterRef.current}`,
                  prompt: text,
                  visible: queue.visible,
                  waiting: queue.waiting,
               };
               setPrompt("");
               setState((current) => ({
                  ...current,
                  isAsking: false,
                  step: "prompt",
                  rows: [row, ...current.rows].slice(0, MAX_ASK_LUDEX_ROWS),
                  focusRowKey: row.key,
               }));
               return;
            }
            if (response.status === "needs_genre") {
               const genres = await getAssistantGenres().catch(() => null);
               if (generation !== generationRef.current) {
                  return;
               }
               setState((current) => ({
                  ...current,
                  isAsking: false,
                  step: "genre",
                  genres: genres?.items ?? [],
                  message: response.message,
                  error: genres === null
                     ? "Unable to load genres from this library."
                     : null,
               }));
               return;
            }
            if (response.status === "needs_refinement" && genreId !== null) {
               const options = await getAssistantFilterOptions({
                  selected_genre_id: genreId,
                  play_status: constraints.play_status,
                  maximum_completion_minutes:
                     constraints.maximum_completion_minutes,
                  theme_ids: themeIds,
                  game_mode_ids: gameModeIds,
                  rejected_steam_app_ids: state.rejectedSteamAppIds,
                  excluded_steam_app_ids: [...excludedSteamAppIds],
               }).catch(() => null);
               if (generation !== generationRef.current) {
                  return;
               }
               setState((current) => ({
                  ...current,
                  isAsking: false,
                  step: "refine",
                  themes: options?.themes ?? [],
                  gameModes: options?.game_modes ?? [],
                  message: response.message,
               }));
               return;
            }
            setState((current) => ({
               ...current,
               isAsking: false,
               message:
                  response.message
                  ?? "Ludex couldn't find a match. Try different wording.",
            }));
         },
         (error: unknown) => {
            if (generation !== generationRef.current) {
               return;
            }
            setState((current) => ({
               ...current,
               isAsking: false,
               error: errorMessage(error, "Unable to ask Ludex right now."),
            }));
         },
      );
   }

   function clearGenre(): void {
      setState((current) => ({
         ...current,
         step: "prompt",
         genreId: null,
         themeIds: [],
         gameModeIds: [],
         message: null,
      }));
   }

   function toggleTheme(id: number): void {
      setState((current) => ({ ...current, themeIds: toggle(current.themeIds, id) }));
   }

   function toggleGameMode(id: number): void {
      setState((current) => ({
         ...current,
         gameModeIds: toggle(current.gameModeIds, id),
      }));
   }

   function showAnother(rowKey: string, steamAppId: number): void {
      setState((current) => {
         const index = current.rows.findIndex((row) => row.key === rowKey);
         if (index < 0) {
            return current;
         }
         const row = current.rows[index];
         const replacement = replaceVisibleItem(
            row.visible,
            row.waiting,
            steamAppId,
         );
         if (replacement === null) {
            return current;
         }
         const rows = [...current.rows];
         rows[index] = {
            ...row,
            visible: replacement.visible,
            waiting: replacement.waiting,
         };
         return {
            ...current,
            rows,
            focusRowKey: null,
            rejectedSteamAppIds: current.rejectedSteamAppIds.includes(steamAppId)
               ? current.rejectedSteamAppIds
               : [...current.rejectedSteamAppIds, steamAppId],
         };
      });
   }

   return {
      ...state,
      prompt,
      setPrompt,
      ask,
      clearGenre,
      toggleTheme,
      toggleGameMode,
      showAnother,
   };
}

export type AskLudex = ReturnType<typeof useAskLudex>;
