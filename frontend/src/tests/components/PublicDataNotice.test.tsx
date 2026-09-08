import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../../App";
import PublicDataNotice from "../../components/PublicDataNotice";

vi.mock("../../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../../api")>();
   return {
      ...actual,
      getCurrentSessionProfile: vi.fn(() => new Promise(() => {})),
      getHealth: vi.fn(() => new Promise(() => {})),
   };
});

describe("PublicDataNotice", () => {
   afterEach(() => {
      cleanup();
      window.history.replaceState({}, "", "/");
   });

   it("discloses data use, retention, and provider boundaries", () => {
      render(<PublicDataNotice />);

      const notice = screen.getByRole("region", {
         name: "Privacy & Data Use",
      });
      expect(notice).toHaveTextContent("fixed seven days");
      expect(notice).toHaveTextContent("at least 30 days");
      expect(notice).toHaveTextContent("approximately 58 days");
      expect(notice).toHaveTextContent("United States");
      expect(notice).toHaveTextContent("not persisted or application-logged");
      expect(notice).toHaveTextContent("not proof of account ownership");
      expect(notice).toHaveTextContent("as-is and as-available");
      expect(notice).toHaveTextContent("not affiliated with or endorsed");
      expect(notice).toHaveTextContent("do not contact those providers");
      expect(within(notice).queryByRole("link")).not.toBeInTheDocument();
   });

   it("keeps the notice off the application page but reachable from its footer", () => {
      window.history.replaceState({}, "", "/");
      render(<App />);

      expect(
         screen.queryByRole("region", { name: "Privacy & Data Use" })
      ).not.toBeInTheDocument();
      const footer = screen.getByRole("contentinfo", {
         name: "Site information",
      });
      expect(
         within(footer).getByRole("link", { name: "Privacy & Data Use" })
      ).toHaveAttribute("href", "/privacy");
      expect(
         within(footer).getByRole("link", { name: "Steam Web API" })
      ).toHaveAttribute("href", "https://steamcommunity.com/dev/apiterms");
      expect(
         within(footer).getByRole("link", { name: "Game Metadata From IGDB" })
      ).toHaveAttribute("href", "https://www.igdb.com/");
   });

   it("renders the complete notice on the dedicated privacy page", () => {
      window.history.replaceState({}, "", "/privacy");
      render(<App />);

      expect(
         screen.getByRole("region", { name: "Privacy & Data Use" })
      ).toBeInTheDocument();
      expect(
         screen.getByRole("link", { name: "← Back to Ludex" })
      ).toHaveAttribute("href", "/");
   });
});
