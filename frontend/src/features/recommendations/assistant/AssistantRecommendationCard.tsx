import { useId } from "react";

import type { AssistantRecommendationItemResponse } from "../../../api";
import { ResultCardCover, ResultCardFacts } from "../results/ResultCardParts";
import { showAnotherLabel } from "../results/resultCardFormat";
import { useFocusOnRequest } from "../results/useFocusOnRequest";
import ScrollFadeFrame from "./ScrollFadeFrame";

type AssistantRecommendationCardProps = {
   item: AssistantRecommendationItemResponse;
   isAccepted?: boolean;
   remainingAlternatives?: number;
   focusRequestId?: number;
   onChoose?: () => void;
   onShowAnother?: () => void;
};

function AssistantRecommendationCard({
   item,
   isAccepted = false,
   remainingAlternatives,
   focusRequestId,
   onChoose,
   onShowAnother,
}: AssistantRecommendationCardProps) {
   const headingId = useId();
   const cardRef = useFocusOnRequest<HTMLElement>(focusRequestId);

   return (
      <article
         ref={cardRef}
         className="recommendation-result-card assistant-result-card"
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
               <div className="assistant-result-card__explanation">
                  <section className="recommendation-result-card__reason">
                     <h4>Summary</h4>
                     <ScrollFadeFrame
                        className="assistant-result-card__scroll-region"
                        role="region"
                        ariaLabel={`${item.title} summary`}
                        tabIndex={0}
                        updateKey={item.summary}
                     >
                        <p>{item.summary}</p>
                     </ScrollFadeFrame>
                  </section>
                  <section className="recommendation-result-card__reason">
                     <h4>Reasoning</h4>
                     <ScrollFadeFrame
                        className="assistant-result-card__scroll-region"
                        role="region"
                        ariaLabel={`${item.title} reasoning`}
                        tabIndex={0}
                        updateKey={item.reasoning}
                     >
                        <p>{item.reasoning}</p>
                     </ScrollFadeFrame>
                  </section>
               </div>
            </div>
         </div>

         {(onChoose !== undefined || onShowAnother !== undefined) && (
            <div className="recommendation-result-card__actions assistant-result-card__actions">
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
                     {showAnotherLabel(remainingAlternatives)}
                  </button>
               )}
            </div>
         )}

         <details className="recommendation-result-card__details">
            <summary>Game details</summary>
            <div className="recommendation-result-card__details-content">
               <ResultCardFacts
                  profilePlaytimeMinutes={item.profile_playtime_minutes}
                  normalCompletionSeconds={item.normal_completion_seconds}
               />
            </div>
         </details>
      </article>
   );
}

export default AssistantRecommendationCard;
