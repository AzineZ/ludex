import { useEffect, useMemo, useRef, useState } from "react";

import {
   getAssistantFilterOptions,
   getAssistantGenres,
   getAssistantRecommendations,
   type AssistantFilterOptionsResponse,
   type AssistantGenreOptionsResponse,
   type AssistantRecommendationResponse,
   type PreferenceConstraints,
} from "../../../api";

type LoadState = "loading" | "ready" | "error";
type SubmissionState = "idle" | "loading" | "ready" | "error";

const DEFAULT_CONSTRAINTS: PreferenceConstraints = {
   play_status: "either",
   maximum_completion_minutes: null,
};

const EMPTY_FILTER_OPTIONS: AssistantFilterOptionsResponse = {
   eligible_count: 0,
   candidate_limit: 400,
   themes: [],
   game_modes: [],
};

function errorMessage(error: unknown, fallback: string): string {
   return error instanceof Error && error.message ? error.message : fallback;
}

function toggleId(values: readonly number[], value: number): number[] {
   return values.includes(value)
      ? values.filter((candidate) => candidate !== value)
      : [...values, value];
}

function retainAvailableIds(
   values: number[],
   availableIds: Set<number>
): number[] {
   const retained = values.filter((id) => availableIds.has(id));
   return retained.length === values.length ? values : retained;
}

function useAssistantWorkflow(sessionEpoch: number | null) {
   const [genreState, setGenreState] = useState<LoadState>("loading");
   const [genres, setGenres] = useState<AssistantGenreOptionsResponse>({
      items: [],
   });
   const [genreError, setGenreError] = useState<string | null>(null);
   const [selectedGenreId, setSelectedGenreId] = useState<number | null>(null);
   const [constraints, setConstraints] = useState<PreferenceConstraints>({
      ...DEFAULT_CONSTRAINTS,
   });
   const [filterState, setFilterState] = useState<LoadState>("ready");
   const [filterOptions, setFilterOptions] = useState(EMPTY_FILTER_OPTIONS);
   const [filterError, setFilterError] = useState<string | null>(null);
   const [selectedThemeIds, setSelectedThemeIds] = useState<number[]>([]);
   const [selectedGameModeIds, setSelectedGameModeIds] = useState<number[]>([]);
   const [prompt, setPrompt] = useState("");
   const [submissionState, setSubmissionState] =
      useState<SubmissionState>("idle");
   const [response, setResponse] =
      useState<AssistantRecommendationResponse | null>(null);
   const [submissionError, setSubmissionError] = useState<string | null>(null);
   const [rejectedSteamAppIds, setRejectedSteamAppIds] = useState<number[]>([]);
   const submissionGeneration = useRef(0);
   const submissionInFlight = useRef(false);
   const filterContextKey = useMemo(
      () =>
         JSON.stringify({
            sessionEpoch,
            selectedGenreId,
            playStatus: constraints.play_status,
            maximumCompletionMinutes: constraints.maximum_completion_minutes,
            selectedThemeIds,
            selectedGameModeIds,
            rejectedSteamAppIds,
         }),
      [
         constraints.maximum_completion_minutes,
         constraints.play_status,
         rejectedSteamAppIds,
         selectedGameModeIds,
         selectedGenreId,
         selectedThemeIds,
         sessionEpoch,
      ]
   );
   const selectedGenre =
      genres.items.find((genre) => genre.igdb_id === selectedGenreId) ?? null;

   useEffect(() => {
      let current = true;
      void getAssistantGenres().then(
         (result) => {
            if (current) {
               setGenres(result);
               setGenreState("ready");
            }
         },
         (error: unknown) => {
            if (current) {
               setGenreError(
                  errorMessage(
                     error,
                     "Unable to load genres from this library."
                  )
               );
               setGenreState("error");
            }
         }
      );
      return () => {
         current = false;
      };
   }, [sessionEpoch]);

   useEffect(() => {
      if (selectedGenreId === null) {
         return;
      }

      let current = true;
      void getAssistantFilterOptions({
         selected_genre_id: selectedGenreId,
         play_status: constraints.play_status,
         maximum_completion_minutes: constraints.maximum_completion_minutes,
         theme_ids: [...selectedThemeIds],
         game_mode_ids: [...selectedGameModeIds],
         rejected_steam_app_ids: [...rejectedSteamAppIds],
      }).then(
         (result) => {
            if (!current) {
               return;
            }
            const themeIds = new Set(result.themes.map((item) => item.igdb_id));
            const gameModeIds = new Set(
               result.game_modes.map((item) => item.igdb_id)
            );
            setSelectedThemeIds((values) =>
               retainAvailableIds(values, themeIds)
            );
            setSelectedGameModeIds((values) =>
               retainAvailableIds(values, gameModeIds)
            );
            setFilterOptions(result);
            setFilterState("ready");
         },
         (error: unknown) => {
            if (current) {
               setFilterError(
                  errorMessage(
                     error,
                     "Unable to load factual filters for this genre."
                  )
               );
               setFilterState("error");
            }
         }
      );
      return () => {
         current = false;
      };
   }, [
      constraints,
      filterContextKey,
      rejectedSteamAppIds,
      selectedGameModeIds,
      selectedGenreId,
      selectedThemeIds,
   ]);

   function markFiltersLoading(): void {
      setFilterState("loading");
      setFilterError(null);
      setResponse(null);
      setSubmissionState("idle");
   }

   function selectGenre(genreId: number): void {
      setSelectedGenreId(genreId);
      setFilterOptions(EMPTY_FILTER_OPTIONS);
      setSelectedThemeIds([]);
      setSelectedGameModeIds([]);
      markFiltersLoading();
   }

   function changeConstraints(value: PreferenceConstraints): void {
      setConstraints(value);
      markFiltersLoading();
   }

   function toggleTheme(id: number): void {
      setSelectedThemeIds((values) => toggleId(values, id));
      markFiltersLoading();
   }

   function toggleGameMode(id: number): void {
      setSelectedGameModeIds((values) => toggleId(values, id));
      markFiltersLoading();
   }

   function changePrompt(value: string): void {
      setPrompt(value);
      setResponse((current) =>
         current?.status === "needs_refinement" ? current : null
      );
      setSubmissionState("idle");
   }

   function submit(): void {
      const normalizedPrompt = prompt.trim();
      if (
         selectedGenreId === null ||
         normalizedPrompt.length === 0 ||
         normalizedPrompt.length > 500 ||
         submissionInFlight.current
      ) {
         return;
      }
      const generation = submissionGeneration.current + 1;
      submissionGeneration.current = generation;
      submissionInFlight.current = true;
      setSubmissionState("loading");
      setSubmissionError(null);
      setResponse(null);
      void getAssistantRecommendations({
         prompt: normalizedPrompt,
         selected_genre_id: selectedGenreId,
         filters: {
            play_status: constraints.play_status,
            maximum_completion_minutes: constraints.maximum_completion_minutes,
            theme_ids: [...selectedThemeIds].sort(
               (first, second) => first - second
            ),
            game_mode_ids: [...selectedGameModeIds].sort(
               (first, second) => first - second
            ),
         },
         rejected_steam_app_ids: [...rejectedSteamAppIds],
      }).then(
         (result) => {
            if (submissionGeneration.current === generation) {
               submissionInFlight.current = false;
               setResponse(result);
               setSubmissionState("ready");
            }
         },
         (error: unknown) => {
            if (submissionGeneration.current === generation) {
               submissionInFlight.current = false;
               setSubmissionError(
                  errorMessage(error, "Unable to ask Ludex right now.")
               );
               setSubmissionState("error");
            }
         }
      );
   }

   function resetResults(): void {
      submissionGeneration.current += 1;
      submissionInFlight.current = false;
      setResponse(null);
      setSubmissionState("idle");
      setSubmissionError(null);
      setRejectedSteamAppIds([]);
      setPrompt("");
   }

   function reject(steamAppId: number): void {
      setFilterState("loading");
      setFilterError(null);
      setRejectedSteamAppIds((ids) =>
         ids.includes(steamAppId) ? ids : [...ids, steamAppId]
      );
   }

   const promptIsValid =
      prompt.trim().length > 0 && prompt.trim().length <= 500;
   const canSubmit =
      selectedGenreId !== null &&
      promptIsValid &&
      filterState !== "loading" &&
      submissionState !== "loading";

   return {
      canSubmit,
      changeConstraints,
      changePrompt,
      constraints,
      filterError,
      filterOptions,
      filterState,
      genreError,
      genres,
      genreState,
      prompt,
      reject,
      resetResults,
      response,
      selectGenre,
      selectedGameModeIds,
      selectedGenre,
      selectedGenreId,
      selectedThemeIds,
      submissionError,
      submissionState,
      submit,
      toggleGameMode,
      toggleTheme,
   };
}

export type AssistantWorkflow = ReturnType<typeof useAssistantWorkflow>;
export default useAssistantWorkflow;
