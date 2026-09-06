import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import SteamSessionForm from "../../features/session/SteamSessionForm";

describe("SteamSessionForm", () => {
   it("explains accepted Steam identifiers through the input description", () => {
      render(
         <SteamSessionForm error={null} isStarting={false} onStart={vi.fn()} />
      );

      const input = screen.getByRole("textbox", {
         name: "Steam ID or profile URL",
      });
      expect(input).toHaveAccessibleDescription(
         "Paste a 17-digit Steam ID or Steam Community profile URL."
      );
   });

   it("marks the form busy and disables duplicate input while loading", () => {
      render(
         <SteamSessionForm error={null} isStarting onStart={vi.fn()} />
      );

      expect(screen.getByRole("form", { name: "Steam library access" }))
         .toHaveAttribute("aria-busy", "true");
      expect(
         screen.getByRole("textbox", { name: "Steam ID or profile URL" })
      ).toBeDisabled();
      expect(
         screen.getByRole("button", { name: "Loading Steam profile…" })
      ).toBeDisabled();
   });

   it("keeps a failed identifier visible and associates its error with the input", () => {
      render(
         <SteamSessionForm
            error="This Steam library is private or unavailable."
            isStarting={false}
            onStart={vi.fn()}
         />
      );

      const input = screen.getByRole("textbox", {
         name: "Steam ID or profile URL",
      });
      fireEvent.change(input, { target: { value: "private-profile" } });

      expect(input).toHaveValue("private-profile");
      expect(input).toHaveAccessibleDescription(
         "Paste a 17-digit Steam ID or Steam Community profile URL. " +
            "This Steam library is private or unavailable."
      );
      expect(screen.getByRole("alert")).toHaveClass("app__session-form-error");
   });
});
