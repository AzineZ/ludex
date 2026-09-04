import { useState } from "react";

import type { PreferenceConstraints } from "../../api";
import "./recommendations.css";
import PreferenceValidationPanel from "./PreferenceValidationPanel";
import RecommendationConstraints from "./RecommendationConstraints";
import ReferenceGameAutocomplete from "./ReferenceGameAutocomplete";
import ReferenceGameCard from "./ReferenceGameCard";
import ReferenceKeywordAutocomplete from "./ReferenceKeywordAutocomplete";
import { serializeRecommendationPreference } from "./preferenceSerialization";
import { useReferenceSelection } from "./useReferenceSelection";

type ReferenceSelectionSectionProps = {
   sessionEpoch: number | null;
};

const DEFAULT_CONSTRAINTS: PreferenceConstraints = {
   maximum_completion_minutes: null,
   play_status: "either",
};

function ReferenceSelectionSession({
   sessionEpoch,
}: ReferenceSelectionSectionProps) {
   const selection = useReferenceSelection(sessionEpoch);
   const [constraints, setConstraints] = useState<PreferenceConstraints>({
      ...DEFAULT_CONSTRAINTS,
   });
   const selectedSteamAppIds = selection.references.map(
      (reference) => reference.details.steam_app_id
   );
   const preference = serializeRecommendationPreference(
      selection.references,
      constraints
   );

   return (
      <section
         className="reference-selection"
         aria-labelledby="reference-selection-heading"
      >
         <header className="reference-selection__heading">
            <p className="app__step-label">Step 2 of 3</p>
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
               void selection.addReference(suggestion);
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
                     onClick={() => void selection.retryReference()}
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
                     onToggleFacet={(facetKey, option) => {
                        selection.toggleDirectFacet(
                           reference.details.steam_app_id,
                           facetKey,
                           option
                        );
                     }}
                     onRemove={selection.removeReference}
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

         <PreferenceValidationPanel
            sessionEpoch={sessionEpoch}
            preference={preference}
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
