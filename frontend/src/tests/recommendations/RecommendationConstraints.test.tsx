import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RecommendationConstraints from "../../features/recommendations/preferences/RecommendationConstraints";
import type { PreferenceConstraints } from "../../api";

const defaults: PreferenceConstraints = {
   maximum_completion_minutes: null,
   play_status: "either",
};

describe("RecommendationConstraints", () => {
   function openConstraints(): void {
      fireEvent.click(screen.getByText("Narrow your results"));
   }

   it("starts collapsed with a plain-language summary of the current filters", () => {
      render(<RecommendationConstraints value={defaults} onChange={vi.fn()} />);

      const disclosure = screen.getByText("Narrow your results").closest("details");
      expect(disclosure).not.toHaveAttribute("open");
      expect(screen.getByText("Any length · Any game"))
         .toBeInTheDocument();
      expect(screen.queryByRole("spinbutton")).toBeNull();

      openConstraints();
      expect(disclosure).toHaveAttribute("open");
   });

   it("offers readable length presets and play-history choices", () => {
      render(<RecommendationConstraints value={defaults} onChange={vi.fn()} />);
      openConstraints();

      expect(screen.getByRole("button", { name: "Any length" }))
         .toHaveAttribute("aria-pressed", "true");
      for (const label of [
         "Up to 5 hours",
         "Up to 10 hours",
         "Up to 20 hours",
         "Up to 40 hours",
         "Custom",
      ]) {
         expect(screen.getByRole("button", { name: label }))
            .toHaveAttribute("aria-pressed", "false");
      }
      expect(screen.getByRole("button", { name: "Either" }))
         .toHaveAttribute("aria-pressed", "true");
   });

   it("converts preset and custom hours to integer minutes", () => {
      const onChange = vi.fn();
      const { rerender } = render(
         <RecommendationConstraints value={defaults} onChange={onChange} />
      );
      openConstraints();

      fireEvent.click(screen.getByRole("button", { name: "Up to 10 hours" }));
      expect(onChange).toHaveBeenCalledWith({
         ...defaults,
         maximum_completion_minutes: 600,
      });

      rerender(
         <RecommendationConstraints
            value={{ ...defaults, maximum_completion_minutes: 600 }}
            onChange={onChange}
         />
      );
      fireEvent.click(screen.getByRole("button", { name: "Custom" }));
      const completion = screen.getByRole("spinbutton", {
         name: "Custom maximum in hours",
      });
      expect(completion).toHaveValue(10);
      expect(completion).toHaveAttribute("min", "0.5");
      expect(completion).toHaveAttribute("max", "1000");
      fireEvent.change(completion, { target: { value: "2.5" } });
      expect(onChange).toHaveBeenLastCalledWith({
         ...defaults,
         maximum_completion_minutes: 150,
      });
   });

   it.each([
      "unplayed",
      "previously_played",
      "either",
   ] as const)("emits the %s play status", (playStatus) => {
      const label = {
         unplayed: "Not started",
         previously_played: "Played before",
         either: "Either",
      }[playStatus];
      const onChange = vi.fn();
      const initialValue: PreferenceConstraints = {
         ...defaults,
         play_status: playStatus === "either" ? "unplayed" : "either",
      };
      render(
         <RecommendationConstraints value={initialValue} onChange={onChange} />
      );
      openConstraints();
      fireEvent.click(screen.getByRole("button", { name: label }));
      expect(onChange).toHaveBeenCalledWith({
         ...initialValue,
         play_status: playStatus,
      });
   });

   it("summarizes custom values and warns when unknown-length games are excluded", () => {
      render(
         <RecommendationConstraints
            value={{
               maximum_completion_minutes: 1800,
               play_status: "unplayed",
            }}
            onChange={vi.fn()}
         />
      );

      expect(screen.getByText("Up to 30 hours · Not started"))
         .toBeInTheDocument();
      openConstraints();
      expect(screen.getByRole("button", { name: "Custom" }))
         .toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("spinbutton", {
         name: "Custom maximum in hours",
      })).toHaveValue(30);
      expect(screen.getByText(
         "Games without a known completion time won’t be included when a limit is set."
      )).toBeInTheDocument();
   });

   it("clears both active constraints together", () => {
      const onChange = vi.fn();
      render(
         <RecommendationConstraints
            value={{
               maximum_completion_minutes: 1200,
               play_status: "previously_played",
            }}
            onChange={onChange}
         />
      );
      openConstraints();

      fireEvent.click(screen.getByRole("button", { name: "Clear constraints" }));

      expect(onChange).toHaveBeenCalledWith(defaults);
   });
});
