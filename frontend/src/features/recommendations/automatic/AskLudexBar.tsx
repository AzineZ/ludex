import { useId, type FormEvent } from "react";

import type { PreferenceConstraints } from "../../../api";
import {
   describeNothingToSearch,
   describeScope,
   describeSearchedGames,
   isNarrowed,
} from "./askLudexScope";
import type { AskLudex } from "./useAskLudex";
import { MAX_ASK_LUDEX_PROMPT_CHARACTERS } from "./useAskLudex";

type AskLudexBarProps = {
   askLudex: AskLudex;
   constraints: PreferenceConstraints;
   onSearchAll: () => void;
   suggestedCount: number;
   includeSuggested: boolean;
   onToggleIncludeSuggested: () => void;
   onAsk: () => void;
   onChooseGenre: (genreId: number) => void;
};

/** One prompt for Gemini, with genre or narrowing steps only when needed. */
function AskLudexBar({
   askLudex,
   constraints,
   onSearchAll,
   suggestedCount,
   includeSuggested,
   onToggleIncludeSuggested,
   onAsk,
   onChooseGenre,
}: AskLudexBarProps) {
   const inputId = useId();
   const noteId = useId();
   const trimmed = askLudex.prompt.trim();
   const canAsk =
      trimmed.length > 0
      && trimmed.length <= MAX_ASK_LUDEX_PROMPT_CHARACTERS
      && !askLudex.isAsking;
   const games = (count: number) => (count === 1 ? "game" : "games");

   function handleSubmit(event: FormEvent<HTMLFormElement>): void {
      event.preventDefault();
      if (canAsk) {
         onAsk();
      }
   }

   return (
      <form
         className="ask-ludex"
         aria-busy={askLudex.isAsking}
         onSubmit={handleSubmit}
      >
         <label htmlFor={inputId}>Ask Ludex</label>
         <div className="ask-ludex__field">
            <input
               id={inputId}
               type="text"
               value={askLudex.prompt}
               maxLength={MAX_ASK_LUDEX_PROMPT_CHARACTERS}
               placeholder="Tell Ludex what you’re in the mood for…"
               aria-describedby={noteId}
               onChange={(event) => askLudex.setPrompt(event.target.value)}
            />
            <button
               className="app__primary-button"
               type="submit"
               disabled={!canAsk}
            >
               {askLudex.isAsking ? "Asking…" : "Ask"}
            </button>
         </div>
         <p className="ask-ludex__note ask-ludex__scope" id={noteId}>
            <strong>{describeScope(constraints)}</strong> Set by the filters
            below. Gemini sees only these games’ titles and facts, never your
            Steam ID or name.
         </p>
         {suggestedCount > 0 && (
            <p className="ask-ludex__note ask-ludex__suggested" role="status">
               <span>
                  {includeSuggested
                     ? `Including ${suggestedCount} ${games(suggestedCount)} already suggested below.`
                     : `Skipping ${suggestedCount} ${games(suggestedCount)} already suggested below.`}
               </span>
               <button
                  className="ask-ludex__link"
                  type="button"
                  aria-pressed={includeSuggested}
                  onClick={onToggleIncludeSuggested}
               >
                  {includeSuggested ? "Skip them" : "Include them"}
               </button>
            </p>
         )}

         {askLudex.step === "genre" && (
            <fieldset className="ask-ludex__step">
               <legend>{askLudex.message ?? "Pick a genre to focus on."}</legend>
               <div className="ask-ludex__choices">
                  {askLudex.genres.map((genre) => (
                     <button
                        key={genre.igdb_id}
                        className="recommendation-choice-pill"
                        type="button"
                        aria-label={`${genre.name}, ${genre.eligible_count} ${games(genre.eligible_count)}`}
                        disabled={askLudex.isAsking}
                        onClick={() => onChooseGenre(genre.igdb_id)}
                     >
                        <span>{genre.name}</span>
                        <span>{genre.eligible_count}</span>
                     </button>
                  ))}
               </div>
            </fieldset>
         )}

         {askLudex.step === "refine" && (
            <fieldset className="ask-ludex__step">
               <legend>
                  {askLudex.message
                     ?? "Still too many games. Pick a theme or game mode."}
               </legend>
               <div className="ask-ludex__choices">
                  {[...askLudex.themes, ...askLudex.gameModes].map((option, index) => {
                     const isTheme = index < askLudex.themes.length;
                     const selected = isTheme
                        ? askLudex.themeIds.includes(option.igdb_id)
                        : askLudex.gameModeIds.includes(option.igdb_id);
                     return (
                        <button
                           key={`${isTheme ? "theme" : "mode"}-${option.igdb_id}`}
                           className="recommendation-choice-pill"
                           type="button"
                           aria-pressed={selected}
                           onClick={() =>
                              isTheme
                                 ? askLudex.toggleTheme(option.igdb_id)
                                 : askLudex.toggleGameMode(option.igdb_id)
                           }
                        >
                           <span>{option.name}</span>
                           <span>{option.eligible_count}</span>
                        </button>
                     );
                  })}
               </div>
               <button
                  className="app__secondary-button"
                  type="submit"
                  disabled={!canAsk}
               >
                  Ask again
               </button>
            </fieldset>
         )}

         {askLudex.genreId !== null && askLudex.step === "prompt" && (
            <p className="ask-ludex__note">
               Focused on one genre.{" "}
               <button
                  className="ask-ludex__link"
                  type="button"
                  onClick={askLudex.clearGenre}
               >
                  Use the whole library
               </button>
            </p>
         )}

         {askLudex.miss !== null && !askLudex.isAsking && (
            <div className="ask-ludex__miss" role="status">
               <p>
                  {askLudex.miss.kind === "empty"
                     ? describeNothingToSearch(askLudex.miss.constraints)
                     : `Ludex looked at ${describeSearchedGames(askLudex.miss.eligibleCount, askLudex.miss.constraints)} and none felt like a fit for “${askLudex.miss.prompt}”.`}
               </p>
               {askLudex.miss.reason !== null && (
                  <p className="ask-ludex__miss-reason">{askLudex.miss.reason}</p>
               )}
               {isNarrowed(askLudex.miss.constraints) && (
                  <button
                     className="app__secondary-button"
                     type="button"
                     onClick={onSearchAll}
                  >
                     Search all my games
                  </button>
               )}
            </div>
         )}

         <p className="ask-ludex__status" role="status" aria-atomic="true">
            {askLudex.isAsking
               ? "Asking Ludex…"
               : askLudex.step === "prompt"
                  ? askLudex.message ?? ""
                  : ""}
         </p>
         {askLudex.error !== null && (
            <p className="ask-ludex__error" role="alert">
               {askLudex.error}
            </p>
         )}
      </form>
   );
}

export default AskLudexBar;
