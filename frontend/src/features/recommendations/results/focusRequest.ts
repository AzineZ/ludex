export type FocusRequest = {
   steamAppId: number;
   requestId: number;
};

/** Builds a state updater that asks one result card to take focus again. */
export function nextFocusRequest(steamAppId: number) {
   return (current: FocusRequest | null): FocusRequest => ({
      steamAppId,
      requestId: (current?.requestId ?? 0) + 1,
   });
}

/** Returns the pending focus request for one card, if it is the target. */
export function focusRequestIdFor(
   focusRequest: FocusRequest | null,
   steamAppId: number
): number | undefined {
   return focusRequest?.steamAppId === steamAppId
      ? focusRequest.requestId
      : undefined;
}
