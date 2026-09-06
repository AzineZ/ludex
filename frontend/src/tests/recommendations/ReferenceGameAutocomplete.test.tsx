import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OwnedGameSuggestionResponse } from "../../api";
import ReferenceGameAutocomplete from "../../features/recommendations/references/ReferenceGameAutocomplete";
import {
   useReferenceGameSearch,
   type ReferenceGameSearchResult,
} from "../../features/recommendations/references/useReferenceGameSearch";


vi.mock(
   "../../features/recommendations/references/useReferenceGameSearch",
   async (importOriginal) => {
      const actual = await importOriginal<
         typeof import(
            "../../features/recommendations/references/useReferenceGameSearch"
         )
      >();

      return {
         ...actual,
         useReferenceGameSearch: vi.fn(),
      };
   }
);

const idleResult: ReferenceGameSearchResult = {
   status: "idle",
   items: [],
   error: null,
};

const suggestions: OwnedGameSuggestionResponse[] = [
   {
      steam_app_id: 100,
      name: "Ready Game",
      cover_url: null,
      metadata_status: "ready",
   },
   {
      steam_app_id: 200,
      name: "Pending Game",
      cover_url: null,
      metadata_status: "pending",
   },
   {
      steam_app_id: 300,
      name: "Missing Game",
      cover_url: null,
      metadata_status: "missing",
   },
   {
      steam_app_id: 400,
      name: "Ambiguous Game",
      cover_url: null,
      metadata_status: "ambiguous",
   },
   {
      steam_app_id: 500,
      name: "Selected Game",
      cover_url: null,
      metadata_status: "ready",
   },
   {
      steam_app_id: 600,
      name: "Another Ready Game",
      cover_url: null,
      metadata_status: "ready",
   },
];

const mockedUseReferenceGameSearch = vi.mocked(
   useReferenceGameSearch
);

function renderAutocomplete(
   overrides: Partial<{
      sessionEpoch: number | null;
      selectedSteamAppIds: number[];
      onSelect: (suggestion: OwnedGameSuggestionResponse) => void;
   }> = {}
) {
   const onSelect = overrides.onSelect ?? vi.fn();
   const sessionEpoch = overrides.sessionEpoch === undefined
      ? 1
      : overrides.sessionEpoch;

   const view = render(
      <ReferenceGameAutocomplete
         sessionEpoch={sessionEpoch}
         selectedSteamAppIds={overrides.selectedSteamAppIds ?? []}
         onSelect={onSelect}
      />
   );

   return {
      input: screen.getByRole("combobox", {
         name: "Find a reference game",
      }),
      onSelect,
      rerender: view.rerender,
   };
}

describe("ReferenceGameAutocomplete", () => {
   beforeEach(() => {
      mockedUseReferenceGameSearch.mockReset();
      mockedUseReferenceGameSearch.mockReturnValue(idleResult);
   });

   it("requires an active Steam session before searching", () => {
      const { input } = renderAutocomplete({ sessionEpoch: null });

      expect(input).toBeDisabled();
      expect(
         screen.getByText("Start a Steam session to choose reference games.")
      ).toBeInTheDocument();
   });

   it("disables search after three references are selected", () => {
      const { input } = renderAutocomplete({
         selectedSteamAppIds: [10, 20, 30],
      });

      expect(input).toBeDisabled();
      expect(
         screen.getByText("You can select up to three reference games.")
      ).toBeInTheDocument();
   });

   it.each(["waiting", "loading"] as const)(
      "shows search progress while %s",
      (status) => {
         mockedUseReferenceGameSearch.mockReturnValue({
            status,
            items: [],
            error: null,
         });
         const { input } = renderAutocomplete();

         fireEvent.change(input, {
            target: { value: "game" },
         });

         expect(mockedUseReferenceGameSearch).toHaveBeenLastCalledWith(
            1,
            "game"
         );
         expect(
            screen.getByText("Searching your library…")
         ).toBeInTheDocument();
      }
   );

   it("shows a successful empty result", () => {
      mockedUseReferenceGameSearch.mockReturnValue({
         status: "ready",
         items: [],
         error: null,
      });
      const { input } = renderAutocomplete();

      fireEvent.change(input, {
         target: { value: "unknown" },
      });

      expect(
         screen.getByText("No owned games match that search.")
      ).toBeInTheDocument();
   });

   it("shows the backend search error", () => {
      mockedUseReferenceGameSearch.mockReturnValue({
         status: "unavailable",
         items: [],
         error: "The selected profile does not exist.",
      });
      const { input } = renderAutocomplete();

      fireEvent.change(input, {
         target: { value: "game" },
      });

      expect(screen.getByRole("alert")).toHaveTextContent(
         "The selected profile does not exist."
      );
   });

   it("renders readiness and disables unavailable or selected games", () => {
      mockedUseReferenceGameSearch.mockReturnValue({
         status: "ready",
         items: suggestions,
         error: null,
      });
      const { input } = renderAutocomplete({
         selectedSteamAppIds: [500],
      });

      fireEvent.change(input, {
         target: { value: "game" },
      });

      expect(
         screen.getByRole("option", { name: /^Ready Game.*Ready/i })
      ).toHaveAttribute("aria-disabled", "false");
      expect(
         screen.getByRole("option", {
            name: /Pending Game.*Metadata pending/i,
         })
      ).toHaveAttribute("aria-disabled", "true");
      expect(
         screen.getByRole("option", {
            name: /Missing Game.*Metadata unavailable/i,
         })
      ).toHaveAttribute("aria-disabled", "true");
      expect(
         screen.getByRole("option", {
            name: /Ambiguous Game.*Metadata needs review/i,
         })
      ).toHaveAttribute("aria-disabled", "true");
      expect(
         screen.getByRole("option", {
            name: /Selected Game.*Already selected/i,
         })
      ).toHaveAttribute("aria-disabled", "true");
      expect(
         screen.getByRole("option", {
            name: /Selected Game.*Already selected/i,
         })
      ).toHaveAttribute("aria-selected", "true");
   });

   it("selects only a stored ready suggestion and clears the query", () => {
      mockedUseReferenceGameSearch.mockImplementation(
         (sessionEpoch, query) => {
            if (sessionEpoch === null || query === "") {
               return idleResult;
            }

            return {
               status: "ready",
               items: [suggestions[0]],
               error: null,
            };
         }
      );
      const onSelect = vi.fn();
      const { input } = renderAutocomplete({ onSelect });

      fireEvent.change(input, {
         target: { value: "ready" },
      });
      expect(onSelect).not.toHaveBeenCalled();

      fireEvent.click(
         screen.getByRole("option", { name: /Ready Game.*Ready/i })
      );

      expect(onSelect).toHaveBeenCalledOnce();
      expect(onSelect).toHaveBeenCalledWith(suggestions[0]);
      expect(input).toHaveValue("");
      expect(
         screen.queryByRole("option", { name: /Ready Game.*Ready/i })
      ).not.toBeInTheDocument();
   });

   it("exposes the listbox relationship only while results are visible", () => {
      mockedUseReferenceGameSearch.mockImplementation(
         (_sessionEpoch, query) => (
            query === ""
               ? idleResult
               : {
                  status: "ready",
                  items: suggestions,
                  error: null,
               }
         )
      );
      const { input } = renderAutocomplete();

      expect(input).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

      fireEvent.change(input, {
         target: { value: "game" },
      });

      const listbox = screen.getByRole("listbox");
      expect(input).toHaveAttribute("aria-expanded", "true");
      expect(input).toHaveAttribute(
         "aria-controls",
         listbox.getAttribute("id")
      );
      expect(input).toHaveAttribute("aria-autocomplete", "list");
   });

   it("moves through selectable options without wrapping", () => {
      mockedUseReferenceGameSearch.mockReturnValue({
         status: "ready",
         items: suggestions,
         error: null,
      });
      const { input } = renderAutocomplete({
         selectedSteamAppIds: [500],
      });
      fireEvent.change(input, {
         target: { value: "game" },
      });

      const firstOption = screen.getByRole("option", {
         name: /^Ready Game.*Ready/i,
      });
      const lastOption = screen.getByRole("option", {
         name: /^Another Ready Game.*Ready/i,
      });

      fireEvent.keyDown(input, { key: "ArrowDown" });
      expect(input).toHaveAttribute(
         "aria-activedescendant",
         firstOption.getAttribute("id")
      );

      fireEvent.keyDown(input, { key: "ArrowDown" });
      expect(input).toHaveAttribute(
         "aria-activedescendant",
         lastOption.getAttribute("id")
      );

      fireEvent.keyDown(input, { key: "ArrowDown" });
      expect(input).toHaveAttribute(
         "aria-activedescendant",
         lastOption.getAttribute("id")
      );

      fireEvent.keyDown(input, { key: "ArrowUp" });
      expect(input).toHaveAttribute(
         "aria-activedescendant",
         firstOption.getAttribute("id")
      );

      fireEvent.keyDown(input, { key: "ArrowUp" });
      expect(input).toHaveAttribute(
         "aria-activedescendant",
         firstOption.getAttribute("id")
      );
   });

   it("supports Home and End and selects only the active option", () => {
      mockedUseReferenceGameSearch.mockImplementation(
         (_sessionEpoch, query) => (
            query === ""
               ? idleResult
               : {
                  status: "ready",
                  items: suggestions,
                  error: null,
               }
         )
      );
      const onSelect = vi.fn();
      const { input } = renderAutocomplete({
         selectedSteamAppIds: [500],
         onSelect,
      });
      fireEvent.change(input, {
         target: { value: "game" },
      });

      fireEvent.keyDown(input, { key: "Enter" });
      expect(onSelect).not.toHaveBeenCalled();

      fireEvent.keyDown(input, { key: "End" });
      fireEvent.keyDown(input, { key: "Enter" });

      expect(onSelect).toHaveBeenCalledWith(suggestions[5]);
      expect(input).toHaveValue("");

      fireEvent.change(input, {
         target: { value: "game" },
      });
      fireEvent.keyDown(input, { key: "Home" });
      fireEvent.keyDown(input, { key: "Enter" });

      expect(onSelect).toHaveBeenLastCalledWith(suggestions[0]);
   });

   it("clears with Escape and never selects on Tab", () => {
      mockedUseReferenceGameSearch.mockImplementation(
         (_sessionEpoch, query) => (
            query === ""
               ? idleResult
               : {
                  status: "ready",
                  items: suggestions,
                  error: null,
               }
         )
      );
      const onSelect = vi.fn();
      const { input } = renderAutocomplete({ onSelect });
      fireEvent.change(input, {
         target: { value: "game" },
      });
      fireEvent.keyDown(input, { key: "ArrowDown" });

      fireEvent.keyDown(input, { key: "Tab" });
      expect(onSelect).not.toHaveBeenCalled();
      expect(input).toHaveValue("game");

      fireEvent.keyDown(input, { key: "Escape" });
      expect(input).toHaveValue("");
      expect(input).toHaveAttribute("aria-expanded", "false");
      expect(input).not.toHaveAttribute("aria-activedescendant");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
   });

   it("resets the active option when the query changes", () => {
      mockedUseReferenceGameSearch.mockReturnValue({
         status: "ready",
         items: suggestions,
         error: null,
      });
      const { input } = renderAutocomplete();
      fireEvent.change(input, {
         target: { value: "game" },
      });
      fireEvent.keyDown(input, { key: "ArrowDown" });
      expect(input).toHaveAttribute("aria-activedescendant");

      fireEvent.change(input, {
         target: { value: "different" },
      });

      expect(input).not.toHaveAttribute("aria-activedescendant");
   });

   it("resets the active option when the search results change", () => {
      let currentSuggestions = suggestions;
      mockedUseReferenceGameSearch.mockImplementation(() => ({
         status: "ready",
         items: currentSuggestions,
         error: null,
      }));
      const { input, rerender } = renderAutocomplete();
      fireEvent.change(input, {
         target: { value: "game" },
      });
      fireEvent.keyDown(input, { key: "ArrowDown" });
      expect(input).toHaveAttribute("aria-activedescendant");

      currentSuggestions = [suggestions[5]];
      rerender(
         <ReferenceGameAutocomplete
            sessionEpoch={1}
            selectedSteamAppIds={[]}
            onSelect={vi.fn()}
         />
      );

      expect(input).not.toHaveAttribute("aria-activedescendant");
   });

   it("clears the query and active option when the profile changes", () => {
      mockedUseReferenceGameSearch.mockReturnValue({
         status: "ready",
         items: suggestions,
         error: null,
      });
      const { input, rerender } = renderAutocomplete();
      fireEvent.change(input, {
         target: { value: "game" },
      });
      fireEvent.keyDown(input, { key: "ArrowDown" });

      rerender(
         <ReferenceGameAutocomplete
            sessionEpoch={2}
            selectedSteamAppIds={[]}
            onSelect={vi.fn()}
         />
      );

      const resetInput = screen.getByRole("combobox", {
         name: "Find a reference game",
      });
      expect(resetInput).toHaveValue("");
      expect(resetInput).not.toHaveAttribute("aria-activedescendant");
      expect(mockedUseReferenceGameSearch).toHaveBeenLastCalledWith(2, "");
   });

   it("clears the query and active option when the selection limit is reached", () => {
      mockedUseReferenceGameSearch.mockReturnValue({
         status: "ready",
         items: suggestions,
         error: null,
      });
      const { input, rerender } = renderAutocomplete({
         selectedSteamAppIds: [10, 20],
      });
      fireEvent.change(input, {
         target: { value: "game" },
      });
      fireEvent.keyDown(input, { key: "ArrowDown" });

      rerender(
         <ReferenceGameAutocomplete
            sessionEpoch={1}
            selectedSteamAppIds={[10, 20, 30]}
            onSelect={vi.fn()}
         />
      );

      const disabledInput = screen.getByRole("combobox", {
         name: "Find a reference game",
      });
      expect(disabledInput).toBeDisabled();
      expect(disabledInput).toHaveValue("");
      expect(disabledInput).not.toHaveAttribute("aria-activedescendant");
      expect(mockedUseReferenceGameSearch).toHaveBeenLastCalledWith(1, "");
   });
});
