import { useEffect, useMemo, useRef, useState } from "react";

import {
   getAssistantFilterOptions,
   getAssistantGenres,
   getAssistantRecommendations,
   type AssistantFilterOptionsResponse,
   type AssistantGenreOptionsResponse,
   type AssistantOptionResponse,
   type AssistantRecommendationResponse,
   type PreferenceConstraints,
} from "../../../api";
import RecommendationConstraints from "../preferences/RecommendationConstraints";
import AssistantResults from "./AssistantResults";

type AssistantWorkspaceProps = {
   sessionEpoch: number | null;
   onUseGuided: () => void;
};

type LoadState = "loading" | "ready" | "error";

const DEFAULT_CONSTRAINTS: PreferenceConstraints = {
   play_status: "either",
   maximum_completion_minutes: null,
};

const EMPTY_FILTER_OPTIONS: AssistantFilterOptionsResponse = {
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

function OptionButtons({
   label,
   options,
   selectedIds,
   onToggle,
}: {
   label: string;
   options: readonly AssistantOptionResponse[];
   selectedIds: readonly number[];
   onToggle: (id: number) => void;
}) {
   return (
      <fieldset className="assistant-filters__group" aria-label={label}>
         <legend>{label}</legend>
         {options.length === 0 ? (
            <p className="assistant-filters__empty">No options in this pool.</p>
         ) : (
            <div className="assistant-option-grid assistant-option-grid--compact">
               {options.map((option) => {
                  const isSelected = selectedIds.includes(option.igdb_id);
                  const selectionLimitReached = selectedIds.length >= 8;
                  return (
                     <button
                        key={option.igdb_id}
                        type="button"
                        aria-label={`${option.name}, ${option.eligible_count} eligible games`}
                        aria-pressed={isSelected}
                        disabled={!isSelected && selectionLimitReached}
                        onClick={() => onToggle(option.igdb_id)}
                     >
                        <span>{option.name}</span>
                        <span>{option.eligible_count}</span>
                     </button>
                  );
               })}
            </div>
         )}
      </fieldset>
   );
}

function AssistantWorkspaceSession({
   sessionEpoch,
   onUseGuided,
}: AssistantWorkspaceProps) {
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
   const [submissionState, setSubmissionState] = useState<
      "idle" | "loading" | "ready" | "error"
   >("idle");
   const [response, setResponse] = useState<AssistantRecommendationResponse | null>(null);
   const [submissionError, setSubmissionError] = useState<string | null>(null);
   const [rejectedSteamAppIds, setRejectedSteamAppIds] = useState<number[]>([]);
   const submissionGeneration = useRef(0);
   const submissionInFlight = useRef(false);
   const filterContextKey = useMemo(() => JSON.stringify({
      sessionEpoch,
      selectedGenreId,
      playStatus: constraints.play_status,
      maximumCompletionMinutes: constraints.maximum_completion_minutes,
      rejectedSteamAppIds,
   }), [
      constraints.maximum_completion_minutes,
      constraints.play_status,
      rejectedSteamAppIds,
      selectedGenreId,
      sessionEpoch,
   ]);
   const selectedGenre = genres.items.find(
      (genre) => genre.igdb_id === selectedGenreId
   ) ?? null;

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
               setGenreError(errorMessage(
                  error,
                  "Unable to load genres from this library."
               ));
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
            setSelectedThemeIds((values) => values.filter((id) => themeIds.has(id)));
            setSelectedGameModeIds((values) => (
               values.filter((id) => gameModeIds.has(id))
            ));
            setFilterOptions(result);
            setFilterState("ready");
         },
         (error: unknown) => {
            if (current) {
               setFilterError(errorMessage(
                  error,
                  "Unable to load factual filters for this genre."
               ));
               setFilterState("error");
            }
         }
      );
      return () => {
         current = false;
      };
   }, [filterContextKey, selectedGenreId, constraints, rejectedSteamAppIds]);

   function selectGenre(genreId: number): void {
      setSelectedGenreId(genreId);
      setFilterOptions(EMPTY_FILTER_OPTIONS);
      setFilterState("loading");
      setFilterError(null);
      setSelectedThemeIds([]);
      setSelectedGameModeIds([]);
      setResponse(null);
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
            theme_ids: [...selectedThemeIds].sort((first, second) => first - second),
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
               setSubmissionError(errorMessage(
                  error,
                  "Unable to ask Ludex right now."
               ));
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

   if (response?.status === "ranked" && response.items.length > 0) {
      return (
         <AssistantResults
            key={response.items.map((item) => item.steam_app_id).join("-")}
            items={response.items}
            eligibleCount={response.eligible_count}
            onStartOver={resetResults}
            onReject={(steamAppId) => {
               setFilterState("loading");
               setFilterError(null);
               setRejectedSteamAppIds((ids) => (
                  ids.includes(steamAppId) ? ids : [...ids, steamAppId]
               ));
            }}
         />
      );
   }

   const promptIsValid = prompt.trim().length > 0 && prompt.trim().length <= 500;
   const canSubmit = selectedGenreId !== null
      && promptIsValid
      && filterState !== "loading"
      && submissionState !== "loading";

   return (
      <section className="assistant-workspace" aria-labelledby="assistant-heading">
         <header className="assistant-workspace__heading">
            <p className="assistant-workspace__eyebrow">Optional Gemini assistant</p>
            <h3 id="assistant-heading">Ask Ludex</h3>
            <p>
               Pick a genre from your owned library, narrow the factual pool if
               needed, then describe what you feel like playing.
            </p>
            <p className="assistant-workspace__boundary">
               Gemini can rank only the eligible owned games Ludex sends it.
               Your Steam ID and profile name are not included.
            </p>
         </header>

         <div className="assistant-step" data-step="1">
            <header className="assistant-step__heading">
               <span aria-hidden="true">01</span>
               <div>
                  <h4>Choose a genre from your library</h4>
                  <p>Counts include only owned games with ready IGDB metadata.</p>
               </div>
            </header>

            {genreState === "loading" && <p role="status">Loading genres…</p>}
            {genreState === "error" && (
               <div className="assistant-state assistant-state--error" role="alert">
                  <p>{genreError}</p>
                  <button className="app__secondary-button" type="button" onClick={onUseGuided}>
                     Use guided recommendations
                  </button>
               </div>
            )}
            {genreState === "ready" && genres.items.length === 0 && (
               <div className="assistant-state">
                  <p>
                     No genre-ready games are available in this cached library.
                  </p>
                  <button className="app__secondary-button" type="button" onClick={onUseGuided}>
                     Use guided recommendations
                  </button>
               </div>
            )}
            {genres.items.length > 0 && (
               <div className="assistant-option-grid assistant-option-grid--genres">
                  {genres.items.map((genre) => (
                     <button
                        key={genre.igdb_id}
                        type="button"
                        aria-label={`${genre.name}, ${genre.eligible_count} eligible games`}
                        aria-pressed={selectedGenreId === genre.igdb_id}
                        onClick={() => selectGenre(genre.igdb_id)}
                     >
                        <span>{genre.name}</span>
                        <span>{genre.eligible_count}</span>
                     </button>
                  ))}
               </div>
            )}
         </div>

         {selectedGenre !== null && (
            <div className="assistant-step" data-step="2">
               <header className="assistant-step__heading">
                  <span aria-hidden="true">02</span>
                  <div>
                     <h4>Narrow {selectedGenre.name}</h4>
                     <p>
                        These are factual filters. Select multiple themes or modes
                        to match any selected option within that group.
                     </p>
                  </div>
               </header>

               <RecommendationConstraints
                  value={constraints}
                  onChange={(value) => {
                     setConstraints(value);
                     setFilterState("loading");
                     setFilterError(null);
                     setResponse(null);
                     setSubmissionState("idle");
                  }}
               />

               {filterState === "loading" && (
                  <p className="assistant-filters__status" role="status">
                     Updating factual filters…
                  </p>
               )}
               {filterState === "error" && (
                  <p className="assistant-filters__status" role="alert">
                     {filterError}
                  </p>
               )}
               {filterState === "ready" && (
                  <div className="assistant-filters">
                     <OptionButtons
                        label="Theme filters"
                        options={filterOptions.themes}
                        selectedIds={selectedThemeIds}
                        onToggle={(id) => {
                           setSelectedThemeIds((values) => toggleId(values, id));
                           setResponse(null);
                           setSubmissionState("idle");
                        }}
                     />
                     <OptionButtons
                        label="Game mode filters"
                        options={filterOptions.game_modes}
                        selectedIds={selectedGameModeIds}
                        onToggle={(id) => {
                           setSelectedGameModeIds((values) => toggleId(values, id));
                           setResponse(null);
                           setSubmissionState("idle");
                        }}
                     />
                  </div>
               )}
            </div>
         )}

         {selectedGenre !== null && (
            <div className="assistant-step" data-step="3">
               <header className="assistant-step__heading">
                  <span aria-hidden="true">03</span>
                  <div>
                     <h4>Describe the kind of game you want</h4>
                     <p>Your wording influences ranking, not hard eligibility.</p>
                  </div>
               </header>

               {response?.status === "needs_refinement" && (
                  <div className="assistant-state assistant-state--attention" role="status">
                     <h4>Narrow your {response.eligible_count}-game pool</h4>
                     <p>
                        The complete pool is over the {response.candidate_limit}-game
                        assistant limit. Add a factual filter above, then ask again.
                        No Gemini call was made.
                     </p>
                  </div>
               )}

               {(response?.status === "empty" || response?.status === "no_match") && (
                  <div className="assistant-state" role="status">
                     <h4>{response.status === "empty" ? "No eligible games" : "No confident match"}</h4>
                     <p>{response.message}</p>
                     <button className="app__secondary-button" type="button" onClick={onUseGuided}>
                        Use guided recommendations
                     </button>
                  </div>
               )}

               {response?.status === "unavailable" && (
                  <div className="assistant-state assistant-state--error" role="status">
                     <h4>AI recommendations unavailable</h4>
                     <p>{response.message}</p>
                     <button className="app__primary-button" type="button" onClick={onUseGuided}>
                        Use guided recommendations
                     </button>
                  </div>
               )}

               {submissionState === "error" && (
                  <div className="assistant-state assistant-state--error" role="alert">
                     <h4>Unable to ask Ludex</h4>
                     <p>{submissionError}</p>
                  </div>
               )}

               <label className="assistant-prompt" htmlFor="assistant-prompt">
                  <span>What are you in the mood to play?</span>
                  <textarea
                     id="assistant-prompt"
                     rows={5}
                     maxLength={500}
                     value={prompt}
                     aria-describedby="assistant-prompt-help assistant-data-use"
                     placeholder="For example: Something relaxing and easy to start after work."
                     onChange={(event) => {
                        setPrompt(event.target.value);
                        setResponse((current) => (
                           current?.status === "needs_refinement" ? current : null
                        ));
                        setSubmissionState("idle");
                     }}
                  />
               </label>
               <div className="assistant-prompt__meta" id="assistant-prompt-help">
                  <span>1–500 characters</span>
                  <span>{prompt.length} / 500</span>
               </div>
               <div className="assistant-data-use" id="assistant-data-use">
                  <strong>Before you send</strong>
                  <p>
                     On Google’s free Gemini tier, prompts and responses may be
                     used for product improvement and human review. Do not include
                     personal, confidential, or sensitive information.
                  </p>
               </div>
               <div className="assistant-submit-row">
                  <button
                     className="app__primary-button"
                     type="button"
                     onClick={submit}
                     disabled={!canSubmit}
                  >
                     {submissionState === "loading" ? "Asking Ludex…" : "Ask Ludex"}
                  </button>
                  <p>
                     One submission normally uses one Gemini request. Filters and
                     queue controls do not.
                  </p>
               </div>
            </div>
         )}
      </section>
   );
}

function AssistantWorkspace(props: AssistantWorkspaceProps) {
   return (
      <AssistantWorkspaceSession
         key={props.sessionEpoch ?? "no-session"}
         {...props}
      />
   );
}

export default AssistantWorkspace;
