import { useEffect, useId, useRef, useState } from "react";

import type { AssistantRecommendationItemResponse } from "../../../api";
import {
   focusRequestIdFor,
   nextFocusRequest,
   type FocusRequest,
} from "../results/focusRequest";
import {
   createReplacementQueue,
   replaceVisibleItem,
} from "../results/replacementQueue";
import AssistantRecommendationCard from "./AssistantRecommendationCard";

type AssistantResultsProps = {
   items: readonly AssistantRecommendationItemResponse[];
   eligibleCount: number;
   onStartOver: () => void;
   onReject: (steamAppId: number) => void;
};

type ResultQueue = {
   visible: readonly AssistantRecommendationItemResponse[];
   waiting: readonly AssistantRecommendationItemResponse[];
   accepted: AssistantRecommendationItemResponse | null;
};

function AssistantResults({
   items,
   eligibleCount,
   onStartOver,
   onReject,
}: AssistantResultsProps) {
   const headingId = useId();
   const resultsRef = useRef<HTMLElement>(null);
   const [queue, setQueue] = useState<ResultQueue>(() => ({
      ...createReplacementQueue(items),
      accepted: null,
   }));
   const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(
      null
   );

   const visible = queue.accepted === null ? queue.visible : [queue.accepted];

   useEffect(() => {
      const results = resultsRef.current;
      if (results === null) {
         return;
      }

      const animationFrame = requestAnimationFrame(() => {
         results.focus({ preventScroll: true });
         if (typeof results.scrollIntoView === "function") {
            const prefersReducedMotion =
               typeof window.matchMedia === "function" &&
               window.matchMedia("(prefers-reduced-motion: reduce)").matches;
            results.scrollIntoView({
               behavior: prefersReducedMotion ? "auto" : "smooth",
               block: "start",
            });
         }
      });
      return () => cancelAnimationFrame(animationFrame);
   }, []);

   return (
      <section
         ref={resultsRef}
         className="recommendation-results assistant-results"
         aria-labelledby={headingId}
         aria-live="polite"
         tabIndex={-1}
      >
         <header className="recommendation-results__header">
            <h3 id={headingId}>
               {queue.accepted === null
                  ? "Your AI recommendations"
                  : "Your choice"}
            </h3>
            <p>
               {queue.accepted === null
                  ? `Gemini compared all ${eligibleCount} eligible games in this pool.`
                  : `You chose ${queue.accepted.title}. Have fun!`}
            </p>
            <button
               className="app__secondary-button recommendation-results__start-over"
               type="button"
               onClick={onStartOver}
            >
               Start over
            </button>
         </header>

         <div
            className={
               queue.accepted === null
                  ? "recommendation-results__cards"
                  : "recommendation-results__cards recommendation-results__cards--accepted"
            }
         >
            {visible.map((item) => (
               <AssistantRecommendationCard
                  key={item.steam_app_id}
                  item={item}
                  isAccepted={queue.accepted !== null}
                  remainingAlternatives={queue.waiting.length}
                  focusRequestId={focusRequestIdFor(
                     focusRequest,
                     item.steam_app_id
                  )}
                  onChoose={
                     queue.accepted === null
                        ? () => {
                             setQueue((current) => ({
                                ...current,
                                accepted: item,
                             }));
                             setFocusRequest(
                                nextFocusRequest(item.steam_app_id)
                             );
                          }
                        : undefined
                  }
                  onShowAnother={
                     queue.accepted === null
                        ? () => {
                             const next = replaceVisibleItem(
                                queue.visible,
                                queue.waiting,
                                item.steam_app_id
                             );
                             if (next === null) {
                                return;
                             }
                             onReject(item.steam_app_id);
                             setQueue({
                                visible: next.visible,
                                waiting: next.waiting,
                                accepted: null,
                             });
                             setFocusRequest(
                                nextFocusRequest(
                                   next.replacement.steam_app_id
                                )
                             );
                          }
                        : undefined
                  }
               />
            ))}
         </div>
      </section>
   );
}

export default AssistantResults;
