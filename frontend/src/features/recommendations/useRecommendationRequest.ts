import { useEffect, useRef, useState } from "react";

import {
   getFinalRecommendations,
   type FinalRecommendationResponse,
   type RecommendationPreference,
} from "../../api";


export type RecommendationRequestStatus =
   | "idle"
   | "loading"
   | "ready"
   | "error";

type StoredRecommendationRequest = {
   key: string;
   status: Exclude<RecommendationRequestStatus, "idle">;
   response: FinalRecommendationResponse | null;
   error: string | null;
};

type InFlightRecommendationRequest = {
   key: string;
   generation: number;
};

export type RecommendationRequestResult = {
   status: RecommendationRequestStatus;
   response: FinalRecommendationResponse | null;
   error: string | null;
   request: () => void;
};

function recommendationRequestError(error: unknown): string {
   if (error instanceof Error) {
      return error.message;
   }
   if (
      typeof error === "object" &&
      error !== null &&
      "message" in error &&
      typeof error.message === "string"
   ) {
      return error.message;
   }

   return "Unable to get recommendations.";
}

export function recommendationRequestFailure(
   key: string,
   error: unknown
): StoredRecommendationRequest {
   return {
      key,
      status: "error",
      response: null,
      error: recommendationRequestError(error),
   };
}

export function useRecommendationRequest(
   profileId: number | null,
   validatedPreference: RecommendationPreference | null
): RecommendationRequestResult {
   const [state, setState] = useState<StoredRecommendationRequest | null>(null);
   const generationRef = useRef(0);
   const inFlightRef = useRef<InFlightRecommendationRequest | null>(null);
   const key =
      profileId === null || validatedPreference === null
         ? null
         : JSON.stringify({ profileId, validatedPreference });
   const visibleState = key !== null && state?.key === key ? state : null;

   useEffect(() => {
      generationRef.current += 1;
   }, [key]);

   function request(): void {
      if (profileId === null || validatedPreference === null || key === null) {
         return;
      }

      if (
         inFlightRef.current?.key === key &&
         inFlightRef.current.generation === generationRef.current
      ) {
         return;
      }

      const requestKey = key;
      const requestGeneration = generationRef.current;
      setState({
         key: requestKey,
         status: "loading",
         response: null,
         error: null,
      });

      function finishWithError(error: unknown): void {
         if (generationRef.current === requestGeneration) {
            setState(recommendationRequestFailure(requestKey, error));
         }
         if (
            inFlightRef.current?.key === requestKey &&
            inFlightRef.current.generation === requestGeneration
         ) {
            inFlightRef.current = null;
         }
      }

      let pendingRequest: Promise<FinalRecommendationResponse>;
      try {
         pendingRequest = getFinalRecommendations(
            profileId,
            validatedPreference
         );
      } catch (error: unknown) {
         finishWithError(error);
         return;
      }

      void pendingRequest.then(
         (response) => {
            if (generationRef.current === requestGeneration) {
               setState({
                  key: requestKey,
                  status: "ready",
                  response,
                  error: null,
               });
            }
            if (
               inFlightRef.current?.key === requestKey &&
               inFlightRef.current.generation === requestGeneration
            ) {
               inFlightRef.current = null;
            }
         },
         finishWithError
      );

      inFlightRef.current = {
         key: requestKey,
         generation: requestGeneration,
      };
   }

   return {
      status: visibleState?.status ?? "idle",
      response: visibleState?.response ?? null,
      error: visibleState?.error ?? null,
      request,
   };
}
