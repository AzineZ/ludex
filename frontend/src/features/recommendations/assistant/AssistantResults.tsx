import { useEffect, useId, useRef, useState } from "react";

import type { AssistantRecommendationItemResponse } from "../../../api";
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
      visible: items.slice(0, 3),
      waiting: items.slice(3),
      accepted: null,
   }));
   const [focusRequest, setFocusRequest] = useState<{
      steamAppId: number;
      requestId: number;
   } | null>(null);

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
                  focusRequestId={
                     focusRequest?.steamAppId === item.steam_app_id
                        ? focusRequest.requestId
                        : undefined
                  }
                  onChoose={
                     queue.accepted === null
                        ? () => {
                             setQueue((current) => ({
                                ...current,
                                accepted: item,
                             }));
                             setFocusRequest((current) => ({
                                steamAppId: item.steam_app_id,
                                requestId: (current?.requestId ?? 0) + 1,
                             }));
                          }
                        : undefined
                  }
                  onShowAnother={
                     queue.accepted === null
                        ? () => {
                             if (queue.waiting.length === 0) {
                                return;
                             }
                             const replacement = queue.waiting[0];
                             const nextVisible = [...queue.visible];
                             const index = nextVisible.findIndex(
                                (candidate) =>
                                   candidate.steam_app_id === item.steam_app_id
                             );
                             if (index < 0) {
                                return;
                             }
                             nextVisible[index] = replacement;
                             onReject(item.steam_app_id);
                             setQueue({
                                visible: nextVisible,
                                waiting: queue.waiting.slice(1),
                                accepted: null,
                             });
                             setFocusRequest((focus) => ({
                                steamAppId: replacement.steam_app_id,
                                requestId: (focus?.requestId ?? 0) + 1,
                             }));
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
