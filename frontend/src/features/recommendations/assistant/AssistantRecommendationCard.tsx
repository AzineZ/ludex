import { useEffect, useId, useRef } from "react";

import type { AssistantRecommendationItemResponse } from "../../../api";

type AssistantRecommendationCardProps = {
   item: AssistantRecommendationItemResponse;
   isAccepted?: boolean;
   remainingAlternatives?: number;
   focusRequestId?: number;
   onChoose?: () => void;
   onShowAnother?: () => void;
};

function formatMinutes(minutes: number): string {
   const hours = Math.floor(minutes / 60);
   const remainder = minutes % 60;
   if (hours === 0) {
      return `${remainder} min`;
   }
   return remainder === 0 ? `${hours} hr` : `${hours} hr ${remainder} min`;
}

function largeCoverUrl(coverUrl: string): string {
   return coverUrl.replace(
      /^(https:\/\/images\.igdb\.com\/igdb\/image\/upload\/)t_cover_big(?=\/)/,
      "$1t_cover_big_2x"
   );
}

function AssistantRecommendationCard({
   item,
   isAccepted = false,
   remainingAlternatives,
   focusRequestId,
   onChoose,
   onShowAnother,
}: AssistantRecommendationCardProps) {
   const headingId = useId();
   const cardRef = useRef<HTMLElement>(null);
   const playtime = item.profile_playtime_minutes === 0
      ? "Not played yet"
      : `${formatMinutes(item.profile_playtime_minutes)} played`;
   const completion = item.normal_completion_seconds === null
      ? "Unavailable"
      : formatMinutes(Math.round(item.normal_completion_seconds / 60));
   const alternativesText = remainingAlternatives === 0
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
         className="recommendation-result-card assistant-result-card"
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
                  src={largeCoverUrl(item.cover_url)}
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
                  <h4>AI-generated reason</h4>
                  <p>{item.reason}</p>
               </section>
            </div>

            {(onChoose !== undefined || onShowAnother !== undefined) && (
               <div className="recommendation-result-card__actions">
                  {onChoose !== undefined && (
                     <button
                        className="app__primary-button"
                        type="button"
                        aria-label={`Choose ${item.title}`}
                        onClick={onChoose}
                     >
                        Choose this game
                     </button>
                  )}
                  {onShowAnother !== undefined && (
                     <button
                        className="app__secondary-button"
                        type="button"
                        aria-label={`Show another instead of ${item.title}`}
                        onClick={onShowAnother}
                        disabled={remainingAlternatives === 0}
                     >
                        {alternativesText}
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
                     <dd>{completion}</dd>
                  </div>
               </dl>
            </div>
         </details>
      </article>
   );
}

export default AssistantRecommendationCard;
