import { useId } from "react";

import type { FinalRecommendationItemResponse } from "../../../api";
import RecommendationEvidenceDisclosure from "./RecommendationEvidenceDisclosure";
import {
   CardHeading,
   CardTitle,
   ResultCardCover,
   ResultCardFacts,
   ResultCardMeta,
   type CardHeadingLevel,
} from "./ResultCardParts";
import { describeShortMatch, showAnotherLabel } from "./resultCardFormat";
import { useFocusOnRequest } from "./useFocusOnRequest";

type RecommendationResultCardProps = {
   item: FinalRecommendationItemResponse;
   headingLevel?: CardHeadingLevel;
   onPlayThis?: () => void;
   onShowAnother?: () => void;
   showAnotherDisabled?: boolean;
   onMoreLikeThis?: () => void;
   moreLikeThisDisabled?: boolean;
   remainingAlternatives?: number;
   focusRequestId?: number;
   isAccepted?: boolean;
};

/** Shows one Guided result: full cover, then title, facts, and actions. */
function RecommendationResultCard({
   item,
   headingLevel = 3,
   onPlayThis,
   onShowAnother,
   showAnotherDisabled = false,
   onMoreLikeThis,
   moreLikeThisDisabled = false,
   remainingAlternatives,
   focusRequestId,
   isAccepted = false,
}: RecommendationResultCardProps) {
   const headingId = useId();
   const cardRef = useFocusOnRequest<HTMLElement>(focusRequestId);
   const innerHeadingLevel = (headingLevel + 1) as CardHeadingLevel | 6;
   const alternativeCountText = remainingAlternatives === undefined
      ? null
      : remainingAlternatives === 0
         ? "No alternatives remaining"
      : remainingAlternatives === 1
         ? "1 alternative remaining"
         : `${remainingAlternatives} alternatives remaining`;
   const hasActions = onPlayThis !== undefined
      || onShowAnother !== undefined
      || onMoreLikeThis !== undefined;

   return (
      <article
         ref={cardRef}
         className="recommendation-result-card"
         data-selection-state={isAccepted ? "accepted" : undefined}
         aria-labelledby={headingId}
         tabIndex={focusRequestId === undefined ? undefined : -1}
      >
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
            <p className="recommendation-result-card__match">
               {describeShortMatch(item.match_summary.reasons)}
            </p>

            {hasActions && (
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
                  <CardHeading level={innerHeadingLevel}>Why it matches</CardHeading>
                  <p>{item.match_summary.text}</p>
               </section>

               <ResultCardFacts
                  profilePlaytimeMinutes={item.profile_playtime_minutes}
                  normalCompletionSeconds={item.normal_completion_seconds}
                  ratings={item.ratings}
               />

               {item.tradeoff !== null && (
                  <aside className="recommendation-result-card__tradeoff">
                     <CardHeading level={innerHeadingLevel}>Keep in mind</CardHeading>
                     <p>{item.tradeoff.text}</p>
                  </aside>
               )}

               <RecommendationEvidenceDisclosure
                  evidence={item.factual_evidence}
                  facetLabels={item.facet_labels}
                  headingLevel={innerHeadingLevel}
               />
            </div>
         </details>
      </article>
   );
}

export default RecommendationResultCard;
