import { useEffect, useRef, useState } from "react";

import {
   getFinalRecommendations,
   refineFinalRecommendations,
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
   refine: (rejectedSteamAppIds: readonly number[]) => void;
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
   sessionEpoch: number | null,
   validatedPreference: RecommendationPreference | null
): RecommendationRequestResult {
   const [state, setState] = useState<StoredRecommendationRequest | null>(null);
   const generationRef = useRef(0);
   const inFlightRef = useRef<InFlightRecommendationRequest | null>(null);
   const key =
      sessionEpoch === null || validatedPreference === null
         ? null
         : JSON.stringify({ sessionEpoch, validatedPreference });
   const visibleState = key !== null && state?.key === key ? state : null;

   useEffect(() => {
      generationRef.current += 1;
   }, [key]);

   function startRequest(
      requestKey: string,
      sendRequest: () => Promise<FinalRecommendationResponse>
   ): void {
      if (key === null) {
         return;
      }
      const stateKey = key;

      if (
         inFlightRef.current?.generation === generationRef.current
      ) {
         return;
      }

      const requestGeneration = generationRef.current;
      setState({
         key: stateKey,
         status: "loading",
         response: null,
         error: null,
      });

      function finishWithError(error: unknown): void {
         if (generationRef.current === requestGeneration) {
            setState(recommendationRequestFailure(stateKey, error));
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
         pendingRequest = sendRequest();
      } catch (error: unknown) {
         finishWithError(error);
         return;
      }

      void pendingRequest.then(
         (response) => {
            if (generationRef.current === requestGeneration) {
               setState({
                  key: stateKey,
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

   function request(): void {
      if (sessionEpoch === null || validatedPreference === null || key === null) {
         return;
      }

      startRequest(
         JSON.stringify({ key, kind: "initial" }),
         () => getFinalRecommendations(validatedPreference)
      );
   }

   function refine(rejectedSteamAppIds: readonly number[]): void {
      if (sessionEpoch === null || validatedPreference === null || key === null) {
         return;
      }

      const rejectedIds = [...rejectedSteamAppIds];
      startRequest(
         JSON.stringify({ key, kind: "refinement", rejectedIds }),
         () => refineFinalRecommendations(
            validatedPreference,
            rejectedIds
         )
      );
   }

   return {
      status: visibleState?.status ?? "idle",
      response: visibleState?.response ?? null,
      error: visibleState?.error ?? null,
      request,
      refine,
   };
}
