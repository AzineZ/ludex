import { useId, useState, type KeyboardEvent } from "react";

import type { FacetOptionResponse } from "../../api";
import { useReferenceKeywordSearch } from "./useReferenceKeywordSearch";

type ReferenceKeywordAutocompleteProps = {
   profileId: number | null;
   steamAppId: number;
   selectedKeywords: FacetOptionResponse[];
   onToggle: (option: FacetOptionResponse) => void;
};

function ReferenceKeywordAutocomplete({
   profileId,
   steamAppId,
   selectedKeywords,
   onToggle,
}: ReferenceKeywordAutocompleteProps) {
   const inputId = useId();
   const listboxId = `${inputId}-listbox`;
   const [query, setQuery] = useState("");
   const [activeId, setActiveId] = useState<number | null>(null);
   const limitReached = selectedKeywords.length >= 3;
   const canSearch = profileId !== null && !limitReached;
   const result = useReferenceKeywordSearch(
      profileId,
      steamAppId,
      canSearch ? query : ""
   );
   const selectedIds = new Set(selectedKeywords.map((keyword) => keyword.id));
   const suggestions = result.items.filter((item) => !selectedIds.has(item.id));
   const hasQuery = query.trim() !== "";
   const listboxVisible =
      canSearch && hasQuery && result.status === "ready" && suggestions.length > 0;
   const activeSuggestion = suggestions.find((item) => item.id === activeId);

   function choose(option: FacetOptionResponse): void {
      onToggle(option);
      setQuery("");
      setActiveId(null);
   }

   function handleKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
      if (event.key === "Escape") {
         setQuery("");
         setActiveId(null);
         return;
      }
      if (!listboxVisible) {
         return;
      }
      const activeIndex = suggestions.findIndex((item) => item.id === activeId);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
         event.preventDefault();
         const nextIndex = event.key === "ArrowDown"
            ? Math.min(activeIndex + 1, suggestions.length - 1)
            : activeIndex < 0
              ? suggestions.length - 1
              : Math.max(activeIndex - 1, 0);
         setActiveId(suggestions[nextIndex].id);
      } else if (event.key === "Enter" && activeSuggestion !== undefined) {
         event.preventDefault();
         choose(activeSuggestion);
      }
   }

   return (
      <section className="reference-keywords" aria-label="Keywords">
         <p>{selectedKeywords.length} of 3 keywords selected</p>
         {selectedKeywords.length > 0 && (
            <ul className="reference-keywords__selected">
               {selectedKeywords.map((keyword) => (
                  <li key={keyword.id}>
                     <button
                        type="button"
                        onClick={() => onToggle(keyword)}
                        aria-label={`Remove keyword ${keyword.name}`}
                     >
                        {keyword.name} ×
                     </button>
                  </li>
               ))}
            </ul>
         )}

         <label htmlFor={inputId}>Find keywords</label>
         <input
            id={inputId}
            type="search"
            role="combobox"
            value={query}
            disabled={!canSearch}
            autoComplete="off"
            aria-autocomplete="list"
            aria-expanded={listboxVisible}
            aria-controls={listboxId}
            aria-activedescendant={
               listboxVisible && activeSuggestion !== undefined
                  ? `${listboxId}-option-${activeSuggestion.id}`
                  : undefined
            }
            onChange={(event) => {
               setQuery(event.target.value);
               setActiveId(null);
            }}
            onKeyDown={handleKeyDown}
         />

         {canSearch && hasQuery &&
            (result.status === "waiting" || result.status === "loading") && (
               <p role="status">Searching keywords…</p>
            )}
         {canSearch && hasQuery && result.status === "ready" &&
            suggestions.length === 0 && (
               <p role="status">No keywords match that search.</p>
            )}
         {canSearch && hasQuery && result.status === "unavailable" &&
            result.error !== null && <p role="alert">{result.error}</p>}

         {listboxVisible && (
            <ul id={listboxId} role="listbox">
               {suggestions.map((option) => (
                  <li
                     id={`${listboxId}-option-${option.id}`}
                     key={option.id}
                     role="option"
                     aria-selected={option.id === activeId}
                     onMouseDown={(event) => event.preventDefault()}
                     onClick={() => choose(option)}
                  >
                     {option.name}
                  </li>
               ))}
            </ul>
         )}
      </section>
   );
}

export default ReferenceKeywordAutocomplete;
