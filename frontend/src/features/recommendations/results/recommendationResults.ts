import type { FinalRecommendationItemResponse } from "../../../api";


const VISIBLE_RECOMMENDATION_COUNT = 3;

export type RecommendationItemSplit = {
   visibleItems: FinalRecommendationItemResponse[];
   waitingItems: FinalRecommendationItemResponse[];
};

export function splitRecommendationItems(
   items: readonly FinalRecommendationItemResponse[]
): RecommendationItemSplit {
   return {
      visibleItems: items.slice(0, VISIBLE_RECOMMENDATION_COUNT),
      waitingItems: items.slice(VISIBLE_RECOMMENDATION_COUNT),
   };
}
