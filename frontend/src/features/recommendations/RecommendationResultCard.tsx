import { useEffect, useId, useRef } from "react";

import type { FinalRecommendationItemResponse } from "../../api";
import RecommendationEvidenceDisclosure from "./RecommendationEvidenceDisclosure";


type RecommendationResultCardProps = {
   item: FinalRecommendationItemResponse;
   onPlayThis?: () => void;
   onShowAnother?: () => void;
   showAnotherDisabled?: boolean;
   focusRequestId?: number;
};

function formatMinutes(minutes: number): string {
   const hours = Math.floor(minutes / 60);
   const remainingMinutes = minutes % 60;

   if (hours === 0) {
      return `${remainingMinutes} min`;
   }
   if (remainingMinutes === 0) {
      return `${hours} hr`;
   }
   return `${hours} hr ${remainingMinutes} min`;
}

function RecommendationResultCard({
   item,
   onPlayThis,
   onShowAnother,
   showAnotherDisabled = false,
   focusRequestId,
}: RecommendationResultCardProps) {
   const headingId = useId();
   const cardRef = useRef<HTMLElement>(null);
   const playtime =
      item.profile_playtime_minutes === 0
         ? "Not played yet"
         : `${formatMinutes(item.profile_playtime_minutes)} played`;
   const completionTime =
      item.normal_completion_seconds === null
         ? "Unavailable"
         : formatMinutes(Math.round(item.normal_completion_seconds / 60));

   useEffect(() => {
      if (focusRequestId !== undefined) {
         cardRef.current?.focus();
      }
   }, [focusRequestId]);

   return (
      <article
         ref={cardRef}
         className="recommendation-result-card"
         aria-labelledby={headingId}
         tabIndex={focusRequestId === undefined ? undefined : -1}
      >
         <div className="recommendation-result-card__cover-frame">
            {item.cover_url === null ? (
               <div
                  className="recommendation-result-card__cover-fallback"
                  role="img"
                  aria-label={`${item.title} cover unavailable`}
               >
                  Cover unavailable
               </div>
            ) : (
               <img
                  className="recommendation-result-card__cover"
                  src={item.cover_url}
                  alt={`${item.title} cover`}
               />
            )}
         </div>

         <div className="recommendation-result-card__content">
            <header>
               <p className="recommendation-result-card__rank">
                  Recommendation {item.rank}
               </p>
               <h3 id={headingId}>{item.title}</h3>
            </header>

            <dl className="recommendation-result-card__facts">
               <div>
                  <dt>Your library</dt>
                  <dd>{playtime}</dd>
               </div>
               <div>
                  <dt>Estimated completion</dt>
                  <dd>{completionTime}</dd>
               </div>
            </dl>

            <section className="recommendation-result-card__reason">
               <h4>Why it matches</h4>
               <p>{item.match_summary.text}</p>
            </section>

            {item.tradeoff !== null && (
               <aside className="recommendation-result-card__tradeoff">
                  <h4>Keep in mind</h4>
                  <p>{item.tradeoff.text}</p>
               </aside>
            )}

            <RecommendationEvidenceDisclosure
               evidence={item.factual_evidence}
               facetLabels={item.facet_labels}
            />

            {(onPlayThis !== undefined || onShowAnother !== undefined) && (
               <div className="recommendation-result-card__actions">
                  {onPlayThis !== undefined && (
                     <button
                        className="app__primary-button"
                        type="button"
                        onClick={onPlayThis}
                     >
                        Play this
                     </button>
                  )}
                  {onShowAnother !== undefined && (
                     <button
                        className="app__secondary-button"
                        type="button"
                        onClick={onShowAnother}
                        disabled={showAnotherDisabled}
                     >
                        Show another
                     </button>
                  )}
               </div>
            )}
         </div>
      </article>
   );
}

export default RecommendationResultCard;
