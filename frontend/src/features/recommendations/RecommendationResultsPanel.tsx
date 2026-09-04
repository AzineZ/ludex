import { useId } from "react";

import type { FinalRecommendationResponse } from "../../api";
import RecommendationResultCard from "./RecommendationResultCard";
import { splitRecommendationItems } from "./recommendationResults";
import type { RecommendationSessionState } from "./recommendationSession";
import type { RecommendationRequestStatus } from "./useRecommendationRequest";


type RecommendationResultsPanelProps = {
   status: RecommendationRequestStatus;
   response: FinalRecommendationResponse | null;
   error: string | null;
   session?: RecommendationSessionState | null;
   onShowAnother?: (steamAppId: number) => void;
   onPlayThis?: (steamAppId: number) => void;
   onStartOver?: () => void;
   focusRequest?: {
      steamAppId: number;
      requestId: number;
   } | null;
};

const UNEXPECTED_ERROR_MESSAGE =
   "Something went wrong while loading recommendations.";

function resultCountMessage(response: FinalRecommendationResponse): string {
   if (response.outcome === "complete") {
      return `${response.returned_count} recommendations found. Showing the top 3.`;
   }
   if (response.returned_count === 1) {
      return "1 recommendation found.";
   }
   return `${response.returned_count} recommendations found.`;
}

function RecommendationResultsPanel({
   status,
   response,
   error,
   session = null,
   onShowAnother,
   onPlayThis,
   onStartOver,
   focusRequest = null,
}: RecommendationResultsPanelProps) {
   const headingId = useId();

   if (status === "idle") {
      return null;
   }

   if (status === "loading") {
      return (
         <p
            className="recommendation-results__state"
            role="status"
            aria-atomic="true"
         >
            Finding recommendations in your cached library…
         </p>
      );
   }

   if (status === "error" || response === null) {
      return (
         <section
            className="recommendation-results__state recommendation-results__error"
            role="alert"
            aria-labelledby={headingId}
         >
            <h3 id={headingId}>Recommendations unavailable</h3>
            <p>{error ?? UNEXPECTED_ERROR_MESSAGE}</p>
            <p>
               Your preference choices are still here. Try again when you’re
               ready.
            </p>
         </section>
      );
   }

   if (response.outcome === "empty") {
      return (
         <section
            className="recommendation-results recommendation-results__state"
            aria-labelledby={headingId}
            aria-live="polite"
         >
            <div role="status" aria-atomic="true">
               <h3 id={headingId}>No recommendations found.</h3>
               <p>
                  No owned games match these preferences. Try changing your
                  reference games, selected facets, or constraints.
               </p>
               {session !== null && onStartOver !== undefined && (
                  <button
                     className="app__secondary-button"
                     type="button"
                     onClick={onStartOver}
                  >
                     Start over
                  </button>
               )}
            </div>
         </section>
      );
   }

   const acceptedSession = session?.phase === "accepted" ? session : null;
   const activeSession = session?.phase === "active" ? session : null;
   const queuedSession =
      session?.phase === "active"
      || session?.phase === "editing"
      || session?.phase === "refining"
         ? session
         : null;
   const fallbackItems = splitRecommendationItems(response.items).visibleItems;
   const visibleItems = acceptedSession !== null
      ? [acceptedSession.acceptedItem]
      : queuedSession?.visibleItems ?? fallbackItems;
   const queueExhausted =
      activeSession !== null
      && activeSession.visibleItems.length > 0
      && activeSession.waitingItems.length === 0;
   const countMessage = resultCountMessage(response);

   return (
      <section
         className="recommendation-results"
         aria-labelledby={headingId}
         aria-live="polite"
      >
         <header className="recommendation-results__header">
            <h3 id={headingId}>
               {acceptedSession === null
                  ? "Your recommendations"
                  : "Your choice"}
            </h3>
            <p role="status" aria-atomic="true">
               {acceptedSession !== null ? (
                  `You chose ${acceptedSession.acceptedItem.title}.`
               ) : session?.phase === "refining" ? (
                  "Refining recommendations while keeping your current queue."
               ) : (
                  <>
                     <span>{countMessage}</span>
                     {queueExhausted && (
                        <>
                           {" You’ve seen every recommendation in this bounded "}
                           queue. Choose a game, refine your preferences, or
                           start over.
                        </>
                     )}
                  </>
               )}
            </p>
            {session !== null && onStartOver !== undefined && (
               <button
                  className="app__secondary-button recommendation-results__start-over"
                  type="button"
                  onClick={onStartOver}
               >
                  Start over
               </button>
            )}
         </header>

         <div className="recommendation-results__cards">
            {visibleItems.map((item) => (
               <RecommendationResultCard
                  key={item.steam_app_id}
                  item={item}
                  onPlayThis={
                     activeSession !== null && onPlayThis !== undefined
                        ? () => onPlayThis(item.steam_app_id)
                        : undefined
                  }
                  onShowAnother={
                     activeSession !== null && onShowAnother !== undefined
                        ? () => onShowAnother(item.steam_app_id)
                        : undefined
                  }
                  showAnotherDisabled={queueExhausted}
                  focusRequestId={
                     focusRequest?.steamAppId === item.steam_app_id
                        ? focusRequest.requestId
                        : undefined
                  }
               />
            ))}
         </div>
      </section>
   );
}

export default RecommendationResultsPanel;
