import { useId, useState, type KeyboardEvent } from "react";

import type { OwnedGameSuggestionResponse } from "../../api";
import { useReferenceGameSearch } from "./useReferenceGameSearch";

type ReferenceGameAutocompleteProps = {
   profileId: number | null;
   selectedSteamAppIds: number[];
   onSelect: (suggestion: OwnedGameSuggestionResponse) => void;
};

type ReferenceGameAutocompleteSessionProps = ReferenceGameAutocompleteProps & {
   selectionLimitReached: boolean;
};

type ActiveOption = {
   steamAppId: number;
   query: string;
   resultIdentity: string;
};

function availabilityLabel(
   suggestion: OwnedGameSuggestionResponse,
   isSelected: boolean
): string {
   if (isSelected) {
      return "Already selected";
   }

   switch (suggestion.metadata_status) {
      case "ready":
         return "Ready";
      case "pending":
         return "Metadata pending";
      case "missing":
         return "Metadata unavailable";
      case "ambiguous":
         return "Metadata needs review";
   }
}

function ReferenceGameAutocompleteSession({
   profileId,
   selectedSteamAppIds,
   onSelect,
   selectionLimitReached,
}: ReferenceGameAutocompleteSessionProps) {
   const inputId = useId();
   const listboxId = `${inputId}-listbox`;
   const [query, setQuery] = useState("");
   const [activeOption, setActiveOption] = useState<ActiveOption | null>(null);

   const canSearch = profileId !== null && !selectionLimitReached;
   const searchResult = useReferenceGameSearch(
      profileId,
      canSearch ? query : ""
   );

   const resultIdentity = [
      ...searchResult.items.map(
         (suggestion) =>
            `${suggestion.steam_app_id}:${suggestion.metadata_status}`
      ),
      `selected:${selectedSteamAppIds.join(",")}`,
   ].join("|");

   const activeSteamAppId =
      activeOption !== null &&
      activeOption.query === query &&
      activeOption.resultIdentity === resultIdentity
         ? activeOption.steamAppId
         : null;

   function setActiveSteamAppId(steamAppId: number | null): void {
      setActiveOption(
         steamAppId === null
            ? null
            : {
                 steamAppId,
                 query,
                 resultIdentity,
              }
      );
   }
   const hasQuery = query.trim() !== "";
   const listboxVisible =
      canSearch &&
      hasQuery &&
      searchResult.status === "ready" &&
      searchResult.items.length > 0;

   function isSelectable(suggestion: OwnedGameSuggestionResponse): boolean {
      return (
         suggestion.metadata_status === "ready" &&
         !selectedSteamAppIds.includes(suggestion.steam_app_id)
      );
   }

   function optionId(suggestion: OwnedGameSuggestionResponse): string {
      return `${listboxId}-option-${suggestion.steam_app_id}`;
   }

   function selectSuggestion(suggestion: OwnedGameSuggestionResponse): void {
      if (!isSelectable(suggestion)) {
         return;
      }

      onSelect(suggestion);
      setQuery("");
      setActiveSteamAppId(null);
   }

   function handleKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
      if (event.key === "Escape") {
         if (query !== "") {
            event.preventDefault();
         }

         setQuery("");
         setActiveSteamAppId(null);
         return;
      }

      if (!listboxVisible) {
         return;
      }

      const selectableSuggestions = searchResult.items.filter(isSelectable);

      if (selectableSuggestions.length === 0) {
         return;
      }

      const activeIndex = selectableSuggestions.findIndex(
         (suggestion) => suggestion.steam_app_id === activeSteamAppId
      );

      if (event.key === "ArrowDown") {
         event.preventDefault();

         const nextIndex =
            activeIndex < 0
               ? 0
               : Math.min(activeIndex + 1, selectableSuggestions.length - 1);

         setActiveSteamAppId(selectableSuggestions[nextIndex].steam_app_id);
         return;
      }

      if (event.key === "ArrowUp") {
         event.preventDefault();

         const previousIndex =
            activeIndex < 0
               ? selectableSuggestions.length - 1
               : Math.max(activeIndex - 1, 0);

         setActiveSteamAppId(selectableSuggestions[previousIndex].steam_app_id);
         return;
      }

      if (event.key === "Home") {
         event.preventDefault();
         setActiveSteamAppId(selectableSuggestions[0].steam_app_id);
         return;
      }

      if (event.key === "End") {
         event.preventDefault();
         setActiveSteamAppId(
            selectableSuggestions[selectableSuggestions.length - 1].steam_app_id
         );
         return;
      }

      if (event.key === "Enter" && activeSteamAppId !== null) {
         const activeSuggestion = selectableSuggestions.find(
            (suggestion) => suggestion.steam_app_id === activeSteamAppId
         );

         if (activeSuggestion !== undefined) {
            event.preventDefault();
            selectSuggestion(activeSuggestion);
         }
      }
   }

   return (
      <section className="reference-game-autocomplete">
         <label htmlFor={inputId}>Find a reference game</label>
         <input
            id={inputId}
            type="search"
            role="combobox"
            value={query}
            placeholder="Search your owned games"
            autoComplete="off"
            disabled={!canSearch}
            aria-autocomplete="list"
            aria-expanded={listboxVisible}
            aria-controls={listboxId}
            aria-activedescendant={
               activeSteamAppId !== null && listboxVisible
                  ? `${listboxId}-option-${activeSteamAppId}`
                  : undefined
            }
            onChange={(event) => {
               setQuery(event.target.value);
               setActiveSteamAppId(null);
            }}
            onKeyDown={handleKeyDown}
         />

         {profileId === null && (
            <p>Select a profile to choose reference games.</p>
         )}

         {profileId !== null && selectionLimitReached && (
            <p>You can select up to three reference games.</p>
         )}

         {canSearch &&
            hasQuery &&
            (searchResult.status === "waiting" ||
               searchResult.status === "loading") && (
               <p role="status">Searching your library…</p>
            )}

         {canSearch &&
            hasQuery &&
            searchResult.status === "ready" &&
            searchResult.items.length === 0 && (
               <p role="status">No owned games match that search.</p>
            )}

         {canSearch &&
            hasQuery &&
            searchResult.status === "unavailable" &&
            searchResult.error !== null && (
               <p role="alert">{searchResult.error}</p>
            )}

         {listboxVisible && (
            <ul
               id={listboxId}
               role="listbox"
               className="reference-game-suggestions"
            >
               {searchResult.items.map((suggestion) => {
                  const isSelected = selectedSteamAppIds.includes(
                     suggestion.steam_app_id
                  );
                  const selectable = isSelectable(suggestion);
                  const active = suggestion.steam_app_id === activeSteamAppId;

                  return (
                     <li
                        id={optionId(suggestion)}
                        key={suggestion.steam_app_id}
                        role="option"
                        aria-selected={isSelected}
                        aria-disabled={!selectable}
                        className={active ? "is-active" : undefined}
                        onMouseDown={(event) => {
                           event.preventDefault();
                        }}
                        onClick={() => {
                           selectSuggestion(suggestion);
                        }}
                     >
                        <span>{suggestion.name}</span>
                        <span>{availabilityLabel(suggestion, isSelected)}</span>
                     </li>
                  );
               })}
            </ul>
         )}
      </section>
   );
}

function ReferenceGameAutocomplete(props: ReferenceGameAutocompleteProps) {
   const selectionLimitReached = props.selectedSteamAppIds.length >= 3;

   const sessionKey = [
      props.profileId ?? "no-profile",
      selectionLimitReached ? "limit-reached" : "search-open",
   ].join(":");

   return (
      <ReferenceGameAutocompleteSession
         key={sessionKey}
         {...props}
         selectionLimitReached={selectionLimitReached}
      />
   );
}

export default ReferenceGameAutocomplete;
