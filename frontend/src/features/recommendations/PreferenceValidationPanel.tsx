import { useEffect, useRef, useState } from "react";

import type {
   FinalRecommendationResponse,
   RecommendationPreference,
} from "../../api";
import RecommendationResultsPanel from "./RecommendationResultsPanel";
import type { RecommendationWorkspaceView } from "./recommendationWorkspace";
import { usePreferenceValidation } from "./usePreferenceValidation";
import { useRecommendationRequest } from "./useRecommendationRequest";
import { useRecommendationSession } from "./useRecommendationSession";

type PreferenceValidationPanelProps = {
   sessionEpoch: number | null;
   preference: RecommendationPreference;
   activeView?: RecommendationWorkspaceView;
   onRecommendationsReady?: () => void;
   onRecommendationsReset?: () => void;
};

function hasSelectedFacet(
   reference: RecommendationPreference["references"][number]
): boolean {
   return Object.values(reference.facets).some((ids) => ids.length > 0);
}

function PreferenceValidationPanel({
   sessionEpoch,
   preference,
   activeView,
   onRecommendationsReady,
   onRecommendationsReset,
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
   const pendingSubmissionRef = useRef<"initial" | "refinement" | null>(null);
   const [focusRequest, setFocusRequest] = useState<{
      steamAppId: number;
      requestId: number;
   } | null>(null);
   const [retainedResponse, setRetainedResponse] =
      useState<FinalRecommendationResponse | null>(null);
   const isControlledWorkspace = activeView !== undefined;
   const displayedView = activeView ?? "preferences";

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
               setFocusRequest((current) => ({
                  steamAppId: firstItem.steam_app_id,
                  requestId: (current?.requestId ?? 0) + 1,
               }));
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

   const recommendationResults = (
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
            onRecommendationsReset?.();
         }}
      />
   );

   return (
      <>
         <section
            className="preference-validation"
            aria-labelledby="preference-validation-heading"
            hidden={isControlledWorkspace && displayedView !== "preferences"}
         >
         <div className="preference-validation__summary">
            <p className="app__step-label">Step 3 of 3</p>
            <h3 id="preference-validation-heading">Find your next game</h3>
            <p>
               Ludex will check your choices and search your cached library.
            </p>
         </div>

         {isValidating && (
            <p role="status">Checking this preference with Ludex…</p>
         )}
         {validation.status === "invalid" && validation.error !== null && (
            <p role="alert">{validation.error}</p>
         )}
         {localRequirementMessage !== null && (
            <p
               className="preference-validation__requirement"
               id="recommendation-requirement"
            >
               {localRequirementMessage}
            </p>
         )}

         <div className="preference-validation__recommendation-action">
            <button
               ref={recommendationActionRef}
               type="button"
               aria-describedby={
                  localRequirementMessage === null
                     ? undefined
                     : "recommendation-requirement"
               }
               disabled={!canRequestRecommendations}
               onClick={submitRecommendation}
            >
               {isValidating
                  ? "Checking preferences…"
                  : sessionState.phase === "refining"
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

            {(!isControlledWorkspace || !hasRetainedSession) &&
               recommendationResults}
         </section>

         {isControlledWorkspace ? (
            <div
               className="recommendation-workspace__results"
               hidden={displayedView !== "recommendations"}
            >
               {hasRetainedSession && recommendationResults}
            </div>
         ) : null}
      </>
   );
}

export default PreferenceValidationPanel;
