import { useEffect, useRef } from "react";

/** Moves focus to the returned element each time a new request arrives. */
export function useFocusOnRequest<Target extends HTMLElement>(
   focusRequestId: number | undefined
) {
   const targetRef = useRef<Target>(null);

   useEffect(() => {
      if (focusRequestId !== undefined) {
         targetRef.current?.focus();
      }
   }, [focusRequestId]);

   return targetRef;
}
