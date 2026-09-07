import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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
   it("discloses data use, retention, deletion, and provider boundaries", () => {
      render(<PublicDataNotice />);

      const notice = screen.getByRole("region", {
         name: "Privacy & data use",
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
      expect(
         within(notice).getByRole("link", { name: "Game metadata from IGDB" })
      ).toHaveAttribute("href", "https://www.igdb.com/");
      expect(
         within(notice).getByRole("link", { name: "Ludex repository" })
      ).toHaveAttribute("href", "https://github.com/AzineZ/ludex/issues/new");
   });

   it("keeps the privacy notice reachable from the site footer", () => {
      render(<App />);

      const footer = screen.getByRole("contentinfo", {
         name: "Site information",
      });
      expect(
         within(footer).getByRole("link", { name: "Privacy & data use" })
      ).toHaveAttribute("href", "#privacy-data");
   });
});
