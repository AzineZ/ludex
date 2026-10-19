import { useId } from "react";

import type { RecommendationPreference } from "../../../api";
import RecommendationResultCard from "../results/RecommendationResultCard";
import {
   remainingAlternatives,
   rowHeading,
   type AutomaticRow,
} from "./automaticRows";
import QuickToggles from "./QuickToggles";
import {
   useAutomaticRecommendations,
   type AutomaticRecommendationsResult,
} from "./useAutomaticRecommendations";
import "./automatic.css";

type AutomaticRecommendationsProps = {
   onCustomize: (preference: RecommendationPreference | null) => void;
   onUnavailable: () => void;
};

type AutomaticRowSectionProps = {
   row: AutomaticRow;
   allRows: readonly AutomaticRow[];
   automatic: AutomaticRecommendationsResult;
};

function AutomaticRowSection({
   row,
   allRows,
   automatic,
}: AutomaticRowSectionProps) {
   const headingId = useId();
   const alternatives = remainingAlternatives(allRows, row);
   const moreLikeBusy =
      automatic.isRefreshing || automatic.pendingMoreLikeSteamAppId !== null;

   return (
      <section
         className="automatic-recommendations__row"
         aria-labelledby={headingId}
         data-row-kind={row.kind}
      >
         <h4 id={headingId}>{rowHeading(row)}</h4>
         <div className="automatic-recommendations__cards">
            {row.visible.map((item) => (
               <RecommendationResultCard
                  key={item.steam_app_id}
                  item={item}
                  onShowAnother={() =>
                     automatic.showAnother(row.key, item.steam_app_id)
                  }
                  showAnotherDisabled={
                     alternatives === 0 || !automatic.canShowAnother
                  }
                  remainingAlternatives={alternatives}
                  onMoreLikeThis={() => automatic.moreLikeThis(item)}
                  moreLikeThisDisabled={moreLikeBusy}
               />
            ))}
         </div>
      </section>
   );
}

/** Shows input-free Guided rows built from the visitor's most-played games. */
function AutomaticRecommendations({
   onCustomize,
   onUnavailable,
}: AutomaticRecommendationsProps) {
   const headingId = useId();
   const automatic = useAutomaticRecommendations(onUnavailable);
   const allRows = [...automatic.moreLikeRows, ...automatic.rows];
   const visibleRows = allRows.filter((row) => row.visible.length > 0);

   return (
      <section
         className="automatic-recommendations"
         aria-labelledby={headingId}
         aria-busy={
            automatic.status === "loading"
            || automatic.status === "preparing"
            || automatic.isRefreshing
         }
      >
         <header className="automatic-recommendations__header">
            <div>
               <h3 id={headingId}>Picked from your library</h3>
               <p>
                  Based on the games you’ve played most, with recent play
                  counting extra.
               </p>
            </div>
            <button
               className="app__secondary-button automatic-recommendations__customize"
               type="button"
               onClick={() => onCustomize(automatic.suggestedPreference)}
            >
               Customize
            </button>
         </header>

         {automatic.status === "loading" && (
            <p className="recommendation-results__state" role="status">
               Finding recommendations in your library…
            </p>
         )}

         {automatic.status === "preparing" && (
            <p className="recommendation-results__state" role="status">
               Preparing your recommendations… Ludex is still reading game
               details for your most-played games.
            </p>
         )}

         {automatic.status === "error" && (
            <div
               className="recommendation-results__state recommendation-results__error"
               role="alert"
            >
               <p>{automatic.error}</p>
               <button
                  className="app__secondary-button"
                  type="button"
                  onClick={automatic.retry}
               >
                  Try again
               </button>
            </div>
         )}

         {automatic.status === "ready" && (
            <>
               <QuickToggles
                  value={automatic.constraints}
                  disabled={automatic.isRefreshing}
                  onChange={automatic.changeConstraints}
               />

               <p
                  className="automatic-recommendations__status"
                  role="status"
                  aria-atomic="true"
               >
                  {automatic.isRefreshing
                     ? "Updating recommendations…"
                     : automatic.announcement ?? ""}
               </p>

               {automatic.error !== null && (
                  <div
                     className="recommendation-results__state recommendation-results__error"
                     role="alert"
                  >
                     <p>{automatic.error}</p>
                     <button
                        className="app__secondary-button"
                        type="button"
                        onClick={automatic.retry}
                     >
                        Try again
                     </button>
                  </div>
               )}

               {visibleRows.length === 0 ? (
                  <div className="recommendation-results__state">
                     <p>
                        No games in your library match these filters. Try a
                        longer length or a different play status, or use
                        Customize to choose your own reference games.
                     </p>
                  </div>
               ) : (
                  <div className="automatic-recommendations__rows">
                     {visibleRows.map((row) => (
                        <AutomaticRowSection
                           key={row.key}
                           row={row}
                           allRows={allRows}
                           automatic={automatic}
                        />
                     ))}
                  </div>
               )}
            </>
         )}
      </section>
   );
}

export default AutomaticRecommendations;
