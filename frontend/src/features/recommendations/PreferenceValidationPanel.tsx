import type { RecommendationPreference } from "../../api";
import RecommendationResultsPanel from "./RecommendationResultsPanel";
import { usePreferenceValidation } from "./usePreferenceValidation";
import { useRecommendationRequest } from "./useRecommendationRequest";

type PreferenceValidationPanelProps = {
   profileId: number | null;
   preference: RecommendationPreference;
};

function PreferenceValidationPanel({
   profileId,
   preference,
}: PreferenceValidationPanelProps) {
   const validation = usePreferenceValidation(profileId, preference);
   const recommendation = useRecommendationRequest(
      profileId,
      validation.validatedPreference
   );
   const isValidating = validation.status === "validating";
   const isLoadingRecommendations = recommendation.status === "loading";
   const canRequestRecommendations =
      validation.status === "valid" &&
      validation.validatedPreference !== null &&
      !isLoadingRecommendations;

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
            disabled={profileId === null || isValidating}
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
               type="button"
               disabled={!canRequestRecommendations}
               onClick={() => {
                  recommendation.request();
               }}
            >
               {isLoadingRecommendations
                  ? "Finding recommendations…"
                  : recommendation.status === "error"
                    ? "Try recommendations again"
                    : "Get recommendations"}
            </button>
         </div>

         <RecommendationResultsPanel
            status={recommendation.status}
            response={recommendation.response}
            error={recommendation.error}
         />
      </section>
   );
}

export default PreferenceValidationPanel;
