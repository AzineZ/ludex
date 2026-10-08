import type { RecommendationPreference } from "../../../api";
import type { RecommendationWorkspaceView } from "../recommendationWorkspaceTypes";
import RecommendationResultsPanel from "../results/RecommendationResultsPanel";
import { useGuidedRecommendationFlow } from "./useGuidedRecommendationFlow";

type PreferenceValidationPanelProps = {
   sessionEpoch: number | null;
   preference: RecommendationPreference;
   activeView?: RecommendationWorkspaceView;
   onRecommendationsReady?: () => void;
   onRecommendationsReset?: () => void;
};

function PreferenceValidationPanel({
   sessionEpoch,
   preference,
   activeView,
   onRecommendationsReady,
   onRecommendationsReset,
}: PreferenceValidationPanelProps) {
   const {
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
      startOver,
   } = useGuidedRecommendationFlow({
      sessionEpoch,
      preference,
      onRecommendationsReady,
      onRecommendationsReset,
   });
   const isControlledWorkspace = activeView !== undefined;
   const displayedView = activeView ?? "preferences";

   const recommendationResults = (
      <RecommendationResultsPanel
         status={displayedStatus}
         response={displayedResponse}
         error={recommendation.error}
         session={sessionState}
         focusRequest={focusRequest}
         onShowAnother={showAnother}
         onPlayThis={playThis}
         onStartOver={startOver}
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
               className="app__primary-button"
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
