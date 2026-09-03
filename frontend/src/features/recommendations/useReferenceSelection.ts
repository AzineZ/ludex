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
   addReference: (suggestion: OwnedGameSuggestionResponse) => Promise<boolean>;
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
   profileId: number | null;
   references: SelectedReference[];
   pendingSteamAppId: number | null;
   error: string | null;
};

type StoredReferences = {
   profileId: number | null;
   references: SelectedReference[];
};

type PendingReference = {
   profileId: number;
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
   profileId: number | null
): ReferenceSelectionState {
   return {
      profileId,
      references: [],
      pendingSteamAppId: null,
      error: null,
   };
}

function errorMessage(error: unknown): string {
   if (error instanceof Error) {
      return error.message;
   }

   return "Unable to load reference game details.";
}

export function useReferenceSelection(
   profileId: number | null
): ReferenceSelectionResult {
   const [selectionState, setSelectionState] =
      useState<ReferenceSelectionState>(() => emptySelectionState(profileId));

   const referencesRef = useRef<StoredReferences>({
      profileId,
      references: [],
   });
   const pendingReferenceRef = useRef<PendingReference | null>(null);
   const activeProfileIdRef = useRef(profileId);

   useEffect(() => {
      activeProfileIdRef.current = profileId;
   }, [profileId]);

   const visibleState =
      selectionState.profileId === profileId
         ? selectionState
         : emptySelectionState(profileId);

   function referencesForCurrentProfile(): SelectedReference[] {
      if (referencesRef.current.profileId !== profileId) {
         return [];
      }

      return referencesRef.current.references;
   }

   function pendingForCurrentProfile(): PendingReference | null {
      if (pendingReferenceRef.current?.profileId !== profileId) {
         return null;
      }

      return pendingReferenceRef.current;
   }

   async function addReference(
      suggestion: OwnedGameSuggestionResponse
   ): Promise<boolean> {
      const currentReferences = referencesForCurrentProfile();

      if (
         profileId === null ||
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

      const requestProfileId = profileId;
      const pendingReference: PendingReference = {
         profileId: requestProfileId,
         steamAppId: suggestion.steam_app_id,
      };

      pendingReferenceRef.current = pendingReference;
      setSelectionState({
         profileId: requestProfileId,
         references: currentReferences,
         pendingSteamAppId: suggestion.steam_app_id,
         error: null,
      });

      try {
         const details = await getReferenceDetails(
            suggestion.steam_app_id
         );

         if (activeProfileIdRef.current !== requestProfileId) {
            return false;
         }

         const selectedReference: SelectedReference = {
            details,
            selectedFacets: emptySelectedFacets(),
         };
         const latestReferences =
            referencesRef.current.profileId === requestProfileId
               ? referencesRef.current.references
               : [];
         const nextReferences = [...latestReferences, selectedReference];

         referencesRef.current = {
            profileId: requestProfileId,
            references: nextReferences,
         };
         setSelectionState({
            profileId: requestProfileId,
            references: nextReferences,
            pendingSteamAppId: suggestion.steam_app_id,
            error: null,
         });

         return true;
      } catch (requestError: unknown) {
         if (activeProfileIdRef.current !== requestProfileId) {
            return false;
         }

         const currentProfileReferences =
            referencesRef.current.profileId === requestProfileId
               ? referencesRef.current.references
               : [];

         setSelectionState({
            profileId: requestProfileId,
            references: currentProfileReferences,
            pendingSteamAppId: suggestion.steam_app_id,
            error: errorMessage(requestError),
         });

         return false;
      } finally {
         const pendingReference = pendingReferenceRef.current;

         if (
            activeProfileIdRef.current === requestProfileId &&
            pendingReference?.profileId === requestProfileId &&
            pendingReference.steamAppId === suggestion.steam_app_id
         ) {
            pendingReferenceRef.current = null;

            setSelectionState((currentState) => {
               if (currentState.profileId !== requestProfileId) {
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
         profileId,
         references: nextReferences,
      };
      setSelectionState({
         profileId,
         references: nextReferences,
         pendingSteamAppId: currentPending?.steamAppId ?? null,
         error: visibleState.error,
      });

      return true;
   }

   function removeReference(steamAppId: number): void {
      const nextReferences = referencesForCurrentProfile().filter(
         (reference) => reference.details.steam_app_id !== steamAppId
      );
      const currentPending = pendingForCurrentProfile();

      referencesRef.current = {
         profileId,
         references: nextReferences,
      };
      setSelectionState({
         profileId,
         references: nextReferences,
         pendingSteamAppId: currentPending?.steamAppId ?? null,
         error: visibleState.error,
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

      referencesRef.current = { profileId, references: nextReferences };
      setSelectionState({
         profileId,
         references: nextReferences,
         pendingSteamAppId: currentPending?.steamAppId ?? null,
         error: visibleState.error,
      });
      return true;
   }

   return {
      references: visibleState.references,
      pendingSteamAppId: visibleState.pendingSteamAppId,
      error: visibleState.error,
      addReference,
      toggleDirectFacet,
      toggleKeyword,
      removeReference,
   };
}
