import { useEffect, useRef, useState } from "react";

import {
   getReferenceDetails,
   type FacetOptionResponse,
   type OwnedGameSuggestionResponse,
   type ReferenceDetailsResponse,
} from "../../api";

export type SelectedReferenceFacets = {
   genres: FacetOptionResponse[];
   themes: FacetOptionResponse[];
   keywords: FacetOptionResponse[];
   gameModes: FacetOptionResponse[];
};

export type SelectedReference = {
   details: ReferenceDetailsResponse;
   selectedFacets: SelectedReferenceFacets;
};

export type DirectFacetKey = "genres" | "themes" | "gameModes";

export type ReferenceSelectionResult = {
   references: SelectedReference[];
   pendingSteamAppId: number | null;
   error: string | null;
   failedSuggestion: OwnedGameSuggestionResponse | null;
   addReference: (suggestion: OwnedGameSuggestionResponse) => Promise<boolean>;
   retryReference: () => Promise<boolean>;
   toggleDirectFacet: (
      steamAppId: number,
      facetKey: DirectFacetKey,
      option: FacetOptionResponse
   ) => boolean;
   toggleKeyword: (
      steamAppId: number,
      option: FacetOptionResponse
   ) => boolean;
   removeReference: (steamAppId: number) => void;
};

type ReferenceSelectionState = {
   sessionEpoch: number | null;
   references: SelectedReference[];
   pendingSteamAppId: number | null;
   error: string | null;
   failedSuggestion: OwnedGameSuggestionResponse | null;
};

type StoredReferences = {
   sessionEpoch: number | null;
   references: SelectedReference[];
};

type PendingReference = {
   sessionEpoch: number;
   steamAppId: number;
};

function emptySelectedFacets(): SelectedReferenceFacets {
   return {
      genres: [],
      themes: [],
      keywords: [],
      gameModes: [],
   };
}

function directFacetOptions(
   reference: SelectedReference,
   facetKey: DirectFacetKey
): FacetOptionResponse[] {
   switch (facetKey) {
      case "genres":
         return reference.details.facets.genres;
      case "themes":
         return reference.details.facets.themes;
      case "gameModes":
         return reference.details.facets.game_modes;
   }
}

function emptySelectionState(
   sessionEpoch: number | null
): ReferenceSelectionState {
   return {
      sessionEpoch,
      references: [],
      pendingSteamAppId: null,
      error: null,
      failedSuggestion: null,
   };
}

function errorMessage(error: unknown): string {
   if (error instanceof Error) {
      return error.message;
   }

   return "Unable to load reference game details.";
}

export function useReferenceSelection(
   sessionEpoch: number | null
): ReferenceSelectionResult {
   const [selectionState, setSelectionState] =
      useState<ReferenceSelectionState>(() => emptySelectionState(sessionEpoch));

   const referencesRef = useRef<StoredReferences>({
      sessionEpoch,
      references: [],
   });
   const pendingReferenceRef = useRef<PendingReference | null>(null);
   const activeSessionEpochRef = useRef(sessionEpoch);

   useEffect(() => {
      activeSessionEpochRef.current = sessionEpoch;
   }, [sessionEpoch]);

   const visibleState =
      selectionState.sessionEpoch === sessionEpoch
         ? selectionState
         : emptySelectionState(sessionEpoch);

   function referencesForCurrentProfile(): SelectedReference[] {
      if (referencesRef.current.sessionEpoch !== sessionEpoch) {
         return [];
      }

      return referencesRef.current.references;
   }

   function pendingForCurrentProfile(): PendingReference | null {
      if (pendingReferenceRef.current?.sessionEpoch !== sessionEpoch) {
         return null;
      }

      return pendingReferenceRef.current;
   }

   async function addReference(
      suggestion: OwnedGameSuggestionResponse
   ): Promise<boolean> {
      const currentReferences = referencesForCurrentProfile();

      if (
         sessionEpoch === null ||
         suggestion.metadata_status !== "ready" ||
         pendingForCurrentProfile() !== null ||
         currentReferences.length >= 3 ||
         currentReferences.some(
            (reference) =>
               reference.details.steam_app_id === suggestion.steam_app_id
         )
      ) {
         return false;
      }

      const requestSessionEpoch = sessionEpoch;
      const pendingReference: PendingReference = {
         sessionEpoch: requestSessionEpoch,
         steamAppId: suggestion.steam_app_id,
      };

      pendingReferenceRef.current = pendingReference;
      setSelectionState({
         sessionEpoch: requestSessionEpoch,
         references: currentReferences,
         pendingSteamAppId: suggestion.steam_app_id,
         error: null,
         failedSuggestion: null,
      });

      try {
         const details = await getReferenceDetails(
            suggestion.steam_app_id
         );

         if (activeSessionEpochRef.current !== requestSessionEpoch) {
            return false;
         }

         const selectedReference: SelectedReference = {
            details,
            selectedFacets: emptySelectedFacets(),
         };
         const latestReferences =
            referencesRef.current.sessionEpoch === requestSessionEpoch
               ? referencesRef.current.references
               : [];
         const nextReferences = [...latestReferences, selectedReference];

         referencesRef.current = {
            sessionEpoch: requestSessionEpoch,
            references: nextReferences,
         };
         setSelectionState({
            sessionEpoch: requestSessionEpoch,
            references: nextReferences,
            pendingSteamAppId: suggestion.steam_app_id,
            error: null,
            failedSuggestion: null,
         });

         return true;
      } catch (requestError: unknown) {
         if (activeSessionEpochRef.current !== requestSessionEpoch) {
            return false;
         }

         const currentProfileReferences =
            referencesRef.current.sessionEpoch === requestSessionEpoch
               ? referencesRef.current.references
               : [];

         setSelectionState({
            sessionEpoch: requestSessionEpoch,
            references: currentProfileReferences,
            pendingSteamAppId: suggestion.steam_app_id,
            error: errorMessage(requestError),
            failedSuggestion: suggestion,
         });

         return false;
      } finally {
         const pendingReference = pendingReferenceRef.current;

         if (
            activeSessionEpochRef.current === requestSessionEpoch &&
            pendingReference?.sessionEpoch === requestSessionEpoch &&
            pendingReference.steamAppId === suggestion.steam_app_id
         ) {
            pendingReferenceRef.current = null;

            setSelectionState((currentState) => {
               if (currentState.sessionEpoch !== requestSessionEpoch) {
                  return currentState;
               }

               return {
                  ...currentState,
                  pendingSteamAppId: null,
               };
            });
         }
      }
   }

   function toggleDirectFacet(
      steamAppId: number,
      facetKey: DirectFacetKey,
      option: FacetOptionResponse
   ): boolean {
      const currentReferences = referencesForCurrentProfile();
      const referenceIndex = currentReferences.findIndex(
         (reference) => reference.details.steam_app_id === steamAppId
      );

      if (referenceIndex < 0) {
         return false;
      }

      const reference = currentReferences[referenceIndex];
      const canonicalOption = directFacetOptions(reference, facetKey).find(
         (candidate) => candidate.id === option.id
      );

      if (canonicalOption === undefined) {
         return false;
      }

      const selectedOptions = reference.selectedFacets[facetKey];
      const alreadySelected = selectedOptions.some(
         (selectedOption) => selectedOption.id === canonicalOption.id
      );

      const nextSelectedOptions = alreadySelected
         ? selectedOptions.filter(
              (selectedOption) => selectedOption.id !== canonicalOption.id
           )
         : [...selectedOptions, canonicalOption];

      const nextReference: SelectedReference = {
         ...reference,
         selectedFacets: {
            ...reference.selectedFacets,
            [facetKey]: nextSelectedOptions,
         },
      };

      const nextReferences = currentReferences.map((currentReference, index) =>
         index === referenceIndex ? nextReference : currentReference
      );
      const currentPending = pendingForCurrentProfile();

      referencesRef.current = {
         sessionEpoch,
         references: nextReferences,
      };
      setSelectionState({
         sessionEpoch,
         references: nextReferences,
         pendingSteamAppId: currentPending?.steamAppId ?? null,
         error: visibleState.error,
         failedSuggestion: visibleState.failedSuggestion,
      });

      return true;
   }

   function removeReference(steamAppId: number): void {
      const nextReferences = referencesForCurrentProfile().filter(
         (reference) => reference.details.steam_app_id !== steamAppId
      );
      const currentPending = pendingForCurrentProfile();

      referencesRef.current = {
         sessionEpoch,
         references: nextReferences,
      };
      setSelectionState({
         sessionEpoch,
         references: nextReferences,
         pendingSteamAppId: currentPending?.steamAppId ?? null,
         error: visibleState.error,
         failedSuggestion: visibleState.failedSuggestion,
      });
   }

   function toggleKeyword(
      steamAppId: number,
      option: FacetOptionResponse
   ): boolean {
      const currentReferences = referencesForCurrentProfile();
      const referenceIndex = currentReferences.findIndex(
         (reference) => reference.details.steam_app_id === steamAppId
      );

      if (referenceIndex < 0) {
         return false;
      }

      const reference = currentReferences[referenceIndex];
      const selectedKeywords = reference.selectedFacets.keywords;
      const alreadySelected = selectedKeywords.some(
         (keyword) => keyword.id === option.id
      );

      if (!alreadySelected && selectedKeywords.length >= 3) {
         return false;
      }

      const nextKeywords = alreadySelected
         ? selectedKeywords.filter((keyword) => keyword.id !== option.id)
         : [...selectedKeywords, option];
      const nextReference: SelectedReference = {
         ...reference,
         selectedFacets: {
            ...reference.selectedFacets,
            keywords: nextKeywords,
         },
      };
      const nextReferences = currentReferences.map((currentReference, index) =>
         index === referenceIndex ? nextReference : currentReference
      );
      const currentPending = pendingForCurrentProfile();

      referencesRef.current = { sessionEpoch, references: nextReferences };
      setSelectionState({
         sessionEpoch,
         references: nextReferences,
         pendingSteamAppId: currentPending?.steamAppId ?? null,
         error: visibleState.error,
         failedSuggestion: visibleState.failedSuggestion,
      });
      return true;
   }

   return {
      references: visibleState.references,
      pendingSteamAppId: visibleState.pendingSteamAppId,
      error: visibleState.error,
      failedSuggestion: visibleState.failedSuggestion,
      addReference,
      retryReference: () =>
         visibleState.failedSuggestion === null
            ? Promise.resolve(false)
            : addReference(visibleState.failedSuggestion),
      toggleDirectFacet,
      toggleKeyword,
      removeReference,
   };
}
