import { useEffect, useId, useRef } from "react";

import type { FinalRecommendationItemResponse } from "../../../api";
import RecommendationEvidenceDisclosure from "./RecommendationEvidenceDisclosure";


type RecommendationResultCardProps = {
   item: FinalRecommendationItemResponse;
   onPlayThis?: () => void;
   onShowAnother?: () => void;
   showAnotherDisabled?: boolean;
   remainingAlternatives?: number;
   focusRequestId?: number;
   isAccepted?: boolean;
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

function getRecommendationCoverUrl(coverUrl: string): string {
   return coverUrl.replace(
      /^(https:\/\/images\.igdb\.com\/igdb\/image\/upload\/)t_cover_big(?=\/)/,
      "$1t_cover_big_2x"
   );
}

function RecommendationResultCard({
   item,
   onPlayThis,
   onShowAnother,
   showAnotherDisabled = false,
   remainingAlternatives,
   focusRequestId,
   isAccepted = false,
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
   const alternativeCountText = remainingAlternatives === undefined
      ? null
      : remainingAlternatives === 0
         ? "No alternatives remaining"
      : remainingAlternatives === 1
         ? "1 alternative remaining"
         : `${remainingAlternatives} alternatives remaining`;
   const showAnotherText = remainingAlternatives === 0
      ? "No alternatives left"
      : remainingAlternatives === undefined
         ? "Show another"
         : `Show another · ${remainingAlternatives} left`;

   useEffect(() => {
      if (focusRequestId !== undefined) {
         cardRef.current?.focus();
      }
   }, [focusRequestId]);

   return (
      <article
         ref={cardRef}
         className="recommendation-result-card"
         data-selection-state={isAccepted ? "accepted" : undefined}
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
                  src={getRecommendationCoverUrl(item.cover_url)}
                  alt={`${item.title} cover`}
               />
            )}
         </div>

         <div className="recommendation-result-card__stage">
            <p className="recommendation-result-card__rank">
               {isAccepted ? "Your pick" : `Recommendation ${item.rank}`}
            </p>

            <div className="recommendation-result-card__content">
               <header>
                  <h3 id={headingId}>{item.title}</h3>
               </header>

               <section className="recommendation-result-card__reason">
                  <h4>Why it matches</h4>
                  <p>{item.match_summary.text}</p>
               </section>
            </div>

            {(onPlayThis !== undefined || onShowAnother !== undefined) && (
               <div className="recommendation-result-card__actions">
                  {onPlayThis !== undefined && (
                     <button
                        className="app__primary-button"
                        type="button"
                        aria-label={`Choose ${item.title}`}
                        onClick={onPlayThis}
                     >
                        Choose this game
                     </button>
                  )}
                  {onShowAnother !== undefined && (
                     <button
                        className="app__secondary-button"
                        type="button"
                        aria-label={
                           `Show another instead of ${item.title}`
                           + (alternativeCountText === null
                              ? ""
                              : `. ${alternativeCountText}.`)
                        }
                        onClick={onShowAnother}
                        disabled={showAnotherDisabled}
                     >
                        {showAnotherText}
                     </button>
                  )}
               </div>
            )}
         </div>

         <details className="recommendation-result-card__details">
            <summary>Game details</summary>
            <div className="recommendation-result-card__details-content">
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
            </div>
         </details>
      </article>
   );
}

export default RecommendationResultCard;
