import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OwnedGameSuggestionResponse } from "../api";
import ReferenceSelectionSection from "../features/recommendations/ReferenceSelectionSection";
import {
   useReferenceSelection,
   type ReferenceSelectionResult,
   type SelectedReference,
} from "../features/recommendations/useReferenceSelection";

const suggestion: OwnedGameSuggestionResponse = {
   steam_app_id: 100,
   name: "First Game",
   cover_url: null,
   metadata_status: "ready",
};

const selectedReference: SelectedReference = {
   details: {
      ...suggestion,
      facets: {
         genres: [{ id: 11, name: "Role-playing" }],
         themes: [{ id: 21, name: "Fantasy" }],
         game_modes: [{ id: 31, name: "Single player" }],
      },
   },
   selectedFacets: {
      genres: [],
      themes: [],
      keywords: [],
      gameModes: [],
   },
};

vi.mock(
   "../features/recommendations/useReferenceSelection",
   async (importOriginal) => {
      const actual = await importOriginal<
         typeof import("../features/recommendations/useReferenceSelection")
      >();

      return {
         ...actual,
         useReferenceSelection: vi.fn(),
      };
   }
);

vi.mock(
   "../features/recommendations/ReferenceGameAutocomplete",
   () => ({
      default: ({
         sessionEpoch,
         selectedSteamAppIds,
         onSelect,
      }: {
         sessionEpoch: number | null;
         selectedSteamAppIds: number[];
         onSelect: (suggestion: OwnedGameSuggestionResponse) => void;
      }) => (
         <button
            type="button"
            onClick={() => onSelect(suggestion)}
         >
            Add reference for profile {sessionEpoch ?? "none"} with selected{
               ` ${selectedSteamAppIds.join(",")}`
            }
         </button>
      ),
   })
);

const mockedUseReferenceSelection = vi.mocked(useReferenceSelection);

function selectionResult(
   overrides: Partial<ReferenceSelectionResult> = {}
): ReferenceSelectionResult {
   return {
      references: [],
      pendingSteamAppId: null,
      error: null,
      addReference: vi.fn().mockResolvedValue(true),
      toggleDirectFacet: vi.fn().mockReturnValue(true),
      toggleKeyword: vi.fn().mockReturnValue(true),
      removeReference: vi.fn(),
      ...overrides,
   };
}

describe("ReferenceSelectionSection", () => {
   beforeEach(() => {
      mockedUseReferenceSelection.mockReset();
   });

   it("connects the session epoch and selected IDs to reference addition", () => {
      const selection = selectionResult({
         references: [selectedReference],
      });
      mockedUseReferenceSelection.mockReturnValue(selection);

      render(<ReferenceSelectionSection sessionEpoch={7} />);

      expect(mockedUseReferenceSelection).toHaveBeenCalledWith(7);
      fireEvent.click(
         screen.getByRole("button", {
            name: "Add reference for profile 7 with selected 100",
         })
      );
      expect(selection.addReference).toHaveBeenCalledWith(suggestion);
      expect(screen.getByText("1 of 3 reference games selected")).toBeInTheDocument();
   });

   it("renders selected cards and connects facet toggling and removal", () => {
      const selection = selectionResult({
         references: [selectedReference],
      });
      mockedUseReferenceSelection.mockReturnValue(selection);

      render(<ReferenceSelectionSection sessionEpoch={7} />);

      fireEvent.click(screen.getByRole("button", { name: "Role-playing" }));
      expect(selection.toggleDirectFacet).toHaveBeenCalledWith(
         100,
         "genres",
         { id: 11, name: "Role-playing" }
      );

      fireEvent.click(screen.getByRole("button", { name: "Remove First Game" }));
      expect(selection.removeReference).toHaveBeenCalledWith(100);
   });

   it("shows pending detail loading and the latest selection error", () => {
      mockedUseReferenceSelection.mockReturnValue(
         selectionResult({
            pendingSteamAppId: 100,
            error: "Reference details are unavailable.",
         })
      );

      render(<ReferenceSelectionSection sessionEpoch={7} />);

      expect(screen.getByRole("status")).toHaveTextContent(
         "Loading reference game details…"
      );
      expect(screen.getByRole("alert")).toHaveTextContent(
         "Reference details are unavailable."
      );
      expect(screen.getByText("0 of 3 reference games selected")).toBeInTheDocument();
   });

   it("connects reference-scoped keyword removal to selection state", () => {
      const keyword = { id: 41, name: "Exploration" };
      const selection = selectionResult({
         references: [
            {
               ...selectedReference,
               selectedFacets: {
                  ...selectedReference.selectedFacets,
                  keywords: [keyword],
               },
            },
         ],
      });
      mockedUseReferenceSelection.mockReturnValue(selection);

      render(<ReferenceSelectionSection sessionEpoch={7} />);
      fireEvent.click(
         screen.getByRole("button", { name: "Remove keyword Exploration" })
      );

      expect(selection.toggleKeyword).toHaveBeenCalledWith(100, keyword);
   });

   it("serializes controlled constraints into the inspectable draft", () => {
      mockedUseReferenceSelection.mockReturnValue(selectionResult());
      render(<ReferenceSelectionSection sessionEpoch={7} />);

      const preview = screen.getByTestId("preference-draft");
      expect(preview).toHaveTextContent('"play_status": "either"');
      fireEvent.click(screen.getByRole("radio", { name: "Unplayed" }));
      expect(preview).toHaveTextContent('"play_status": "unplayed"');
   });

   it("resets recommendation constraints when the profile changes", () => {
      mockedUseReferenceSelection.mockReturnValue(selectionResult());
      const { rerender } = render(<ReferenceSelectionSection sessionEpoch={7} />);
      fireEvent.click(
         screen.getByRole("radio", { name: "Previously played" })
      );
      expect(
         screen.getByRole("radio", { name: "Previously played" })
      ).toBeChecked();

      rerender(<ReferenceSelectionSection sessionEpoch={8} />);
      expect(screen.getByRole("radio", { name: "Either" })).toBeChecked();
   });
});
