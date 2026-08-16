import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ReferenceGameCard from "../features/recommendations/ReferenceGameCard";
import type { SelectedReference } from "../features/recommendations/useReferenceSelection";

const reference: SelectedReference = {
   details: {
      steam_app_id: 100,
      name: "First Game",
      cover_url: "https://images.example/first-game.jpg",
      metadata_status: "ready",
      facets: {
         genres: [
            { id: 11, name: "Role-playing" },
            { id: 12, name: "Adventure" },
         ],
         themes: [{ id: 21, name: "Fantasy" }],
         game_modes: [
            { id: 31, name: "Single player" },
            { id: 32, name: "Multiplayer" },
         ],
      },
   },
   selectedFacets: {
      genres: [{ id: 11, name: "Role-playing" }],
      themes: [],
      keywords: [],
      gameModes: [{ id: 32, name: "Multiplayer" }],
   },
};

function renderCard(
   selectedReference: SelectedReference = reference
) {
   const onToggleFacet = vi.fn();
   const onRemove = vi.fn();

   render(
      <ReferenceGameCard
         reference={selectedReference}
         onToggleFacet={onToggleFacet}
         onRemove={onRemove}
      />
   );

   return {
      onToggleFacet,
      onRemove,
   };
}

describe("ReferenceGameCard", () => {
   it("renders authoritative identity, cover, and direct facet groups", () => {
      renderCard();

      expect(
         screen.getByRole("heading", { name: "First Game" })
      ).toBeInTheDocument();
      expect(screen.getByRole("img", { name: "First Game cover" })).toHaveAttribute(
         "src",
         "https://images.example/first-game.jpg"
      );

      expect(
         within(screen.getByRole("group", { name: "Genres" })).getAllByRole(
            "button"
         )
      ).toHaveLength(2);
      expect(
         within(screen.getByRole("group", { name: "Themes" })).getByRole(
            "button",
            { name: "Fantasy" }
         )
      ).toBeInTheDocument();
      expect(
         within(screen.getByRole("group", { name: "Game modes" })).getAllByRole(
            "button"
         )
      ).toHaveLength(2);
   });

   it("marks only selected direct facets as pressed", () => {
      renderCard();

      expect(screen.getByRole("button", { name: "Role-playing" })).toHaveAttribute(
         "aria-pressed",
         "true"
      );
      expect(screen.getByRole("button", { name: "Adventure" })).toHaveAttribute(
         "aria-pressed",
         "false"
      );
      expect(screen.getByRole("button", { name: "Fantasy" })).toHaveAttribute(
         "aria-pressed",
         "false"
      );
      expect(screen.getByRole("button", { name: "Multiplayer" })).toHaveAttribute(
         "aria-pressed",
         "true"
      );
   });

   it("reports the exact facet group and authoritative option when toggled", () => {
      const { onToggleFacet } = renderCard();

      fireEvent.click(screen.getByRole("button", { name: "Adventure" }));
      fireEvent.click(screen.getByRole("button", { name: "Fantasy" }));
      fireEvent.click(screen.getByRole("button", { name: "Single player" }));

      expect(onToggleFacet).toHaveBeenNthCalledWith(
         1,
         "genres",
         reference.details.facets.genres[1]
      );
      expect(onToggleFacet).toHaveBeenNthCalledWith(
         2,
         "themes",
         reference.details.facets.themes[0]
      );
      expect(onToggleFacet).toHaveBeenNthCalledWith(
         3,
         "gameModes",
         reference.details.facets.game_modes[0]
      );
      expect(reference.selectedFacets.genres).toEqual([
         { id: 11, name: "Role-playing" },
      ]);
   });

   it("reports removal for the displayed reference", () => {
      const { onRemove } = renderCard();

      fireEvent.click(
         screen.getByRole("button", { name: "Remove First Game" })
      );

      expect(onRemove).toHaveBeenCalledOnce();
      expect(onRemove).toHaveBeenCalledWith(100);
   });

   it("renders honest fallbacks for a missing cover and empty facet groups", () => {
      renderCard({
         details: {
            ...reference.details,
            cover_url: null,
            facets: {
               genres: [],
               themes: [],
               game_modes: [],
            },
         },
         selectedFacets: {
            genres: [],
            themes: [],
            keywords: [],
            gameModes: [],
         },
      });

      expect(screen.queryByRole("img")).not.toBeInTheDocument();
      expect(screen.getByText("Cover unavailable")).toBeInTheDocument();
      expect(screen.getByText("No genre metadata available.")).toBeInTheDocument();
      expect(screen.getByText("No theme metadata available.")).toBeInTheDocument();
      expect(
         screen.getByText("No game mode metadata available.")
      ).toBeInTheDocument();
   });

   it("renders an optional reference-scoped keyword control", () => {
      render(
         <ReferenceGameCard
            reference={reference}
            onToggleFacet={vi.fn()}
            onRemove={vi.fn()}
            keywordControl={<button type="button">Choose keywords</button>}
         />
      );

      expect(
         screen.getByRole("button", { name: "Choose keywords" })
      ).toBeInTheDocument();
   });
});
