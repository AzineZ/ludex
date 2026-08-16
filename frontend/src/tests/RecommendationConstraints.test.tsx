import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RecommendationConstraints from "../features/recommendations/RecommendationConstraints";
import type { PreferenceConstraints } from "../api";

const defaults: PreferenceConstraints = {
   maximum_completion_minutes: null,
   play_status: "either",
};

describe("RecommendationConstraints", () => {
   it("renders an optional bounded completion time and the current play status", () => {
      render(<RecommendationConstraints value={defaults} onChange={vi.fn()} />);
      const completion = screen.getByRole("spinbutton", {
         name: "Maximum completion time in minutes",
      });
      expect(completion).toHaveValue(null);
      expect(completion).toHaveAttribute("min", "30");
      expect(completion).toHaveAttribute("max", "60000");
      expect(screen.getByRole("radio", { name: "Either" })).toBeChecked();
   });

   it("emits integer minutes and supports clearing the optional maximum", () => {
      const onChange = vi.fn();
      const { rerender } = render(
         <RecommendationConstraints value={defaults} onChange={onChange} />
      );
      const completion = screen.getByRole("spinbutton", {
         name: "Maximum completion time in minutes",
      });
      fireEvent.change(completion, { target: { value: "1800" } });
      expect(onChange).toHaveBeenCalledWith({
         ...defaults,
         maximum_completion_minutes: 1800,
      });

      rerender(
         <RecommendationConstraints
            value={{ ...defaults, maximum_completion_minutes: 1800 }}
            onChange={onChange}
         />
      );
      fireEvent.change(completion, { target: { value: "" } });
      expect(onChange).toHaveBeenLastCalledWith(defaults);
   });

   it.each([
      ["unplayed", "Unplayed"],
      ["previously_played", "Previously played"],
      ["either", "Either"],
   ] as const)("emits the %s play status", (playStatus, label) => {
      const onChange = vi.fn();
      const initialValue: PreferenceConstraints = {
         ...defaults,
         play_status: playStatus === "either" ? "unplayed" : "either",
      };
      render(
         <RecommendationConstraints value={initialValue} onChange={onChange} />
      );
      fireEvent.click(screen.getByRole("radio", { name: label }));
      expect(onChange).toHaveBeenCalledWith({
         ...initialValue,
         play_status: playStatus,
      });
   });
});
