import { useId } from "react";

import type { FinalRecommendationResponse } from "../../api";
import RecommendationResultCard from "./RecommendationResultCard";
import { splitRecommendationItems } from "./recommendationResults";
import type { RecommendationRequestStatus } from "./useRecommendationRequest";


type RecommendationResultsPanelProps = {
   status: RecommendationRequestStatus;
   response: FinalRecommendationResponse | null;
   error: string | null;
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
}: RecommendationResultsPanelProps) {
   const headingId = useId();

   if (status === "idle") {
      return null;
   }

   if (status === "loading") {
      return (
         <p className="recommendation-results__state" role="status">
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

   const { visibleItems } = splitRecommendationItems(response.items);

   if (response.outcome === "empty") {
      return (
         <section
            className="recommendation-results recommendation-results__state"
            aria-labelledby={headingId}
            aria-live="polite"
         >
            <div role="status">
               <h3 id={headingId}>No recommendations found.</h3>
               <p>
                  No owned games match these preferences. Try changing your
                  reference games, selected facets, or constraints.
               </p>
            </div>
         </section>
      );
   }

   return (
      <section
         className="recommendation-results"
         aria-labelledby={headingId}
         aria-live="polite"
      >
         <header className="recommendation-results__header">
            <h3 id={headingId}>Your recommendations</h3>
            <p role="status">{resultCountMessage(response)}</p>
         </header>

         <div className="recommendation-results__cards">
            {visibleItems.map((item) => (
               <RecommendationResultCard
                  key={item.steam_app_id}
                  item={item}
               />
            ))}
         </div>
      </section>
   );
}

export default RecommendationResultsPanel;
