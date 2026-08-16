import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReferenceKeywordAutocomplete from "../features/recommendations/ReferenceKeywordAutocomplete";
import {
   useReferenceKeywordSearch,
   type ReferenceKeywordSearchResult,
} from "../features/recommendations/useReferenceKeywordSearch";

vi.mock(
   "../features/recommendations/useReferenceKeywordSearch",
   async (importOriginal) => {
      const actual = await importOriginal<
         typeof import("../features/recommendations/useReferenceKeywordSearch")
      >();
      return { ...actual, useReferenceKeywordSearch: vi.fn() };
   }
);

const idle: ReferenceKeywordSearchResult = {
   status: "idle",
   items: [],
   error: null,
};
const items = [
   { id: 41, name: "Exploration" },
   { id: 42, name: "Choices" },
];
const mockedSearch = vi.mocked(useReferenceKeywordSearch);

describe("ReferenceKeywordAutocomplete", () => {
   beforeEach(() => {
      mockedSearch.mockReset();
      mockedSearch.mockReturnValue(idle);
   });

   it("renders selected keywords and toggles one off", () => {
      const onToggle = vi.fn();
      render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={[items[0]]}
            onToggle={onToggle}
         />
      );
      fireEvent.click(
         screen.getByRole("button", { name: "Remove keyword Exploration" })
      );
      expect(onToggle).toHaveBeenCalledWith(items[0]);
   });

   it("disables searching at three keywords while keeping removal available", () => {
      const selected = [...items, { id: 43, name: "Crafting" }];
      render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={selected}
            onToggle={vi.fn()}
         />
      );
      expect(screen.getByRole("combobox", { name: "Find keywords" })).toBeDisabled();
      expect(screen.getByText("3 of 3 keywords selected")).toBeInTheDocument();
      expect(
         screen.getByRole("button", { name: "Remove keyword Exploration" })
      ).toBeEnabled();
   });

   it.each([
      ["waiting", "Searching keywords…"],
      ["loading", "Searching keywords…"],
      ["ready", "No keywords match that search."],
      ["unavailable", "Keyword search failed."],
   ] as const)("shows the %s state", (status, message) => {
      mockedSearch.mockReturnValue({
         status,
         items: [],
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
      fireEvent.change(screen.getByRole("combobox", { name: "Find keywords" }), {
         target: { value: "story" },
      });
      expect(screen.getByText(message)).toBeInTheDocument();
   });

   it("selects an exact suggestion by mouse and clears the query", () => {
      mockedSearch.mockImplementation((_profileId, _steamAppId, query) =>
         query === "" ? idle : { status: "ready", items, error: null }
      );
      const onToggle = vi.fn();
      render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={[]}
            onToggle={onToggle}
         />
      );
      const input = screen.getByRole("combobox", { name: "Find keywords" });
      fireEvent.change(input, { target: { value: "explore" } });
      fireEvent.click(screen.getByRole("option", { name: "Exploration" }));
      expect(onToggle).toHaveBeenCalledWith(items[0]);
      expect(input).toHaveValue("");
   });

   it("skips selected suggestions and supports keyboard confirmation", () => {
      mockedSearch.mockReturnValue({ status: "ready", items, error: null });
      const onToggle = vi.fn();
      render(
         <ReferenceKeywordAutocomplete
            profileId={1}
            steamAppId={100}
            selectedKeywords={[items[0]]}
            onToggle={onToggle}
         />
      );
      const input = screen.getByRole("combobox", { name: "Find keywords" });
      fireEvent.change(input, { target: { value: "choice" } });
      expect(screen.queryByRole("option", { name: "Exploration" })).not.toBeInTheDocument();
      fireEvent.keyDown(input, { key: "ArrowDown" });
      fireEvent.keyDown(input, { key: "Enter" });
      expect(onToggle).toHaveBeenCalledWith(items[1]);
      expect(input).toHaveValue("");
   });
});
