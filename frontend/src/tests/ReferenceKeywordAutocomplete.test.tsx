import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReferenceKeywordAutocomplete from "../features/recommendations/ReferenceKeywordAutocomplete";
import {
   useReferenceKeywordBrowse,
   type ReferenceKeywordBrowseResult,
} from "../features/recommendations/useReferenceKeywordBrowse";

vi.mock(
   "../features/recommendations/useReferenceKeywordBrowse",
   async (importOriginal) => {
      const actual = await importOriginal<
         typeof import("../features/recommendations/useReferenceKeywordBrowse")
      >();
      return { ...actual, useReferenceKeywordBrowse: vi.fn() };
   }
);

const items = [
   { id: 41, name: "Exploration" },
   { id: 42, name: "Choices" },
   { id: 43, name: "Atmospheric" },
   { id: 44, name: "Story rich" },
];
const ready: ReferenceKeywordBrowseResult = {
   status: "ready",
   items,
   truncated: false,
   error: null,
};
const mockedBrowse = vi.mocked(useReferenceKeywordBrowse);

describe("ReferenceKeywordAutocomplete", () => {
   beforeEach(() => {
      mockedBrowse.mockReset();
      mockedBrowse.mockReturnValue(ready);
   });

   it("shows browsable keywords before the user knows what to filter", () => {
      render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={[]}
            onToggle={vi.fn()}
         />
      );

      expect(screen.getByRole("list", { name: "Available keywords" }))
         .toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Select keyword Exploration" }))
         .toBeEnabled();
      expect(screen.getByRole("button", { name: "Select keyword Story rich" }))
         .toBeEnabled();
   });

   it("filters the visible cached list case-insensitively", () => {
      render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={[]}
            onToggle={vi.fn()}
         />
      );

      fireEvent.change(screen.getByRole("searchbox", { name: "Filter keywords" }), {
         target: { value: "STORY" },
      });
      expect(screen.getByRole("button", { name: "Select keyword Story rich" }))
         .toBeInTheDocument();
      expect(screen.queryByText("Exploration")).not.toBeInTheDocument();
   });

   it("selects and removes exact stored keyword options", () => {
      const onToggle = vi.fn();
      const { rerender } = render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={[]}
            onToggle={onToggle}
         />
      );
      fireEvent.click(
         screen.getByRole("button", { name: "Select keyword Exploration" })
      );
      expect(onToggle).toHaveBeenCalledWith(items[0]);

      rerender(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={[items[0]]}
            onToggle={onToggle}
         />
      );
      expect(screen.getByText("1 of 3 keywords selected")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Remove keyword Exploration" }))
         .toHaveAttribute("aria-pressed", "true");
      fireEvent.click(
         screen.getByRole("button", { name: "Remove keyword Exploration" })
      );
      expect(onToggle).toHaveBeenLastCalledWith(items[0]);
   });

   it("keeps browsing and removal available at the three-keyword limit", () => {
      render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={items.slice(0, 3)}
            onToggle={vi.fn()}
         />
      );

      expect(screen.getByRole("searchbox", { name: "Filter keywords" }))
         .toBeEnabled();
      expect(screen.getByRole("button", { name: "Remove keyword Exploration" }))
         .toBeEnabled();
      expect(screen.getByRole("button", { name: "Select keyword Story rich" }))
         .toBeDisabled();
      expect(screen.getByText("Remove one selected keyword to choose another."))
         .toBeInTheDocument();
   });

   it.each([
      ["loading", "Loading keywords…"],
      ["ready", "No cached keywords are available for this game."],
      ["unavailable", "Keyword browse failed."],
   ] as const)("shows the %s state", (status, message) => {
      mockedBrowse.mockReturnValue({
         status,
         items: [],
         truncated: false,
         error: status === "unavailable" ? message : null,
      });
      render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={[]}
            onToggle={vi.fn()}
         />
      );
      expect(screen.getByText(message)).toBeInTheDocument();
   });

   it("shows filtered-empty and bounded-list guidance", () => {
      mockedBrowse.mockReturnValue({ ...ready, truncated: true });
      render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={[]}
            onToggle={vi.fn()}
         />
      );
      expect(screen.getByText("Showing the first 250 cached keywords."))
         .toBeInTheDocument();

      fireEvent.change(screen.getByRole("searchbox", { name: "Filter keywords" }), {
         target: { value: "missing" },
      });
      expect(screen.getByText("No keywords match that filter."))
         .toBeInTheDocument();
   });
});
