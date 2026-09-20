import { fireEvent, render, screen } from "@testing-library/react";
import { page } from "vitest/browser";
import { describe, expect, it, vi } from "vitest";

import type { SessionProfileResponse } from "../../api";
import Hero from "../../components/Hero";
import PublicDataNotice from "../../components/PublicDataNotice";
import ServerStatus from "../../components/ServerStatus";
import AssistantWorkspace from "../../features/recommendations/assistant/AssistantWorkspace";
import SessionGameLibrary from "../../features/session/SessionGameLibrary";
import SteamSessionForm from "../../features/session/SteamSessionForm";
import "../../index.css";
import "../../App.css";
import "../../features/session/session.css";
import "../../features/recommendations/recommendations.css";

vi.mock("../../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../../api")>();
   return {
      ...actual,
      getAssistantGenres: vi.fn().mockResolvedValue({
         items: Array.from({ length: 20 }, (_, index) => ({
            igdb_id: index === 0 ? 31 : 100 + index,
            name: index === 0 ? "Adventure" : `Responsive genre ${index + 1}`,
            eligible_count: 42 - index,
         })),
      }),
      getAssistantFilterOptions: vi.fn().mockResolvedValue({
         eligible_count: 42,
         candidate_limit: 400,
         themes: [
            { igdb_id: 17, name: "Fantasy", eligible_count: 16 },
            { igdb_id: 18, name: "Science fiction", eligible_count: 9 },
            {
               igdb_id: 19,
               name: "Long-form atmospheric exploration",
               eligible_count: 7,
            },
            { igdb_id: 20, name: "Relaxing", eligible_count: 6 },
         ],
         game_modes: [
            { igdb_id: 1, name: "Single player", eligible_count: 35 },
            { igdb_id: 2, name: "Split screen cooperative", eligible_count: 8 },
            { igdb_id: 3, name: "Multiplayer", eligible_count: 5 },
         ],
      }),
      getAssistantRecommendations: vi.fn().mockResolvedValue({
         status: "ranked",
         eligible_count: 6,
         candidate_limit: 400,
         message: null,
         guided_fallback_available: true,
         items: Array.from({ length: 6 }, (_, index) => ({
            rank: index + 1,
            steam_app_id: 800 + index,
            title: `Responsive Assistant Game ${index + 1}`,
            cover_url: null,
            profile_playtime_minutes: index * 60,
            normal_completion_seconds: 7_200,
            summary: "A bounded AI-generated summary describing the game's premise, setting, central activity, and moment-to-moment play for this responsive fixture. ".repeat(3),
            reasoning: "Its relaxed pacing, low-pressure exploration, and gentle progression directly match your request for something relaxing after work. ".repeat(2),
            content_source: "ai_generated",
         })),
      }),
   };
});

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

function AssistantFixture() {
   return (
      <div className="app">
         <main className="app__content">
            <section className="app__session">
               <div className="app__current-profile" />
               <AssistantWorkspace sessionEpoch={7} onUseGuided={vi.fn()} />
            </section>
         </main>
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

   it("aligns the sample-library notice with the Steam input", async () => {
      const { container } = render(<PublicPageFixture />);
      const sampleNotice = container.querySelector<HTMLElement>(
         ".app__session-form-sample"
      );
      const input = container.querySelector<HTMLInputElement>(".app__input");
      expect(sampleNotice).not.toBeNull();
      expect(input).not.toBeNull();

      for (const viewport of PUBLIC_PAGE_VIEWPORTS) {
         await setTestViewport(viewport);
         const noticeBounds = (
            sampleNotice as HTMLElement
         ).getBoundingClientRect();
         const inputBounds = (input as HTMLInputElement).getBoundingClientRect();

         expect(
            noticeBounds.left,
            `sample/input left edge at ${viewportName(viewport)}`
         ).toBeCloseTo(inputBounds.left, 1);
         expect(
            noticeBounds.right,
            `sample/input right edge at ${viewportName(viewport)}`
         ).toBeCloseTo(inputBounds.right, 1);
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

   it("keeps the assistant form and result deck within every supported width", async () => {
      render(<AssistantFixture />);
      fireEvent.click(await screen.findByRole("button", {
         name: "Adventure, 42 eligible games",
      }));
      await screen.findByRole("group", { name: "Theme filters" });

      for (const viewport of PUBLIC_PAGE_VIEWPORTS) {
         await setTestViewport(viewport);
         expect(
            document.documentElement.scrollWidth,
            `assistant form width at ${viewportName(viewport)}`
         ).toBeLessThanOrEqual(viewport.width);
      }

      fireEvent.change(screen.getByLabelText("What are you in the mood to play?"), {
         target: { value: "Something relaxed with a satisfying ending" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Ask Ludex" }));
      await screen.findByRole("heading", { name: "Your AI recommendations" });

      for (const viewport of PUBLIC_PAGE_VIEWPORTS) {
         await setTestViewport(viewport);
         expect(
            document.documentElement.scrollWidth,
            `assistant results width at ${viewportName(viewport)}`
         ).toBeLessThanOrEqual(viewport.width);

         const firstCard = screen.getByRole("article", {
            name: "Responsive Assistant Game 1",
         });
         const stage = firstCard.querySelector<HTMLElement>(
            ".recommendation-result-card__stage"
         );
         const actions = firstCard.querySelector<HTMLElement>(
            ".assistant-result-card__actions"
         );
         const explanation = firstCard.querySelector<HTMLElement>(
            ".assistant-result-card__explanation"
         );
         const summaryRegion = screen.getByRole("region", {
            name: "Responsive Assistant Game 1 summary",
         });
         const reasoningRegion = screen.getByRole("region", {
            name: "Responsive Assistant Game 1 reasoning",
         });
         expect(stage).not.toBeNull();
         expect(actions).not.toBeNull();
         expect(explanation).not.toBeNull();
         expect(
            (actions as HTMLElement).getBoundingClientRect().top,
            `assistant actions after image stage at ${viewportName(viewport)}`
         ).toBeGreaterThanOrEqual(
            (stage as HTMLElement).getBoundingClientRect().bottom - 1
         );
         expect(
            (explanation as HTMLElement).getBoundingClientRect().bottom,
            `assistant explanation inside image stage at ${viewportName(viewport)}`
         ).toBeLessThanOrEqual(
            (stage as HTMLElement).getBoundingClientRect().bottom
         );
         expect(getComputedStyle(summaryRegion).overflowY).toBe("auto");
         expect(getComputedStyle(reasoningRegion).overflowY).toBe("auto");
         expect(summaryRegion.parentElement?.dataset.hasOverflow).toBe("true");
         expect(summaryRegion.parentElement?.dataset.atEnd).toBe("false");
         expect(
            summaryRegion.getBoundingClientRect().height,
            `summary/reasoning height at ${viewportName(viewport)}`
         ).toBeGreaterThan(0);
         expect(
            reasoningRegion.getBoundingClientRect().height,
            `reasoning scroll height at ${viewportName(viewport)}`
         ).toBeGreaterThan(0);
      }
   });

   it("signals bounded option overflow and aligns narrowing choices with genre pills", async () => {
      const { container } = render(<AssistantFixture />);
      await setTestViewport({ width: 1280, height: 720 });

      const genreFrame = container.querySelector<HTMLElement>(
         ".assistant-scroll-frame"
      );
      expect(genreFrame).not.toBeNull();
      expect(genreFrame?.dataset.hasOverflow).toBe("true");
      expect(genreFrame?.dataset.atEnd).toBe("false");

      fireEvent.click(await screen.findByRole("button", {
         name: "Adventure, 42 eligible games",
      }));
      await screen.findByRole("group", { name: "Theme filters" });

      for (const viewport of [
         { width: 320, height: 568 },
         { width: 1280, height: 720 },
         { width: 3840, height: 2160 },
      ]) {
         await setTestViewport(viewport);
         const themeButtons = Array.from(container.querySelectorAll<HTMLElement>(
            '.assistant-filters__group[aria-label="Theme filters"] .recommendation-choice-pill'
         ));
         const genreButton = screen.getByRole("button", {
            name: "Adventure, 42 eligible games",
         });
         const first = themeButtons[0].getBoundingClientRect();
         const genreRectangle = genreButton.getBoundingClientRect();
         expect(
            first.height,
            `standard filter and genre pill height at ${viewportName(viewport)}`
         ).toBeCloseTo(genreRectangle.height, 1);
         for (const button of themeButtons.slice(1)) {
            const rectangle = button.getBoundingClientRect();
            expect(
               rectangle.width,
               `theme pill width at ${viewportName(viewport)}`
            ).toBeCloseTo(first.width, 1);
            expect(
               rectangle.height,
               `wrapped theme pill height at ${viewportName(viewport)}`
            ).toBeGreaterThanOrEqual(first.height);
            expect(
               button.scrollHeight,
               `theme pill content at ${viewportName(viewport)}`
            ).toBeLessThanOrEqual(button.clientHeight);
         }

         const longModeButton = screen.getByRole("button", {
            name: "Split screen cooperative, 8 eligible games",
         });
         expect(
            longModeButton.getBoundingClientRect().height,
            `long filter pill height at ${viewportName(viewport)}`
         ).toBeGreaterThanOrEqual(first.height);
         expect(
            longModeButton.scrollHeight,
            `long filter pill content at ${viewportName(viewport)}`
         ).toBeLessThanOrEqual(longModeButton.clientHeight);
      }
   });
});
