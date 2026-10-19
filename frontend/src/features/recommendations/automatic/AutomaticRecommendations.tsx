import { useEffect, useId, useRef } from "react";

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
   focusOnMount: boolean;
   collapsed: boolean;
   allRows: readonly AutomaticRow[];
   automatic: AutomaticRecommendationsResult;
};

function prefersReducedMotion(): boolean {
   return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
      ?? false;
}

function AutomaticRowSection({
   row,
   focusOnMount,
   collapsed,
   allRows,
   automatic,
}: AutomaticRowSectionProps) {
   const headingId = useId();
   const headingRef = useRef<HTMLHeadingElement>(null);

   // A new "More like" row appears above the card that asked for it, so
   // bring it into view and move keyboard focus to its heading.
   useEffect(() => {
      const heading = headingRef.current;
      if (!focusOnMount || heading === null) {
         return;
      }
      heading.focus({ preventScroll: true });
      heading.scrollIntoView?.({
         behavior: prefersReducedMotion() ? "auto" : "smooth",
         block: "start",
      });
      // Only the first render of a newly added row should move the page.
      // eslint-disable-next-line react-hooks/exhaustive-deps
   }, []);
   const alternatives = remainingAlternatives(allRows, row);
   const moreLikeBusy =
      automatic.isRefreshing || automatic.pendingMoreLikeSteamAppId !== null;

   const heading = rowHeading(row);
   const cards = (
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
   );

   // Older "More like" rows shrink to one line so repeated use stays short.
   if (collapsed) {
      return (
         <section
            className="automatic-recommendations__row automatic-recommendations__row--collapsed"
            aria-label={heading}
            data-row-kind={row.kind}
            data-row-title={heading}
         >
            <details className="automatic-recommendations__collapsed">
               <summary>
                  <span className="automatic-recommendations__collapsed-title">
                     {heading}
                  </span>
                  <span className="automatic-recommendations__collapsed-count">
                     {row.visible.length === 1
                        ? "1 game"
                        : `${row.visible.length} games`}
                  </span>
               </summary>
               {cards}
            </details>
         </section>
      );
   }

   return (
      <section
         className="automatic-recommendations__row"
         aria-labelledby={headingId}
         data-row-kind={row.kind}
         data-row-title={heading}
      >
         <h4
            id={headingId}
            ref={headingRef}
            tabIndex={row.kind === "more-like" ? -1 : undefined}
         >
            {heading}
         </h4>
         {cards}
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
   const newestMoreLikeKey = automatic.moreLikeRows[0]?.key ?? null;

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
                  Based on games you’ve played or finished recently.
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
                           focusOnMount={row.key === automatic.focusRowKey}
                           collapsed={
                              row.kind === "more-like"
                              && row.key !== newestMoreLikeKey
                           }
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
