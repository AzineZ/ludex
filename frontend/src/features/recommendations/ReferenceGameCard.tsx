import { useId, type ReactNode } from "react";

import type { FacetOptionResponse } from "../../api";
import type {
   DirectFacetKey,
   SelectedReference,
} from "./useReferenceSelection";

type ReferenceGameCardProps = {
   reference: SelectedReference;
   onToggleFacet: (
      facetKey: DirectFacetKey,
      option: FacetOptionResponse
   ) => void;
   onRemove: (steamAppId: number) => void;
   keywordControl?: ReactNode;
};

type FacetGroupDefinition = {
   key: DirectFacetKey;
   label: string;
   emptyMessage: string;
   options: (reference: SelectedReference) => FacetOptionResponse[];
};

const FACET_GROUPS: FacetGroupDefinition[] = [
   {
      key: "genres",
      label: "Genres",
      emptyMessage: "No genre metadata available.",
      options: (reference) => reference.details.facets.genres,
   },
   {
      key: "themes",
      label: "Themes",
      emptyMessage: "No theme metadata available.",
      options: (reference) => reference.details.facets.themes,
   },
   {
      key: "gameModes",
      label: "Game modes",
      emptyMessage: "No game mode metadata available.",
      options: (reference) => reference.details.facets.game_modes,
   },
];

function ReferenceGameCard({
   reference,
   onToggleFacet,
   onRemove,
   keywordControl,
}: ReferenceGameCardProps) {
   const headingId = useId();
   const { details, selectedFacets } = reference;

   return (
      <article className="reference-game-card" aria-labelledby={headingId}>
         <header className="reference-game-card__header">
            {details.cover_url === null ? (
               <div className="reference-game-card__cover-fallback">
                  Cover unavailable
               </div>
            ) : (
               <img
                  className="reference-game-card__cover"
                  src={details.cover_url}
                  alt={`${details.name} cover`}
               />
            )}

            <div className="reference-game-card__identity">
               <h3 id={headingId}>{details.name}</h3>
               <button
                  type="button"
                  className="reference-game-card__remove"
                  onClick={() => {
                     onRemove(details.steam_app_id);
                  }}
               >
                  Remove {details.name}
               </button>
            </div>
         </header>

         <div className="reference-game-card__facets">
            {FACET_GROUPS.map((group) => {
               const options = group.options(reference);
               const selectedIds = new Set(
                  selectedFacets[group.key].map((option) => option.id)
               );

               return (
                  <fieldset
                     className="reference-game-card__facet-group"
                     key={group.key}
                  >
                     <legend>{group.label}</legend>

                     {options.length === 0 ? (
                        <p>{group.emptyMessage}</p>
                     ) : (
                        <div className="reference-game-card__facet-options">
                           {options.map((option) => (
                              <button
                                 key={option.id}
                                 type="button"
                                 className="reference-game-card__facet"
                                 aria-pressed={selectedIds.has(option.id)}
                                 onClick={() => {
                                    onToggleFacet(group.key, option);
                                 }}
                              >
                                 {option.name}
                              </button>
                           ))}
                        </div>
                     )}
                  </fieldset>
               );
            })}
         </div>

         {keywordControl}
      </article>
   );
}

export default ReferenceGameCard;
