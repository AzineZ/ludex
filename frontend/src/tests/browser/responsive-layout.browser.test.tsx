import { render } from "@testing-library/react";
import { page } from "vitest/browser";
import { describe, expect, it, vi } from "vitest";

import type { SessionProfileResponse } from "../../api";
import Hero from "../../components/Hero";
import PublicDataNotice from "../../components/PublicDataNotice";
import ServerStatus from "../../components/ServerStatus";
import SessionGameLibrary from "../../features/session/SessionGameLibrary";
import SteamSessionForm from "../../features/session/SteamSessionForm";
import "../../index.css";
import "../../App.css";
import "../../features/session/session.css";

type Viewport = {
   width: number;
   height: number;
};

const TALL_VIEWPORTS: Viewport[] = [
   { width: 390, height: 844 },
   { width: 768, height: 1024 },
   { width: 1920, height: 1080 },
   { width: 3840, height: 2160 },
];

const NARROW_VIEWPORTS: Viewport[] = [
   { width: 320, height: 568 },
   { width: 390, height: 844 },
   { width: 568, height: 320 },
];

const WIDE_VIEWPORTS: Viewport[] = [
   { width: 1920, height: 1080 },
   { width: 2560, height: 1440 },
   { width: 3440, height: 1440 },
   { width: 3840, height: 2160 },
];

const SHORT_LANDSCAPE_VIEWPORTS: Viewport[] = [
   { width: 568, height: 320 },
   { width: 844, height: 390 },
];

const PUBLIC_PAGE_VIEWPORTS: Viewport[] = [
   { width: 320, height: 568 },
   { width: 390, height: 844 },
   { width: 568, height: 320 },
   { width: 768, height: 1024 },
   { width: 1024, height: 768 },
   { width: 1280, height: 720 },
   { width: 1920, height: 1080 },
   { width: 2560, height: 1440 },
   { width: 3440, height: 1440 },
   { width: 3840, height: 2160 },
];

function viewportName({ width, height }: Viewport): string {
   return `${width}x${height}`;
}

async function setTestViewport({ width, height }: Viewport): Promise<void> {
   await page.viewport(width, height);
   await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
   });
}

function rectanglesOverlap(first: DOMRect, second: DOMRect): boolean {
   return (
      first.left < second.right &&
      first.right > second.left &&
      first.top < second.bottom &&
      first.bottom > second.top
   );
}

function libraryProfile(): SessionProfileResponse {
   return {
      steam_id: "76561198000000001",
      display_name: "Responsive Test Player",
      profile_url: null,
      avatar_url: null,
      created_at: "2026-09-08T12:00:00Z",
      last_synced_at: "2026-09-08T12:00:00Z",
      games: Array.from({ length: 24 }, (_, index) => ({
         steam_app_id: index + 1,
         name: `Game ${index + 1}`,
         icon_url: null,
         cover_url: null,
         playtime_minutes: 60,
         recent_playtime_minutes: null,
         last_played_at: null,
      })),
   };
}

function PublicPageFixture() {
   return (
      <div className="app">
         <ServerStatus connectionState="connected" />
         <main className="app__content">
            <Hero />
            <section className="app__session app__session--access">
               <h2>Connect your Steam library</h2>
               <p>
                  Use a public Steam profile to load your library on this
                  browser.
               </p>
               <SteamSessionForm
                  error={null}
                  isStarting={false}
                  onStart={vi.fn().mockResolvedValue(true)}
               />
            </section>
         </main>
      </div>
   );
}

function PrivacyPageFixture() {
   return (
      <div className="app app--privacy">
         <main className="app__privacy-content">
            <a className="app__privacy-back" href="/">
               ← Back to Ludex
            </a>
            <PublicDataNotice />
         </main>
      </div>
   );
}

function LibraryBackdropFixture() {
   return (
      <div className="app">
         <SessionGameLibrary
            profile={libraryProfile()}
            isRefreshing={false}
            refreshError={null}
            refreshSucceeded={false}
            onRefresh={vi.fn().mockResolvedValue(true)}
         />
      </div>
   );
}

describe("responsive layout contracts", () => {
   it("keeps the public background image layer at least as tall as the viewport", async () => {
      const { container } = render(<PublicPageFixture />);
      const app = container.querySelector<HTMLElement>(".app");
      expect(app).not.toBeNull();

      for (const viewport of TALL_VIEWPORTS) {
         await setTestViewport(viewport);
         const backgroundHeight = Number.parseFloat(
            getComputedStyle(app as HTMLElement, "::before").height
         );

         expect(
            backgroundHeight,
            `background height at ${viewportName(viewport)}`
         ).toBeGreaterThanOrEqual(viewport.height);
      }
   });

   it("uses the approved background artwork for the current orientation", async () => {
      const { container } = render(<PublicPageFixture />);
      const app = container.querySelector<HTMLElement>(".app");
      expect(app).not.toBeNull();

      await setTestViewport({ width: 390, height: 844 });
      expect(getComputedStyle(app as HTMLElement, "::before").backgroundImage)
         .toContain("monitor-cover-portrait");

      await setTestViewport({ width: 844, height: 390 });
      expect(getComputedStyle(app as HTMLElement, "::before").backgroundImage)
         .toContain("monitor-cover-landscape");
   });

   it("keeps the server badge clear of the Ludex logo", async () => {
      const { container } = render(<PublicPageFixture />);
      const logo = container.querySelector<HTMLImageElement>(".app__logo");
      const status = container.querySelector<HTMLElement>(".app__status");
      expect(logo).not.toBeNull();
      expect(status).not.toBeNull();
      await logo?.decode();

      for (const viewport of NARROW_VIEWPORTS) {
         await setTestViewport(viewport);
         expect(
            rectanglesOverlap(
               (logo as HTMLImageElement).getBoundingClientRect(),
               (status as HTMLElement).getBoundingClientRect()
            ),
            `badge/logo overlap at ${viewportName(viewport)}`
         ).toBe(false);
      }
   });

   it("keeps the login page within every supported viewport width", async () => {
      render(<PublicPageFixture />);

      for (const viewport of PUBLIC_PAGE_VIEWPORTS) {
         await setTestViewport(viewport);
         expect(
            document.documentElement.scrollWidth,
            `login page width at ${viewportName(viewport)}`
         ).toBeLessThanOrEqual(viewport.width);
      }
   });

   it("keeps the privacy page within every supported viewport width", async () => {
      render(<PrivacyPageFixture />);

      for (const viewport of PUBLIC_PAGE_VIEWPORTS) {
         await setTestViewport(viewport);
         expect(
            document.documentElement.scrollWidth,
            `privacy page width at ${viewportName(viewport)}`
         ).toBeLessThanOrEqual(viewport.width);
      }
   });

   it("keeps one full duplicate cover group beyond the animation distance", async () => {
      const { container } = render(<LibraryBackdropFixture />);
      const track = container.querySelector<HTMLElement>(".app__library-track");
      const group = track?.querySelector<HTMLElement>(
         ".app__library-track-group"
      );
      expect(track).not.toBeNull();
      expect(group).not.toBeNull();

      for (const viewport of WIDE_VIEWPORTS) {
         await setTestViewport(viewport);
         const remainingTrackWidth =
            (track as HTMLElement).getBoundingClientRect().width -
            (group as HTMLElement).getBoundingClientRect().width;

         expect(
            remainingTrackWidth,
            `remaining track width at ${viewportName(viewport)}`
         ).toBeGreaterThanOrEqual(viewport.width);
      }
   });

   it("keeps cover rows from overlapping on short landscape screens", async () => {
      const { container } = render(<LibraryBackdropFixture />);
      const tracks = Array.from(
         container.querySelectorAll<HTMLElement>(".app__library-track")
      );
      expect(tracks).toHaveLength(3);

      for (const viewport of SHORT_LANDSCAPE_VIEWPORTS) {
         await setTestViewport(viewport);
         const cards = tracks.map((track) =>
            track.querySelector<HTMLElement>(".app__library-card")
         );
         expect(cards.every((card) => card !== null)).toBe(true);

         const firstCard = (cards[0] as HTMLElement).getBoundingClientRect();
         const secondCard = (cards[1] as HTMLElement).getBoundingClientRect();
         const thirdCard = (cards[2] as HTMLElement).getBoundingClientRect();

         expect(
            firstCard.bottom,
            `first/second row overlap at ${viewportName(viewport)}`
         ).toBeLessThanOrEqual(secondCard.top);
         expect(
            secondCard.bottom,
            `second/third row overlap at ${viewportName(viewport)}`
         ).toBeLessThanOrEqual(thirdCard.top);
      }
   });
});
