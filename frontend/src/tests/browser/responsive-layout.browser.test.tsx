import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { page, userEvent } from "vitest/browser";
import { describe, expect, it, vi } from "vitest";

import {
   getAssistantRecommendations,
   type SessionProfileResponse,
} from "../../api";
import Hero from "../../components/Hero";
import PublicDataNotice from "../../components/PublicDataNotice";
import ServerStatus from "../../components/ServerStatus";
import AutomaticRecommendations from "../../features/recommendations/automatic/AutomaticRecommendations";
import RecommendationResultCard from "../../features/recommendations/results/RecommendationResultCard";
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
      getAutomaticRecommendations: vi.fn().mockResolvedValue({
         status: "ready",
         rows: [0, 1, 2].map((rowIndex) => ({
            source_game: {
               steam_app_id: 900 + rowIndex,
               title: rowIndex === 0
                  ? "An Extraordinarily Long Responsive Source Game Title With Many Words"
                  : `Responsive Source ${rowIndex + 1}`,
               cover_url: null,
               playtime_minutes: 2_520 * (rowIndex + 1),
               achievement_percent: null,
            },
            recommendations: {
               outcome: "complete",
               eligible_count: 6,
               returned_count: 6,
               items: Array.from({ length: 6 }, (_, index) => ({
                  rank: index + 1,
                  steam_app_id: 1_000 + rowIndex * 10 + index,
                  title: index === 0
                     ? "Supercalifragilisticexpialidocious Responsive Automatic Game"
                     : `Responsive Automatic Game ${rowIndex * 10 + index + 1}`,
                  cover_url: null,
                  profile_playtime_minutes: 0,
                  normal_completion_seconds: 7_200,
                  ratings: { headline: null, critics: null, total: null },
                  factual_evidence: {
                     version: "factual-overlap-v1",
                     score_basis_points: 9_000,
                     active_budget: 100,
                     contributions: [],
                  },
                  facet_labels: [],
                  match_summary: {
                     reasons: [],
                     additional_match_count: 0,
                     text: "Matches your Adventure, Fantasy, and Single player preferences, plus 2 more.",
                  },
                  tradeoff: null,
               })),
            },
         })),
         suggested_preference: null,
      }),
      getMoreLikeThisRecommendations: vi.fn().mockResolvedValue({
         source_game: {
            steam_app_id: 1_020,
            title: "Responsive More Like Source",
            cover_url: null,
            playtime_minutes: 0,
            achievement_percent: null,
         },
         recommendations: {
            outcome: "sparse",
            eligible_count: 3,
            returned_count: 3,
            items: Array.from({ length: 3 }, (_, index) => ({
               rank: index + 1,
               steam_app_id: 1_100 + index,
               title: `Responsive More Like Game ${index + 1}`,
               cover_url: null,
               profile_playtime_minutes: 0,
               normal_completion_seconds: 3_600,
               ratings: { headline: null, critics: null, total: null },
               factual_evidence: {
                  version: "factual-overlap-v1",
                  score_basis_points: 8_000,
                  active_budget: 100,
                  contributions: [],
               },
               facet_labels: [],
               match_summary: {
                  reasons: [],
                  additional_match_count: 0,
                  text: "Matches your Fantasy preference.",
               },
               tradeoff: null,
            })),
         },
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
            ratings: { headline: null, critics: null, total: null },
            summary: "A bounded AI-generated summary describing the game's premise, setting, central activity, and moment-to-moment play for this responsive fixture. ".repeat(3),
            reasoning: "Its relaxed pacing, low-pressure exploration, and gentle progression directly match your request for something relaxing after work. ".repeat(6),
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

function AutomaticFixture() {
   return (
      <div className="app">
         <main className="app__content">
            <section className="app__session">
               <div className="app__current-profile" />
               <AutomaticRecommendations
                  onCustomize={vi.fn()}
                  onUnavailable={vi.fn()}
               />
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

   it("keeps the open Steam ID guide aligned with the input without overflow", async () => {
      const { container } = render(<PublicPageFixture />);
      const guide = container.querySelector<HTMLDetailsElement>(
         ".app__session-form-guide"
      );
      const input = container.querySelector<HTMLInputElement>(".app__input");
      expect(guide).not.toBeNull();
      expect(input).not.toBeNull();
      (guide as HTMLDetailsElement).open = true;

      for (const viewport of PUBLIC_PAGE_VIEWPORTS) {
         await setTestViewport(viewport);
         const guideBounds = (
            guide as HTMLDetailsElement
         ).getBoundingClientRect();
         const inputBounds = (input as HTMLInputElement).getBoundingClientRect();

         expect(
            guideBounds.left,
            `guide/input left edge at ${viewportName(viewport)}`
         ).toBeCloseTo(inputBounds.left, 1);
         expect(
            guideBounds.right,
            `guide/input right edge at ${viewportName(viewport)}`
         ).toBeCloseTo(inputBounds.right, 1);
         expect(
            (guide as HTMLDetailsElement).scrollWidth,
            `guide content width at ${viewportName(viewport)}`
         ).toBeLessThanOrEqual((guide as HTMLDetailsElement).clientWidth);
         expect(
            document.documentElement.scrollWidth,
            `login page width with open guide at ${viewportName(viewport)}`
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

   it("keeps automatic rows and toggles within every supported width", async () => {
      render(<AutomaticFixture />);
      await screen.findByRole("region", {
         name: /^Because you played An Extraordinarily Long/,
      });
      fireEvent.click(screen.getByRole("button", { name: "Up to 10 hours" }));
      await screen.findByText(/Games without a known completion time/);

      for (const viewport of PUBLIC_PAGE_VIEWPORTS) {
         await setTestViewport(viewport);
         const name = viewportName(viewport);
         expect(
            document.documentElement.scrollWidth,
            `automatic page width at ${name}`
         ).toBeLessThanOrEqual(viewport.width);

         const toggles = document.querySelector<HTMLElement>(".automatic-toggles");
         expect(toggles).not.toBeNull();
         const togglesBounds = (toggles as HTMLElement).getBoundingClientRect();
         for (const pill of Array.from(
            (toggles as HTMLElement).querySelectorAll<HTMLElement>("button")
         )) {
            const bounds = pill.getBoundingClientRect();
            expect(bounds.left, `toggle left at ${name}`)
               .toBeGreaterThanOrEqual(togglesBounds.left - 0.5);
            expect(bounds.right, `toggle right at ${name}`)
               .toBeLessThanOrEqual(togglesBounds.right + 0.5);
         }

         for (const row of Array.from(
            document.querySelectorAll<HTMLElement>(".automatic-recommendations__row")
         )) {
            const rowBounds = row.getBoundingClientRect();
            const cards = Array.from(
               row.querySelectorAll<HTMLElement>(".recommendation-result-card")
            );
            expect(cards, `row card count at ${name}`).toHaveLength(3);
            const tops = cards.map((card) => card.getBoundingClientRect().top);
            for (const card of cards) {
               const bounds = card.getBoundingClientRect();
               expect(bounds.left, `card left at ${name}`)
                  .toBeGreaterThanOrEqual(rowBounds.left - 0.5);
               expect(bounds.right, `card right at ${name}`)
                  .toBeLessThanOrEqual(rowBounds.right + 0.5);
               expect(card.scrollWidth, `card content width at ${name}`)
                  .toBeLessThanOrEqual(card.clientWidth + 1);
               // The whole portrait cover shows, and text stacks below it.
               const cover = card.querySelector<HTMLElement>(
                  ".recommendation-result-card__cover-frame"
               ) as HTMLElement;
               const coverBounds = cover.getBoundingClientRect();
               expect(
                  coverBounds.height / coverBounds.width,
                  `cover ratio at ${name}`
               ).toBeCloseTo(374 / 264, 1);
               const parts = [
                  ".recommendation-result-card__title",
                  ".recommendation-result-card__meta",
                  ".recommendation-result-card__match",
                  ".recommendation-result-card__actions",
               ].map((selector) =>
                  (card.querySelector(selector) as HTMLElement)
                     .getBoundingClientRect()
               );
               expect(parts[0].top, `title below cover at ${name}`)
                  .toBeGreaterThanOrEqual(coverBounds.bottom - 0.5);
               for (let index = 1; index < parts.length; index += 1) {
                  expect(
                     parts[index].top,
                     `card text stacks without overlap at ${name}`
                  ).toBeGreaterThanOrEqual(parts[index - 1].bottom - 0.5);
               }
               for (const button of Array.from(
                  card.querySelectorAll<HTMLElement>(
                     ".recommendation-result-card__actions button"
                  )
               )) {
                  const bounds = button.getBoundingClientRect();
                  expect(bounds.right, `action inside card at ${name}`)
                     .toBeLessThanOrEqual(card.getBoundingClientRect().right + 0.5);
                  expect(button.scrollWidth, `action label fits at ${name}`)
                     .toBeLessThanOrEqual(button.clientWidth + 1);
               }
            }
            const titleHeights = cards.map(
               (card) => (card.querySelector(
                  ".recommendation-result-card__title"
               ) as HTMLElement).getBoundingClientRect().height
            );
            expect(
               Math.max(...titleHeights) - Math.min(...titleHeights),
               `titles stay one line at ${name}`
            ).toBeLessThan(1);
            if (viewport.width >= 1024) {
               expect(
                  Math.max(...tops) - Math.min(...tops),
                  `three cards share a line at ${name}`
               ).toBeLessThan(1);
               const heights = cards.map(
                  (card) => card.getBoundingClientRect().height
               );
               expect(
                  Math.max(...heights) - Math.min(...heights),
                  `cards in a row are equally tall at ${name}`
               ).toBeLessThan(1);
            } else {
               expect(tops[1], `stacked cards at ${name}`)
                  .toBeGreaterThan(tops[0]);
               expect(tops[2], `stacked cards at ${name}`)
                  .toBeGreaterThan(tops[1]);
            }
         }
      }
   });

   it("scrolls a long title only while its card is hovered", async () => {
      await setTestViewport({ width: 1280, height: 900 });
      render(<AutomaticFixture />);
      await screen.findByRole("region", {
         name: /^Because you played An Extraordinarily Long/,
      });
      const [longCard] = screen.getAllByRole("article", {
         name: "Supercalifragilisticexpialidocious Responsive Automatic Game",
      });
      const titleOf = (card: HTMLElement) => card.querySelector<HTMLElement>(
         ".recommendation-result-card__title"
      ) as HTMLElement;
      const offset = (card: HTMLElement) => {
         const text = card.querySelector<HTMLElement>(
            ".recommendation-result-card__title-text"
         ) as HTMLElement;
         return text.getBoundingClientRect().left
            - titleOf(card).getBoundingClientRect().left;
      };

      await waitFor(() => {
         expect(titleOf(longCard).dataset.overflowing).toBe("true");
      });
      expect(getComputedStyle(titleOf(longCard)).maskImage).toContain("gradient");

      await userEvent.hover(longCard);
      await waitFor(() => {
         expect(offset(longCard)).toBeLessThan(-20);
      }, { timeout: 5_000 });
      expect(titleOf(longCard).dataset.marquee).toBe("active");

      await userEvent.unhover(longCard);
      await waitFor(() => {
         expect(Math.abs(offset(longCard))).toBeLessThan(1);
      }, { timeout: 2_000 });
      expect(titleOf(longCard).dataset.marquee).toBeUndefined();
   });

   it("lays out each preference comparison row as columns, stacking on phones", async () => {
      const { container } = render(
         <div style={{ width: "24rem" }}>
            <RecommendationResultCard
               item={{
                  rank: 1,
                  steam_app_id: 5,
                  title: "Comparison Game",
                  cover_url: null,
                  profile_playtime_minutes: 0,
                  normal_completion_seconds: null,
                  ratings: { headline: null, critics: null, total: null },
                  factual_evidence: {
                     version: "factual-overlap-v1",
                     score_basis_points: 5_000,
                     active_budget: 100,
                     contributions: [
                        {
                           reference_steam_app_id: 1,
                           facet_kind: "genre",
                           facet_igdb_id: 12,
                           match_state: "matched",
                           points_numerator: 1,
                           points_denominator: 1,
                        },
                     ],
                  },
                  facet_labels: [
                     { facet_kind: "genre", facet_igdb_id: 12, name: "Role-playing (RPG)" },
                  ],
                  match_summary: { reasons: [], additional_match_count: 0, text: "Matches." },
                  tradeoff: null,
               }}
            />
         </div>
      );
      fireEvent.click(screen.getByText("Game details"));
      const row = container.querySelector<HTMLElement>(
         ".recommendation-evidence__list li"
      ) as HTMLElement;
      const parts = Array.from(row.children) as HTMLElement[];

      await setTestViewport({ width: 1280, height: 900 });
      expect(getComputedStyle(row).listStyleType).toBe("none");
      const tops = parts.map((part) => part.getBoundingClientRect().top);
      expect(Math.max(...tops) - Math.min(...tops)).toBeLessThan(2);
      expect(parts[1].getBoundingClientRect().left)
         .toBeGreaterThan(parts[0].getBoundingClientRect().right);

      await setTestViewport({ width: 320, height: 800 });
      expect(parts[1].getBoundingClientRect().top)
         .toBeGreaterThanOrEqual(parts[0].getBoundingClientRect().bottom - 1);
   });

   it("brings a new More like row into view from the last row", async () => {
      for (const viewport of [
         { width: 390, height: 844 },
         { width: 3840, height: 2160 },
      ]) {
         await setTestViewport(viewport);
         const { unmount } = render(<AutomaticFixture />);
         await screen.findByRole("region", {
            name: /^Because you played An Extraordinarily Long/,
         });
         const button = screen.getByRole("button", {
            name: "More games like Responsive Automatic Game 23",
         });
         button.scrollIntoView({ block: "center" });
         fireEvent.click(button);

         const heading = await screen.findByRole("heading", {
            name: "More like Responsive More Like Source",
         });
         await waitFor(() => expect(heading).toHaveFocus());
         await waitFor(() => {
            const top = heading.getBoundingClientRect().top;
            expect(top, `new row top at ${viewportName(viewport)}`)
               .toBeGreaterThanOrEqual(0);
            expect(top, `new row top at ${viewportName(viewport)}`)
               .toBeLessThan(viewport.height / 3);
         }, { timeout: 5_000 });

         // A second request collapses the first More like row to one line.
         fireEvent.click(screen.getByRole("button", {
            name: "More games like Responsive Automatic Game 22",
         }));
         await waitFor(() => {
            expect(
               document.querySelectorAll(".automatic-recommendations__collapsed")
            ).toHaveLength(1);
         });
         for (const width of [320, viewport.width]) {
            await setTestViewport({ width, height: viewport.height });
            const summary = document.querySelector<HTMLElement>(
               ".automatic-recommendations__collapsed > summary"
            ) as HTMLElement;
            const rows = document.querySelector<HTMLElement>(
               ".automatic-recommendations__rows"
            ) as HTMLElement;
            const summaryBounds = summary.getBoundingClientRect();
            expect(summaryBounds.left, `collapsed row left at ${width}`)
               .toBeGreaterThanOrEqual(rows.getBoundingClientRect().left - 0.5);
            expect(summaryBounds.right, `collapsed row right at ${width}`)
               .toBeLessThanOrEqual(rows.getBoundingClientRect().right + 0.5);
            expect(summaryBounds.height, `collapsed row height at ${width}`)
               .toBeLessThan(120);
            expect(document.documentElement.scrollWidth, `page width at ${width}`)
               .toBeLessThanOrEqual(width);
         }
         unmount();
      }
   });

   it("keeps the Ask Ludex bar and its row within every supported width", async () => {
      render(<AutomaticFixture />);
      await screen.findByRole("region", {
         name: /^Because you played An Extraordinarily Long/,
      });
      fireEvent.change(screen.getByLabelText("Ask Ludex"), {
         target: { value: "Something relaxed with a satisfying ending" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Ask" }));
      const row = await screen.findByRole("region", {
         name: "Ludex AI picks for “Something relaxed with a satisfying ending”",
      });
      const form = document.querySelector<HTMLElement>(".ask-ludex") as HTMLElement;

      for (const viewport of PUBLIC_PAGE_VIEWPORTS) {
         await setTestViewport(viewport);
         const name = viewportName(viewport);
         expect(
            document.documentElement.scrollWidth,
            `Ask Ludex page width at ${name}`
         ).toBeLessThanOrEqual(viewport.width);
         const formBounds = form.getBoundingClientRect();
         for (const control of [
            screen.getByLabelText("Ask Ludex"),
            screen.getByRole("button", { name: "Ask" }),
         ]) {
            const bounds = control.getBoundingClientRect();
            expect(bounds.left, `prompt control left at ${name}`)
               .toBeGreaterThanOrEqual(formBounds.left - 0.5);
            expect(bounds.right, `prompt control right at ${name}`)
               .toBeLessThanOrEqual(formBounds.right + 0.5);
         }

         const firstCard = within(row).getByRole("article", {
            name: "Responsive Assistant Game 1",
         });
         const cover = firstCard.querySelector<HTMLElement>(
            ".recommendation-result-card__cover-frame"
         ) as HTMLElement;
         const explanation = firstCard.querySelector<HTMLElement>(
            ".assistant-result-card__explanation"
         ) as HTMLElement;
         const actions = firstCard.querySelector<HTMLElement>(
            ".recommendation-result-card__actions"
         ) as HTMLElement;
         const reasoningRegion = within(firstCard).getByRole("region", {
            name: "Responsive Assistant Game 1 reasoning",
         });
         const coverBounds = cover.getBoundingClientRect();
         expect(coverBounds.height / coverBounds.width, `AI cover ratio at ${name}`)
            .toBeCloseTo(374 / 264, 1);
         expect(explanation.getBoundingClientRect().top, `reasoning below cover at ${name}`)
            .toBeGreaterThanOrEqual(coverBounds.bottom - 0.5);
         expect(
            actions.getBoundingClientRect().top
               - explanation.getBoundingClientRect().bottom,
            `no gap between reasoning and actions at ${name}`
         ).toBeLessThan(24);
         expect(getComputedStyle(reasoningRegion).overflowY).toBe("auto");
         expect(reasoningRegion.parentElement?.dataset.hasOverflow).toBe("true");
         expect(firstCard.querySelector("details")).toContainElement(
            within(firstCard).getByText(/A bounded AI-generated summary/)
         );
         expect(firstCard.scrollWidth, `AI card width at ${name}`)
            .toBeLessThanOrEqual(firstCard.clientWidth + 1);
      }
   });

   it("keeps the inline genre step within every supported width", async () => {
      vi.mocked(getAssistantRecommendations).mockResolvedValueOnce({
         status: "needs_genre",
         eligible_count: 2_400,
         candidate_limit: 2000,
         items: [],
         message: "Your library is large, so pick a genre to focus on.",
         guided_fallback_available: true,
      });
      render(<AutomaticFixture />);
      await screen.findByRole("region", {
         name: /^Because you played An Extraordinarily Long/,
      });
      fireEvent.change(screen.getByLabelText("Ask Ludex"), {
         target: { value: "A long RPG" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Ask" }));
      await screen.findByRole("button", { name: "Adventure, 42 games" });
      const choices = document.querySelector<HTMLElement>(
         ".ask-ludex__choices"
      ) as HTMLElement;

      for (const viewport of PUBLIC_PAGE_VIEWPORTS) {
         await setTestViewport(viewport);
         const name = viewportName(viewport);
         expect(
            document.documentElement.scrollWidth,
            `genre step page width at ${name}`
         ).toBeLessThanOrEqual(viewport.width);
         const bounds = choices.getBoundingClientRect();
         for (const pill of Array.from(choices.querySelectorAll<HTMLElement>("button"))) {
            const pillBounds = pill.getBoundingClientRect();
            expect(pillBounds.right, `genre pill inside step at ${name}`)
               .toBeLessThanOrEqual(bounds.right + 0.5);
         }
         expect(bounds.height, `genre list bounded at ${name}`)
            .toBeLessThanOrEqual(16 * 16 + 1);
         const step = choices.closest("fieldset") as HTMLElement;
         const legend = step.querySelector("legend") as HTMLElement;
         expect(
            legend.getBoundingClientRect().top,
            `genre question below the divider at ${name}`
         ).toBeGreaterThanOrEqual(step.getBoundingClientRect().top + 1);
      }
   });
});
