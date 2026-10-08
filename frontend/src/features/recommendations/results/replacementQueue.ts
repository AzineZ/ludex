export const VISIBLE_RESULT_COUNT = 3;

type QueueItem = { steam_app_id: number };

export type ReplacementQueue<Item> = {
   visible: Item[];
   waiting: Item[];
};

export type QueueReplacement<Item> = ReplacementQueue<Item> & {
   replacement: Item;
};

/** Splits one ranked response into the visible cards and the waiting queue. */
export function createReplacementQueue<Item>(
   items: readonly Item[]
): ReplacementQueue<Item> {
   return {
      visible: items.slice(0, VISIBLE_RESULT_COUNT),
      waiting: items.slice(VISIBLE_RESULT_COUNT),
   };
}

/**
 * Swaps one visible item for the next waiting item, keeping its position.
 * Returns null when no item waits or the rejected item is not visible.
 */
export function replaceVisibleItem<Item extends QueueItem>(
   visible: readonly Item[],
   waiting: readonly Item[],
   rejectedSteamAppId: number
): QueueReplacement<Item> | null {
   const replacement = waiting[0];
   const rejectedIndex = visible.findIndex(
      (item) => item.steam_app_id === rejectedSteamAppId
   );
   if (replacement === undefined || rejectedIndex < 0) {
      return null;
   }

   const nextVisible = [...visible];
   nextVisible[rejectedIndex] = replacement;
   return {
      visible: nextVisible,
      waiting: waiting.slice(1),
      replacement,
   };
}
