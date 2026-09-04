import { useId, useMemo, useState } from "react";

import type { FacetOptionResponse } from "../../api";
import { useReferenceKeywordBrowse } from "./useReferenceKeywordBrowse";

type ReferenceKeywordAutocompleteProps = {
   sessionEpoch: number | null;
   steamAppId: number;
   selectedKeywords: FacetOptionResponse[];
   onToggle: (option: FacetOptionResponse) => void;
};

function ReferenceKeywordAutocomplete({
   sessionEpoch,
   steamAppId,
   selectedKeywords,
   onToggle,
}: ReferenceKeywordAutocompleteProps) {
   const filterId = useId();
   const [filter, setFilter] = useState("");
   const browse = useReferenceKeywordBrowse(sessionEpoch, steamAppId);
   const selectedIds = useMemo(
      () => new Set(selectedKeywords.map((keyword) => keyword.id)),
      [selectedKeywords]
   );
   const normalizedFilter = filter.trim().toLocaleLowerCase();
   const visibleKeywords = browse.items.filter(
      (keyword) =>
         !selectedIds.has(keyword.id) &&
         keyword.name.toLocaleLowerCase().includes(normalizedFilter)
   );
   const limitReached = selectedKeywords.length >= 3;

   return (
      <section className="reference-keywords" aria-label="Keywords">
         <p>{selectedKeywords.length} of 3 keywords selected</p>
         {selectedKeywords.length > 0 && (
            <ul
               className="reference-keywords__selected"
               aria-label="Selected keywords"
            >
               {selectedKeywords.map((keyword) => (
                  <li key={keyword.id}>
                     <button
                        type="button"
                        aria-pressed="true"
                        aria-label={`Remove keyword ${keyword.name}`}
                        onClick={() => onToggle(keyword)}
                     >
                        {keyword.name} ×
                     </button>
                  </li>
               ))}
            </ul>
         )}

         {browse.status === "loading" && (
            <p role="status">Loading keywords…</p>
         )}
         {browse.status === "unavailable" && browse.error !== null && (
            <div className="reference-keywords__recovery">
               <p role="alert">{browse.error}</p>
               <button type="button" onClick={browse.retry}>
                  Try loading keywords again
               </button>
            </div>
         )}
         {browse.status === "ready" && browse.items.length === 0 && (
            <p role="status">No cached keywords are available for this game.</p>
         )}

         {browse.status === "ready" && browse.items.length > 0 && (
            <>
               <label htmlFor={filterId}>Filter keywords</label>
               <input
                  id={filterId}
                  type="search"
                  value={filter}
                  autoComplete="off"
                  onChange={(event) => setFilter(event.target.value)}
               />

               {limitReached && (
                  <p>Remove one selected keyword to choose another.</p>
               )}
               {browse.truncated && (
                  <p>Showing the first 250 cached keywords.</p>
               )}
               {visibleKeywords.length === 0 ? (
                  <p role="status">No keywords match that filter.</p>
               ) : (
                  <ul
                     className="reference-keywords__options"
                     aria-label="Available keywords"
                  >
                     {visibleKeywords.map((keyword) => (
                        <li key={keyword.id}>
                           <button
                              type="button"
                              aria-pressed="false"
                              aria-label={`Select keyword ${keyword.name}`}
                              disabled={limitReached}
                              onClick={() => onToggle(keyword)}
                           >
                              {keyword.name}
                           </button>
                        </li>
                     ))}
                  </ul>
               )}
            </>
         )}
      </section>
   );
}

export default ReferenceKeywordAutocomplete;
