import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const secondSelectedReference: SelectedReference = {
   details: {
      steam_app_id: 200,
      name: "Second Game",
      cover_url: null,
      metadata_status: "ready",
      facets: {
         genres: [{ id: 12, name: "Action" }],
         themes: [{ id: 22, name: "Science fiction" }],
         game_modes: [{ id: 32, name: "Multiplayer" }],
      },
   },
   selectedFacets: {
      genres: [{ id: 12, name: "Action" }],
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
      failedSuggestion: null,
      addReference: vi.fn().mockResolvedValue(true),
      retryReference: vi.fn().mockResolvedValue(true),
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
      expect(screen.queryByText(/step 2 of 3/i)).not.toBeInTheDocument();
      expect(screen.getByText(
         "Choose 1 to 3 games you own. For each game, select at least one trait you want Ludex to match."
      )).toBeInTheDocument();
   });

   it("marks the recommendations view so its outer divider can be removed", () => {
      mockedUseReferenceSelection.mockReturnValue(selectionResult());

      const { container } = render(
         <ReferenceSelectionSection
            sessionEpoch={7}
            activeView="recommendations"
         />
      );

      expect(container.querySelector(".reference-selection")).toHaveClass(
         "reference-selection--recommendations"
      );
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

   it("opens only one reference preference editor while preserving every summary", () => {
      mockedUseReferenceSelection.mockReturnValue(selectionResult({
         references: [selectedReference, secondSelectedReference],
      }));

      render(<ReferenceSelectionSection sessionEpoch={7} />);

      expect(screen.getByRole("article", { name: "First Game" }))
         .toBeInTheDocument();
      expect(screen.getByRole("article", { name: "Second Game" }))
         .toBeInTheDocument();
      expect(screen.getByRole("button", {
         name: "Edit preferences for First Game",
      })).toHaveAttribute("aria-expanded", "false");
      expect(screen.getByRole("button", {
         name: "Hide preferences for Second Game",
      })).toHaveAttribute("aria-expanded", "true");
      expect(screen.queryByRole("button", { name: "Role-playing" }))
         .not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Action" }))
         .toHaveAttribute("aria-pressed", "true");

      fireEvent.click(screen.getByRole("button", {
         name: "Edit preferences for First Game",
      }));
      expect(screen.getByRole("button", { name: "Role-playing" }))
         .toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Action" }))
         .not.toBeInTheDocument();
   });

   it("opens a successfully added reference and moves to a remaining one after removal", async () => {
      const selection = selectionResult({ references: [] });
      mockedUseReferenceSelection.mockReturnValue(selection);
      const { rerender } = render(<ReferenceSelectionSection sessionEpoch={7} />);

      fireEvent.click(screen.getByRole("button", {
         name: "Add reference for profile 7 with selected",
      }));
      await waitFor(() => expect(selection.addReference).toHaveBeenCalledOnce());
      mockedUseReferenceSelection.mockReturnValue(selectionResult({
         references: [selectedReference],
      }));
      rerender(<ReferenceSelectionSection sessionEpoch={7} />);
      expect(screen.getByRole("button", {
         name: "Hide preferences for First Game",
      })).toHaveAttribute("aria-expanded", "true");

      mockedUseReferenceSelection.mockReturnValue(selectionResult({
         references: [selectedReference, secondSelectedReference],
      }));
      rerender(<ReferenceSelectionSection sessionEpoch={7} />);
      fireEvent.click(screen.getByRole("button", { name: "Remove First Game" }));
      mockedUseReferenceSelection.mockReturnValue(selectionResult({
         references: [secondSelectedReference],
      }));
      rerender(<ReferenceSelectionSection sessionEpoch={7} />);
      expect(screen.getByRole("button", {
         name: "Hide preferences for Second Game",
      })).toHaveAttribute("aria-expanded", "true");
   });

   it("shows pending detail loading and the latest selection error", () => {
      const retryReference = vi.fn().mockResolvedValue(true);
      mockedUseReferenceSelection.mockReturnValue(
         selectionResult({
            references: [selectedReference],
            pendingSteamAppId: 100,
            error: "Reference details are unavailable.",
            failedSuggestion: suggestion,
            retryReference,
         })
      );

      render(<ReferenceSelectionSection sessionEpoch={7} />);

      expect(screen.getByText(
         "Loading reference game details…"
      )).toHaveAttribute("role", "status");
      expect(screen.getByRole("alert")).toHaveTextContent(
         "Reference details are unavailable."
      );
      expect(screen.getByText("1 of 3 reference games selected")).toBeInTheDocument();
      expect(screen.getByRole("article", { name: "First Game" }))
         .toBeInTheDocument();
      fireEvent.click(
         screen.getByRole("button", { name: "Try loading First Game again" })
      );
      expect(retryReference).toHaveBeenCalledOnce();
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

   it("keeps controlled constraints user-facing without exposing JSON", () => {
      mockedUseReferenceSelection.mockReturnValue(selectionResult());
      const { container } = render(<ReferenceSelectionSection sessionEpoch={7} />);

      fireEvent.click(screen.getByText("Optional constraints"));
      expect(screen.getByRole("radio", { name: "Either" })).toBeChecked();
      fireEvent.click(screen.getByRole("radio", { name: "Unplayed" }));
      expect(screen.getByRole("radio", { name: "Unplayed" })).toBeChecked();
      expect(container.querySelector("pre")).toBeNull();
   });

   it("resets recommendation constraints when the profile changes", () => {
      mockedUseReferenceSelection.mockReturnValue(selectionResult());
      const { rerender } = render(<ReferenceSelectionSection sessionEpoch={7} />);
      fireEvent.click(screen.getByText("Optional constraints"));
      fireEvent.click(
         screen.getByRole("radio", { name: "Previously played" })
      );
      expect(
         screen.getByRole("radio", { name: "Previously played" })
      ).toBeChecked();

      rerender(<ReferenceSelectionSection sessionEpoch={8} />);
      fireEvent.click(screen.getByText("Optional constraints"));
      expect(screen.getByRole("radio", { name: "Either" })).toBeChecked();
   });
});
