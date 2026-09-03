import { useEffect, useRef, useState } from "react";

import type {
   FinalRecommendationResponse,
   RecommendationPreference,
} from "../../api";
import RecommendationResultsPanel from "./RecommendationResultsPanel";
import { usePreferenceValidation } from "./usePreferenceValidation";
import { useRecommendationRequest } from "./useRecommendationRequest";
import { useRecommendationSession } from "./useRecommendationSession";

type PreferenceValidationPanelProps = {
   sessionEpoch: number | null;
   preference: RecommendationPreference;
};

function PreferenceValidationPanel({
   sessionEpoch,
   preference,
}: PreferenceValidationPanelProps) {
   const validation = usePreferenceValidation(sessionEpoch, preference);
   const recommendation = useRecommendationRequest(
      sessionEpoch,
      validation.validatedPreference
   );
   const {
      state: sessionState,
      initialize: initializeSession,
      showAnother,
      playThis,
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
   const [focusRequest, setFocusRequest] = useState<{
      steamAppId: number;
      requestId: number;
   } | null>(null);
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
      if (sessionState.phase === "refining") {
         completeRefinement(recommendation.response.items);
      } else if (sessionState.phase === "idle") {
         initializeSession(
            validation.validatedPreference,
            recommendation.response.items
         );
      }
   }, [
      completeRefinement,
      initializeSession,
      recommendation.response,
      recommendation.status,
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
   const isValidating = validation.status === "validating";
   const isLoadingRecommendations = recommendation.status === "loading";
   const canSubmitForSession =
      sessionState.phase === "idle" || sessionState.phase === "editing";
   const canRequestRecommendations =
      validation.status === "valid" &&
      validation.validatedPreference !== null &&
      !isLoadingRecommendations &&
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

   return (
      <section
         className="preference-validation"
         aria-labelledby="preference-validation-heading"
      >
         <h3 id="preference-validation-heading">Preference preview</h3>
         <p>This is the exact preference Ludex will validate.</p>
         <pre data-testid="preference-draft">
            {JSON.stringify(preference, null, 2)}
         </pre>

         <button
            type="button"
            disabled={sessionEpoch === null || isValidating}
            onClick={() => {
               void validation.validate();
            }}
         >
            {isValidating ? "Validating preferences…" : "Validate preferences"}
         </button>

         {isValidating && (
            <p role="status">Checking this preference with Ludex…</p>
         )}
         {validation.status === "valid" && (
            <>
               <p role="status">Preference is valid.</p>
               <pre data-testid="validated-preference">
                  {JSON.stringify(validation.validatedPreference, null, 2)}
               </pre>
            </>
         )}
         {validation.status === "invalid" && validation.error !== null && (
            <p role="alert">
               {validation.errorField === null
                  ? validation.error
                  : `${validation.errorField}: ${validation.error}`}
            </p>
         )}

         <div className="preference-validation__recommendation-action">
            <button
               ref={recommendationActionRef}
               type="button"
               disabled={!canRequestRecommendations}
               onClick={() => {
                  if (
                     sessionState.phase === "editing"
                     && validation.validatedPreference !== null
                  ) {
                     beginRefinement(validation.validatedPreference);
                     recommendation.refine(
                        sessionState.rejectedSteamAppIds
                     );
                  } else {
                     recommendation.request();
                  }
               }}
            >
               {sessionState.phase === "refining"
                  ? "Refining recommendations…"
                  : isLoadingRecommendations
                    ? "Finding recommendations…"
                    : sessionState.phase === "editing"
                      ? recommendation.status === "error"
                        ? "Try refinement again"
                        : "Refine recommendations"
                      : sessionState.phase === "active"
                        ? "Recommendations ready"
                        : sessionState.phase === "accepted"
                          ? "Game selected"
                  : recommendation.status === "error"
                    ? "Try recommendations again"
                    : "Get recommendations"}
            </button>
         </div>

         {sessionState.phase === "editing"
            && recommendation.status === "error" && (
            <section
               className="recommendation-results__state recommendation-results__error"
               role="alert"
            >
               <h4>Refinement unavailable</h4>
               <p>
                  {recommendation.error
                     ?? "Something went wrong while refining recommendations."}
               </p>
               <p>Your current recommendation queue has been preserved.</p>
            </section>
         )}

         <RecommendationResultsPanel
            status={displayedStatus}
            response={displayedResponse}
            error={recommendation.error}
            session={sessionState}
            focusRequest={focusRequest}
            onShowAnother={(steamAppId) => {
               if (sessionState.phase !== "active") {
                  return;
               }
               const replacement = sessionState.waitingItems[0];
               if (replacement === undefined) {
                  return;
               }
               setFocusRequest((current) => ({
                  steamAppId: replacement.steam_app_id,
                  requestId: (current?.requestId ?? 0) + 1,
               }));
               showAnother(steamAppId);
            }}
            onPlayThis={(steamAppId) => {
               setFocusRequest((current) => ({
                  steamAppId,
                  requestId: (current?.requestId ?? 0) + 1,
               }));
               playThis(steamAppId);
            }}
            onStartOver={() => {
               focusStartOverRef.current = true;
               setFocusRequest(null);
               setRetainedResponse(null);
               startOver();
            }}
         />
      </section>
   );
}

export default PreferenceValidationPanel;
