import { useEffect, useRef, useState } from "react";

import type {
   FinalRecommendationResponse,
   RecommendationPreference,
} from "../../../api";
import { nextFocusRequest, type FocusRequest } from "../results/focusRequest";
import { useRecommendationRequest } from "../results/useRecommendationRequest";
import { useRecommendationSession } from "../state/useRecommendationSession";
import { usePreferenceValidation } from "./usePreferenceValidation";

type GuidedRecommendationFlowOptions = {
   sessionEpoch: number | null;
   preference: RecommendationPreference;
   onRecommendationsReady?: () => void;
   onRecommendationsReset?: () => void;
};

function hasSelectedFacet(
   reference: RecommendationPreference["references"][number]
): boolean {
   return Object.values(reference.facets).some((ids) => ids.length > 0);
}

/**
 * Coordinates preference validation, the recommendation request, the
 * replacement-queue session, and focus hand-offs for Guided Recommendations.
 */
export function useGuidedRecommendationFlow({
   sessionEpoch,
   preference,
   onRecommendationsReady,
   onRecommendationsReset,
}: GuidedRecommendationFlowOptions) {
   const validation = usePreferenceValidation(sessionEpoch, preference);
   const recommendation = useRecommendationRequest(
      sessionEpoch,
      validation.validatedPreference
   );
   const {
      state: sessionState,
      initialize: initializeSession,
      showAnother: showAnotherInSession,
      playThis: playThisInSession,
      updateDraft,
      beginRefinement,
      completeRefinement,
      failRefinement,
      startOver,
   } = useRecommendationSession(sessionEpoch);
   const processedResponseRef = useRef<FinalRecommendationResponse | null>(
      null
   );
   const recommendationActionRef = useRef<HTMLButtonElement>(null);
   const focusStartOverRef = useRef(false);
   const pendingSubmissionRef = useRef<"initial" | "refinement" | null>(null);
   const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(
      null
   );
   const [retainedResponse, setRetainedResponse] =
      useState<FinalRecommendationResponse | null>(null);

   useEffect(() => {
      if (
         recommendation.status !== "ready"
         || recommendation.response === null
         || validation.validatedPreference === null
      ) {
         processedResponseRef.current = null;
         return;
      }
      if (processedResponseRef.current === recommendation.response) {
         return;
      }

      processedResponseRef.current = recommendation.response;
      setRetainedResponse(recommendation.response);
      const firstItem = recommendation.response.items[0];
      if (firstItem !== undefined) {
         const responseForFocus = recommendation.response;
         queueMicrotask(() => {
            if (processedResponseRef.current === responseForFocus) {
               setFocusRequest(nextFocusRequest(firstItem.steam_app_id));
            }
         });
      }
      if (sessionState.phase === "refining") {
         completeRefinement(recommendation.response.items);
      } else if (sessionState.phase === "idle") {
         initializeSession(
            validation.validatedPreference,
            recommendation.response.items
         );
      }
      onRecommendationsReady?.();
   }, [
      completeRefinement,
      initializeSession,
      recommendation.response,
      recommendation.status,
      onRecommendationsReady,
      sessionState.phase,
      validation.validatedPreference,
   ]);

   useEffect(() => {
      const comparablePreference =
         validation.status === "valid"
         && validation.validatedPreference !== null
            ? validation.validatedPreference
            : preference;
      updateDraft(comparablePreference);
   }, [
      preference,
      updateDraft,
      validation.status,
      validation.validatedPreference,
   ]);

   useEffect(() => {
      if (
         recommendation.status === "error"
         && sessionState.phase === "refining"
      ) {
         failRefinement();
      }
   }, [failRefinement, recommendation.status, sessionState.phase]);

   useEffect(() => {
      if (sessionState.phase === "idle" && focusStartOverRef.current) {
         focusStartOverRef.current = false;
         recommendationActionRef.current?.focus();
      }
   }, [sessionState.phase]);

   useEffect(() => {
      if (
         validation.status !== "valid"
         || validation.validatedPreference === null
         || pendingSubmissionRef.current === null
      ) {
         return;
      }

      const submission = pendingSubmissionRef.current;
      pendingSubmissionRef.current = null;
      if (submission === "refinement" && sessionState.phase === "editing") {
         beginRefinement(validation.validatedPreference);
         recommendation.refine(sessionState.rejectedSteamAppIds);
      } else if (submission === "initial" && sessionState.phase === "idle") {
         recommendation.request();
      }
   }, [
      beginRefinement,
      recommendation,
      sessionState.phase,
      sessionState.rejectedSteamAppIds,
      validation.status,
      validation.validatedPreference,
   ]);

   const isValidating = validation.status === "validating";
   const isLoadingRecommendations = recommendation.status === "loading";
   const canSubmitForSession =
      sessionState.phase === "idle" || sessionState.phase === "editing";
   const localRequirementMessage = preference.references.length === 0
      ? "Choose at least one reference game to continue."
      : preference.references.some((reference) => !hasSelectedFacet(reference))
         ? "Select at least one trait from every reference game to continue."
         : null;
   const canRequestRecommendations =
      sessionEpoch !== null &&
      !isValidating &&
      !isLoadingRecommendations &&
      localRequirementMessage === null &&
      canSubmitForSession;
   const hasRetainedSession =
      sessionState.phase !== "idle" && retainedResponse !== null;
   const displayedStatus = hasRetainedSession
      ? "ready"
      : recommendation.status === "ready" && sessionState.phase === "idle"
         ? "idle"
         : recommendation.status;
   const displayedResponse = hasRetainedSession
      ? retainedResponse
      : recommendation.response;

   function submitRecommendation(): void {
      const submission = sessionState.phase === "editing"
         ? "refinement"
         : "initial";
      if (validation.validatedPreference !== null) {
         if (submission === "refinement") {
            beginRefinement(validation.validatedPreference);
            recommendation.refine(sessionState.rejectedSteamAppIds);
         } else {
            recommendation.request();
         }
         return;
      }

      pendingSubmissionRef.current = submission;
      void validation.validate().then((isValid) => {
         if (!isValid) pendingSubmissionRef.current = null;
      });
   }

   function showAnother(steamAppId: number): void {
      if (sessionState.phase !== "active") {
         return;
      }
      const replacement = sessionState.waitingItems[0];
      if (replacement === undefined) {
         return;
      }
      setFocusRequest(nextFocusRequest(replacement.steam_app_id));
      showAnotherInSession(steamAppId);
   }

   function playThis(steamAppId: number): void {
      setFocusRequest(nextFocusRequest(steamAppId));
      playThisInSession(steamAppId);
   }

   function startOverFromResults(): void {
      focusStartOverRef.current = true;
      setFocusRequest(null);
      setRetainedResponse(null);
      startOver();
      onRecommendationsReset?.();
   }

   return {
      validation,
      recommendation,
      sessionState,
      focusRequest,
      recommendationActionRef,
      isValidating,
      isLoadingRecommendations,
      localRequirementMessage,
      canRequestRecommendations,
      hasRetainedSession,
      displayedStatus,
      displayedResponse,
      submitRecommendation,
      showAnother,
      playThis,
      startOver: startOverFromResults,
   };
}
