import { useState } from "react";

import type { PreferenceConstraints } from "../../api";
import "./recommendations.css";
import PreferenceValidationPanel from "./PreferenceValidationPanel";
import RecommendationConstraints from "./RecommendationConstraints";
import ReferenceGameAutocomplete from "./ReferenceGameAutocomplete";
import ReferenceGameCard from "./ReferenceGameCard";
import ReferenceKeywordAutocomplete from "./ReferenceKeywordAutocomplete";
import { serializeRecommendationPreference } from "./preferenceSerialization";
import type { RecommendationWorkspaceView } from "./recommendationWorkspace";
import { useReferenceSelection } from "./useReferenceSelection";

type ReferenceSelectionSectionProps = {
   sessionEpoch: number | null;
   activeView?: RecommendationWorkspaceView;
   onRecommendationsReady?: () => void;
   onRecommendationsReset?: () => void;
};

const DEFAULT_CONSTRAINTS: PreferenceConstraints = {
   maximum_completion_minutes: null,
   play_status: "either",
};

function ReferenceSelectionSession({
   sessionEpoch,
   activeView = "preferences",
   onRecommendationsReady,
   onRecommendationsReset,
}: ReferenceSelectionSectionProps) {
   const selection = useReferenceSelection(sessionEpoch);
   const [constraints, setConstraints] = useState<PreferenceConstraints>({
      ...DEFAULT_CONSTRAINTS,
   });
   const [requestedExpandedSteamAppId, setRequestedExpandedSteamAppId] =
      useState<number | null | undefined>(undefined);
   const selectedSteamAppIds = selection.references.map(
      (reference) => reference.details.steam_app_id
   );
   const expandedSteamAppId =
      requestedExpandedSteamAppId === null
         ? null
         : requestedExpandedSteamAppId !== undefined
           && selection.references.some(
              (reference) =>
                 reference.details.steam_app_id === requestedExpandedSteamAppId
           )
         ? requestedExpandedSteamAppId
         : selection.references.at(-1)?.details.steam_app_id ?? null;
   const preference = serializeRecommendationPreference(
      selection.references,
      constraints
   );

   return (
      <section
         className={
            activeView === "recommendations"
               ? "reference-selection reference-selection--recommendations"
               : "reference-selection"
         }
         aria-labelledby={
            activeView === "preferences"
               ? "reference-selection-heading"
               : undefined
         }
      >
         <div
            className="reference-selection__preferences"
            hidden={activeView !== "preferences"}
         >
            <header className="reference-selection__heading">
               <h3 id="reference-selection-heading">Choose reference games</h3>
               <p>
                  Choose 1 to 3 games you own. For each game, select at least one
                  trait you want Ludex to match.
               </p>
               <p className="reference-selection__count">
                  {selection.references.length} of 3 reference games selected
               </p>
            </header>

            <ReferenceGameAutocomplete
               sessionEpoch={sessionEpoch}
               selectedSteamAppIds={selectedSteamAppIds}
               onSelect={(suggestion) => {
                  void selection.addReference(suggestion).then((wasAdded) => {
                     if (wasAdded) {
                        setRequestedExpandedSteamAppId(suggestion.steam_app_id);
                     }
                  });
               }}
            />

            {selection.pendingSteamAppId !== null && (
               <p role="status">Loading reference game details…</p>
            )}

            {selection.error !== null && (
               <div className="reference-selection__recovery">
                  <p role="alert">{selection.error}</p>
                  {selection.failedSuggestion !== null && (
                     <button
                        type="button"
                        onClick={() => {
                           const failedSuggestion = selection.failedSuggestion;
                           if (failedSuggestion === null) {
                              return;
                           }
                           void selection.retryReference().then((wasAdded) => {
                              if (wasAdded) {
                                 setRequestedExpandedSteamAppId(
                                    failedSuggestion.steam_app_id
                                 );
                              }
                           });
                        }}
                     >
                        Try loading {selection.failedSuggestion.name} again
                     </button>
                  )}
               </div>
            )}

            {selection.references.length > 0 && (
               <div className="reference-selection__cards">
                  {selection.references.map((reference) => (
                     <ReferenceGameCard
                        key={reference.details.steam_app_id}
                        reference={reference}
                        isExpanded={
                           expandedSteamAppId === reference.details.steam_app_id
                        }
                        onToggleExpanded={() => {
                           setRequestedExpandedSteamAppId(
                              expandedSteamAppId === reference.details.steam_app_id
                                 ? null
                                 : reference.details.steam_app_id
                           );
                        }}
                        onToggleFacet={(facetKey, option) => {
                           selection.toggleDirectFacet(
                              reference.details.steam_app_id,
                              facetKey,
                              option
                           );
                        }}
                        onRemove={(steamAppId) => {
                           const remainingReference = selection.references.find(
                              (candidate) =>
                                 candidate.details.steam_app_id !== steamAppId
                           );
                           selection.removeReference(steamAppId);
                           if (expandedSteamAppId === steamAppId) {
                              setRequestedExpandedSteamAppId(
                                 remainingReference?.details.steam_app_id ?? null
                              );
                           }
                        }}
                        keywordControl={
                           <ReferenceKeywordAutocomplete
                              sessionEpoch={sessionEpoch}
                              steamAppId={reference.details.steam_app_id}
                              selectedKeywords={reference.selectedFacets.keywords}
                              onToggle={(option) => {
                                 selection.toggleKeyword(
                                    reference.details.steam_app_id,
                                    option
                                 );
                              }}
                           />
                        }
                     />
                  ))}
               </div>
            )}

            <RecommendationConstraints
               value={constraints}
               onChange={setConstraints}
            />
         </div>

         <PreferenceValidationPanel
            sessionEpoch={sessionEpoch}
            preference={preference}
            activeView={activeView}
            onRecommendationsReady={onRecommendationsReady}
            onRecommendationsReset={onRecommendationsReset}
         />
      </section>
   );
}

function ReferenceSelectionSection(props: ReferenceSelectionSectionProps) {
   return (
      <ReferenceSelectionSession
         key={props.sessionEpoch ?? "no-session"}
         {...props}
      />
   );
}

export default ReferenceSelectionSection;
