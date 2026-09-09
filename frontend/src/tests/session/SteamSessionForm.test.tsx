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
         "Paste a 17-digit Steam ID or Steam Community profile URL. " +
            "Prefer not to use your own Steam ID? Try the Ludex sample " +
            "library by pasting this steam ID: 76561198342733684"
      );
      expect(screen.getByText("76561198342733684").tagName).toBe("CODE");
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
         screen.getByRole("checkbox", { name: /I confirm I am authorized/ })
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
            "Prefer not to use your own Steam ID? Try the Ludex sample " +
            "library by pasting this steam ID: 76561198342733684 " +
            "This Steam library is private or unavailable."
      );
      expect(screen.getByRole("alert")).toHaveClass("app__session-form-error");
   });

   it("requires authorized-use acknowledgment before starting a session", async () => {
      const onStart = vi.fn().mockResolvedValue(true);
      render(
         <SteamSessionForm
            error={null}
            isStarting={false}
            onStart={onStart}
         />
      );

      const input = screen.getByRole("textbox", {
         name: "Steam ID or profile URL",
      });
      const acknowledgment = screen.getByRole("checkbox", {
         name: /I confirm I am authorized/,
      });
      const submit = screen.getByRole("button", {
         name: "Continue with Steam",
      });

      fireEvent.change(input, { target: { value: "example-profile" } });
      expect(submit).toBeDisabled();
      expect(acknowledgment).toBeRequired();
      expect(
         screen.getByRole("link", { name: "privacy and data notice" })
      ).toHaveAttribute("href", "/privacy");

      fireEvent.click(acknowledgment);
      expect(submit).toBeEnabled();
      fireEvent.click(submit);

      expect(onStart).toHaveBeenCalledWith("example-profile", true);
   });
});
