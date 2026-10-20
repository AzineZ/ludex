import { useId } from "react";

import type { AssistantRecommendationItemResponse } from "../../../api";
import {
   CardHeading,
   CardTitle,
   ResultCardBackdrop,
   ResultCardCover,
   ResultCardFacts,
   ResultCardMeta,
   type CardHeadingLevel,
} from "../results/ResultCardParts";
import { showAnotherLabel } from "../results/resultCardFormat";
import { useFocusOnRequest } from "../results/useFocusOnRequest";
import ScrollFadeFrame from "./ScrollFadeFrame";

type AssistantRecommendationCardProps = {
   item: AssistantRecommendationItemResponse;
   headingLevel?: CardHeadingLevel;
   isAccepted?: boolean;
   remainingAlternatives?: number;
   focusRequestId?: number;
   onChoose?: () => void;
   onShowAnother?: () => void;
   onMoreLikeThis?: () => void;
   moreLikeThisDisabled?: boolean;
};

/** Shows one Ask Ludex result with its AI reasoning below the full cover. */
function AssistantRecommendationCard({
   item,
   headingLevel = 3,
   isAccepted = false,
   remainingAlternatives,
   focusRequestId,
   onChoose,
   onShowAnother,
   onMoreLikeThis,
   moreLikeThisDisabled = false,
}: AssistantRecommendationCardProps) {
   const headingId = useId();
   const cardRef = useFocusOnRequest<HTMLElement>(focusRequestId);
   const innerHeadingLevel = (headingLevel + 1) as CardHeadingLevel | 6;

   return (
      <article
         ref={cardRef}
         className="recommendation-result-card assistant-result-card"
         data-selection-state={isAccepted ? "accepted" : undefined}
         aria-labelledby={headingId}
         tabIndex={focusRequestId === undefined ? undefined : -1}
      >
         <ResultCardBackdrop coverUrl={item.cover_url} />
         <ResultCardCover title={item.title} coverUrl={item.cover_url} />

         <div className="recommendation-result-card__body">
            {isAccepted && (
               <p className="recommendation-result-card__badge">Your pick</p>
            )}
            <CardTitle level={headingLevel} id={headingId} title={item.title} />
            <ResultCardMeta
               ratings={item.ratings}
               normalCompletionSeconds={item.normal_completion_seconds}
               profilePlaytimeMinutes={item.profile_playtime_minutes}
            />
            <section className="recommendation-result-card__reason assistant-result-card__explanation">
               <CardHeading level={innerHeadingLevel}>Reasoning</CardHeading>
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

            {(
               onChoose !== undefined
               || onShowAnother !== undefined
               || onMoreLikeThis !== undefined
            ) && (
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
                        {showAnotherLabel(remainingAlternatives)}
                     </button>
                  )}
                  {onMoreLikeThis !== undefined && (
                     <button
                        className="app__secondary-button"
                        type="button"
                        aria-label={`More games like ${item.title}`}
                        onClick={onMoreLikeThis}
                        disabled={moreLikeThisDisabled}
                     >
                        More like this
                     </button>
                  )}
               </div>
            )}
         </div>

         <details className="recommendation-result-card__details">
            <summary>Game details</summary>
            <div className="recommendation-result-card__details-content">
               <section className="recommendation-result-card__reason">
                  <CardHeading level={innerHeadingLevel}>Summary</CardHeading>
                  <p>{item.summary}</p>
               </section>
               <ResultCardFacts
                  profilePlaytimeMinutes={item.profile_playtime_minutes}
                  normalCompletionSeconds={item.normal_completion_seconds}
                  ratings={item.ratings}
               />
            </div>
         </details>
      </article>
   );
}

export default AssistantRecommendationCard;
