import type { RecommendationPreference } from "../../api";
import { usePreferenceValidation } from "./usePreferenceValidation";

type PreferenceValidationPanelProps = {
   profileId: number | null;
   preference: RecommendationPreference;
};

function PreferenceValidationPanel({
   profileId,
   preference,
}: PreferenceValidationPanelProps) {
   const validation = usePreferenceValidation(profileId, preference);
   const isValidating = validation.status === "validating";

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
      </section>
   );
}

export default PreferenceValidationPanel;
