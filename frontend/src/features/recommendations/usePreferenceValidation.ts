import { useEffect, useRef, useState } from "react";

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
   sessionEpoch: number | null,
   preference: RecommendationPreference
): PreferenceValidationResult {
   const [state, setState] = useState<ValidationState | null>(null);
   const generationRef = useRef(0);
   const key = JSON.stringify({ sessionEpoch, preference });
   const visibleState = state?.key === key ? state : null;

   useEffect(() => {
      generationRef.current += 1;
   }, [key]);

   function validate(): Promise<boolean> {
      if (sessionEpoch === null) {
         return Promise.resolve(false);
      }

      const requestKey = key;
      const requestGeneration = generationRef.current + 1;
      generationRef.current = requestGeneration;
      setState({
         key: requestKey,
         status: "validating",
         validatedPreference: null,
         error: null,
         errorField: null,
      });

      return validateRecommendationPreference(preference).then(
         (validatedPreference) => {
            if (generationRef.current !== requestGeneration) return false;
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
            if (generationRef.current !== requestGeneration) return false;
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
