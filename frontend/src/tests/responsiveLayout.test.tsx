// @ts-expect-error Vitest runs this contract in Node; app builds exclude Node globals.
import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
   FinalRecommendationItemResponse,
} from "../api";
import RecommendationResultCard from "../features/recommendations/RecommendationResultCard";

const appCss = readFileSync("src/App.css", "utf8");
const recommendationCss = readFileSync(
   "src/features/recommendations/recommendations.css",
   "utf8"
);
const sessionCss = readFileSync(
   "src/features/session/session.css",
   "utf8"
);
const longToken = "A".repeat(180);

const recommendation: FinalRecommendationItemResponse = {
   rank: 1,
   steam_app_id: 620,
   title: longToken,
   cover_url: null,
   profile_playtime_minutes: 0,
   normal_completion_seconds: null,
   factual_evidence: {
      version: "factual-overlap-v1",
      score_basis_points: 8000,
      active_budget: 100,
      contributions: [],
   },
   facet_labels: [],
   match_summary: {
      reasons: [],
      additional_match_count: 0,
      text: longToken,
   },
   tradeoff: null,
};

describe("responsive layout contract", () => {
   it("renders long cached-library and recommendation facts without truncating them", () => {
      render(<RecommendationResultCard item={recommendation} />);
      expect(screen.getByRole("article", { name: longToken }))
         .toBeInTheDocument();
   });

   it("keeps bounded scroll regions and overflow-resistant text at every width", () => {
      expect(appCss).toMatch(/\.app__content[\s\S]*width:\s*min\(100%,\s*42\.5rem\)/);
      expect(sessionCss).toMatch(/\.app__selection strong\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(sessionCss).toMatch(/\.app__library-backdrop\s*\{[^}]*position:\s*fixed[^}]*inset:\s*0[^}]*overflow:\s*hidden/);
      expect(sessionCss).toMatch(/\.app__library-card-fallback\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(recommendationCss).toMatch(/\.reference-keywords__options[\s\S]*max-height:\s*16rem[\s\S]*overflow-y:\s*auto/);
      expect(recommendationCss).toMatch(/\.reference-game-suggestions span\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(recommendationCss).toMatch(/\.recommendation-result-card__content h3\s*\{[^}]*overflow-wrap:\s*anywhere/);
   });

   it("switches forms, game rows, cards, facts, and evidence to narrow layouts", () => {
      expect(sessionCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.app__session-form[\s\S]*grid-template-columns:\s*1fr/);
      expect(sessionCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.app__profile-actions[\s\S]*flex-direction:\s*column/);
      expect(recommendationCss).toMatch(/\.recommendation-result-card\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
      expect(recommendationCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.recommendation-result-card__facts[\s\S]*grid-template-columns:\s*1fr/);
      expect(recommendationCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.recommendation-evidence__list li[\s\S]*grid-template-columns:\s*1fr/);
   });

   it("shortens the hero when a Steam session is ready", () => {
      expect(appCss).toMatch(
         /\.app:has\(\.app__current-profile\) \.app__hero\s*\{[^}]*min-height:\s*clamp\(/
      );
      expect(appCss).toMatch(
         /\.app:has\(\.app__current-profile\) \.app__session\s*\{[^}]*margin-top:/
      );
      expect(appCss).toMatch(
         /\.app:has\(\.app__current-profile\) \.app__logo-heading\s*\{[^}]*width:\s*min\(100%,\s*22rem\)/
      );
      expect(appCss).toMatch(
         /\.app:has\(\.app__current-profile\) \.app__session h2\s*\{[^}]*font-size:\s*clamp\(/
      );
   });

   it("keeps the workspace navigation in normal document flow", () => {
      expect(sessionCss).not.toMatch(/\.app__workspace-nav-anchor\s*\{/);
      expect(sessionCss).not.toMatch(
         /\.app__recommendation-workspace__body--nav-floating\s*\{/
      );
      expect(sessionCss).not.toMatch(/\.app__workspace-nav--side\s*\{/);
      expect(sessionCss).not.toMatch(/\.app__workspace-nav\s*\{[^}]*position:\s*(?:sticky|fixed)/);
      expect(sessionCss).toMatch(
         /\.app__workspace-nav button\[aria-current="page"\]\s*\{[^}]*background:/
      );
   });

   it("lays recommendation cards out as a compact desktop deck", () => {
      expect(appCss).toMatch(
         /\.app:has\(\.app__current-profile\) \.app__content\s*\{[^}]*width:\s*min\(100%,\s*75rem\)/
      );
      expect(recommendationCss).toMatch(
         /\.reference-selection__preferences,\s*\.preference-validation\s*\{[^}]*width:\s*min\(100%,\s*42\.5rem\)[^}]*margin-inline:\s*auto/
      );
      expect(recommendationCss).toMatch(
         /@media \(min-width:\s*64rem\)[\s\S]*\.recommendation-results__cards\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(18rem,\s*1fr\)\)[^}]*align-items:\s*start/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card\s*\{[^}]*min-height:\s*var\(--recommendation-card-stage-height\)[^}]*align-content:\s*end[^}]*padding-top:\s*5rem/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card\s*\{[^}]*box-sizing:\s*border-box[^}]*min-width:\s*0/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__content h3\s*\{[^}]*font-size:\s*clamp\(/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__details,\s*\.recommendation-result-card__actions\s*\{[^}]*grid-column:\s*1\s*\/\s*-1/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__actions\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*1fr/
      );
   });

   it("gives full-art recommendation cards a readable surface and clear action hierarchy", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card\s*\{[^}]*position:\s*relative[^}]*isolation:\s*isolate[^}]*overflow:\s*hidden[^}]*background:\s*var\(--color-void-black\)/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card::after\s*\{[^}]*position:\s*absolute[^}]*z-index:\s*1[^}]*inset:\s*0[^}]*linear-gradient\(/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card:focus\s*\{[^}]*outline:\s*2px solid var\(--color-alarm-red\)[^}]*outline-offset:\s*3px/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__content h3\s*\{[^}]*min-height:\s*1\.9em/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__actions \.app__secondary-button\s*\{[^}]*margin-top:\s*0[^}]*color:\s*var\(--color-bone-cream\)[^}]*background:\s*transparent[^}]*box-shadow:\s*none/
      );
   });

   it("gives recommendation covers and titles a deliberate composition", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card\s*\{[^}]*--recommendation-card-stage-height:\s*clamp\(30rem,\s*70vw,\s*32rem\)[^}]*min-height:\s*var\(--recommendation-card-stage-height\)/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__cover-frame\s*\{[^}]*position:\s*absolute[^}]*z-index:\s*0[^}]*top:\s*0[^}]*inset-inline:\s*0[^}]*height:\s*var\(--recommendation-card-stage-height\)[^}]*overflow:\s*hidden/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__cover,\s*\.recommendation-result-card__cover-fallback\s*\{[^}]*width:\s*100%[^}]*height:\s*100%/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__cover\s*\{[^}]*object-fit:\s*cover/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__content header\s*\{[^}]*display:\s*grid[^}]*gap:\s*0\.35rem/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__content h3\s*\{[^}]*margin:\s*0[^}]*min-height:\s*1\.9em[^}]*overflow-wrap:\s*anywhere/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__rank\s*\{[^}]*position:\s*absolute[^}]*top:\s*1rem[^}]*left:\s*1rem[^}]*background:/
      );
      expect(recommendationCss).not.toMatch(
         /@media \(min-width:\s*64rem\)[\s\S]*\.recommendation-result-card\s*\{[^}]*padding:\s*1rem/
      );
   });

   it("keeps expanded recommendation details visually simple", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__details > summary:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--color-alarm-red\)[^}]*outline-offset:\s*3px/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__facts\s*\{[^}]*border-top:\s*1px solid var\(--color-ash-taupe\)/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__facts div\s*\{[^}]*padding:\s*0\.75rem 0[^}]*border-bottom:\s*1px solid var\(--color-ash-taupe\)/
      );
      expect(recommendationCss).not.toMatch(
         /\.recommendation-result-card__facts div\s*\{[^}]*border:\s*1px/
      );
      expect(recommendationCss).not.toMatch(
         /\.recommendation-evidence\s*\{[^}]*border-(?:top|bottom):/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__details\[open\]\s*\{[^}]*background:\s*transparent/
      );
      expect(recommendationCss).not.toMatch(
         /\.recommendation-result-card__details\[open\]\s*\{[^}]*background:\s*rgb\(0 0 0 \/ 96%\)/
      );
      expect(recommendationCss).not.toMatch(
         /\.recommendation-result-card__details\[open\]\s*\{[^}]*position:\s*absolute/
      );
      expect(recommendationCss).not.toMatch(
         /\.recommendation-result-card:has\(\.recommendation-result-card__details\[open\]\)[^{]*\{[^}]*visibility:\s*hidden/
      );
   });

   it("turns the recommendation deck into a swipeable snap row below desktop", () => {
      expect(recommendationCss).toMatch(
         /@media \(max-width:\s*63\.999rem\)[\s\S]*\.recommendation-results__cards\s*\{[^}]*grid-auto-flow:\s*column[^}]*overflow-x:\s*auto[^}]*scroll-snap-type:\s*x mandatory/
      );
      expect(recommendationCss).toMatch(
         /@media \(max-width:\s*63\.999rem\)[\s\S]*\.recommendation-result-card\s*\{[^}]*scroll-snap-align:\s*start/
      );
   });

   it("keeps collapsed reference summaries compact and their actions usable", () => {
      expect(recommendationCss).toMatch(
         /\.reference-game-card__header\s*\{[^}]*grid-template-columns:\s*5rem minmax\(0,\s*1fr\)/
      );
      expect(recommendationCss).toMatch(
         /\.reference-game-card__identity h3\s*\{[^}]*font-size:\s*clamp\(/
      );
      expect(recommendationCss).toMatch(
         /\.reference-game-card__summary-actions\s*\{[^}]*display:\s*flex[^}]*flex-wrap:\s*wrap/
      );
   });

   it("keeps the compact recommendation action panel in normal document flow", () => {
      expect(recommendationCss).toMatch(
         /\.preference-validation\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\) auto/
      );
      expect(recommendationCss).toMatch(
         /\.preference-validation\s*\{[^}]*border:\s*1px solid var\(--color-bone-cream\)/
      );
      expect(recommendationCss).not.toMatch(
         /\.preference-validation\s*\{[^}]*border:\s*1px dashed var\(--color-alarm-red\)/
      );
      expect(recommendationCss).not.toMatch(
         /\.preference-validation\s*\{[^}]*position:\s*sticky/
      );
      expect(recommendationCss).toMatch(
         /\.preference-validation__summary h3\s*\{[^}]*font-size:\s*clamp\(/
      );
      expect(recommendationCss).toMatch(
         /@media \(max-width:\s*36rem\)[\s\S]*\.preference-validation\s*\{[^}]*grid-template-columns:\s*1fr/
      );
   });

   it("fully hides the preference action panel on the recommendations tab", () => {
      expect(recommendationCss).toMatch(
         /\.preference-validation\[hidden\]\s*\{[^}]*display:\s*none/
      );
   });

   it("uses only the results divider on the recommendations tab", () => {
      expect(recommendationCss).toMatch(
         /\.reference-selection\s*\{[^}]*margin-top:\s*2rem[^}]*border-top:\s*2px solid var\(--color-alarm-red\)/
      );
      expect(recommendationCss).toMatch(
         /\.reference-selection--recommendations\s*\{[^}]*padding-top:\s*0[^}]*border-top:\s*0/
      );
      expect(recommendationCss).toMatch(
         /\.reference-selection--recommendations \.recommendation-results\s*\{[^}]*margin-top:\s*0/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-results\s*\{[^}]*border-top:\s*2px solid var\(--color-alarm-red\)/
      );
   });
});
