import { useId } from "react";

import type { FinalRecommendationItemResponse } from "../../../api";
import RecommendationEvidenceDisclosure from "./RecommendationEvidenceDisclosure";
import { ResultCardCover, ResultCardFacts } from "./ResultCardParts";
import { showAnotherLabel } from "./resultCardFormat";
import { useFocusOnRequest } from "./useFocusOnRequest";

type RecommendationResultCardProps = {
   item: FinalRecommendationItemResponse;
   onPlayThis?: () => void;
   onShowAnother?: () => void;
   showAnotherDisabled?: boolean;
   remainingAlternatives?: number;
   focusRequestId?: number;
   isAccepted?: boolean;
};

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
   const cardRef = useFocusOnRequest<HTMLElement>(focusRequestId);
   const alternativeCountText = remainingAlternatives === undefined
      ? null
      : remainingAlternatives === 0
         ? "No alternatives remaining"
      : remainingAlternatives === 1
         ? "1 alternative remaining"
         : `${remainingAlternatives} alternatives remaining`;

   return (
      <article
         ref={cardRef}
         className="recommendation-result-card"
         data-selection-state={isAccepted ? "accepted" : undefined}
         aria-labelledby={headingId}
         tabIndex={focusRequestId === undefined ? undefined : -1}
      >
         <ResultCardCover title={item.title} coverUrl={item.cover_url} />

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
                        {showAnotherLabel(remainingAlternatives)}
                     </button>
                  )}
               </div>
            )}
         </div>

         <details className="recommendation-result-card__details">
            <summary>Game details</summary>
            <div className="recommendation-result-card__details-content">
               <ResultCardFacts
                  profilePlaytimeMinutes={item.profile_playtime_minutes}
                  normalCompletionSeconds={item.normal_completion_seconds}
               />

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
