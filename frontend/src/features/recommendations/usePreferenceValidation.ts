import { useState } from "react";

import {
   validateRecommendationPreference,
   type RecommendationPreference,
} from "../../api";

export type PreferenceValidationStatus =
   | "idle"
   | "validating"
   | "valid"
   | "invalid";

type ValidationState = {
   key: string;
   status: Exclude<PreferenceValidationStatus, "idle">;
   validatedPreference: RecommendationPreference | null;
   error: string | null;
   errorField: string | null;
};

export type PreferenceValidationResult = {
   status: PreferenceValidationStatus;
   validatedPreference: RecommendationPreference | null;
   error: string | null;
   errorField: string | null;
   validate: () => Promise<boolean>;
};

export function preferenceValidationError(error: unknown): {
   message: string;
   field: string | null;
} {
   return {
      message:
         error instanceof Error
            ? error.message
            : "Unable to validate recommendation preferences.",
      field:
         error instanceof Error &&
         "field" in error &&
         (typeof error.field === "string" || error.field === null)
            ? error.field
            : null,
   };
}

export function usePreferenceValidation(
   profileId: number | null,
   preference: RecommendationPreference
): PreferenceValidationResult {
   const [state, setState] = useState<ValidationState | null>(null);
   const key = JSON.stringify({ profileId, preference });
   const visibleState = state?.key === key ? state : null;

   function validate(): Promise<boolean> {
      if (profileId === null) {
         return Promise.resolve(false);
      }

      const requestKey = key;
      setState({
         key: requestKey,
         status: "validating",
         validatedPreference: null,
         error: null,
         errorField: null,
      });

      return validateRecommendationPreference(profileId, preference).then(
         (validatedPreference) => {
            setState({
               key: requestKey,
               status: "valid",
               validatedPreference,
               error: null,
               errorField: null,
            });
            return true;
         },
         (error: unknown) => {
            const details = preferenceValidationError(error);
            setState({
               key: requestKey,
               status: "invalid",
               validatedPreference: null,
               error: details.message,
               errorField: details.field,
            });
            return false;
         }
      );
   }

   return {
      status: visibleState?.status ?? "idle",
      validatedPreference: visibleState?.validatedPreference ?? null,
      error: visibleState?.error ?? null,
      errorField: visibleState?.errorField ?? null,
      validate,
   };
}
