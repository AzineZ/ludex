import type { FinalRecommendationItemResponse } from "../../../api";
import { createReplacementQueue } from "./replacementQueue";

type RecommendationItemSplit = {
   visibleItems: FinalRecommendationItemResponse[];
   waitingItems: FinalRecommendationItemResponse[];
};

export function splitRecommendationItems(
   items: readonly FinalRecommendationItemResponse[]
): RecommendationItemSplit {
   const queue = createReplacementQueue(items);
   return { visibleItems: queue.visible, waitingItems: queue.waiting };
}
