// @ts-expect-error Vitest runs this contract in Node; app builds exclude Node globals.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const appCss = readFileSync("src/App.css", "utf8");
const sessionCss = readFileSync("src/features/session/session.css", "utf8");
const recommendationCss = readFileSync(
   "src/features/recommendations/recommendations.css",
   "utf8"
);
const packageJson = JSON.parse(readFileSync("package.json", "utf8")) as {
   dependencies: Record<string, string>;
};

describe("retro visual theme contract", () => {
   it("bundles one stable condensed display face while preserving body typography", () => {
      expect(packageJson.dependencies).toHaveProperty("@fontsource/bebas-neue");
      expect(appCss).toMatch(/^@import "@fontsource\/bebas-neue\/400\.css";/);
      expect(appCss).toMatch(
         /--font-display:\s*"Bebas Neue",\s*"Arial Narrow",\s*sans-serif/
      );
      expect(appCss).toMatch(
         /--font-body:\s*"Helvetica Neue",\s*Helvetica,\s*Arial,\s*sans-serif/
      );
   });

   it("keeps the hero dominant over secondary section headings", () => {
      expect(sessionCss).toMatch(
         /\.app__session h2\s*\{[^}]*font-size:\s*clamp\(3\.5rem,\s*12vw,\s*6\.25rem\)/
      );
      expect(sessionCss).toMatch(
         /\.app__session h3\s*\{[^}]*font-size:\s*clamp\(2\.5rem,\s*7vw,\s*3\.5rem\)/
      );
   });

   it("uses compact cream workspace tabs without a competing underline", () => {
      expect(sessionCss).toMatch(
         /\.app__workspace-nav\s*\{[^}]*gap:\s*0[^}]*padding:\s*0[^}]*backdrop-filter:\s*none/
      );
      expect(sessionCss).toMatch(
         /\.app__workspace-nav button\[aria-current="page"\]\s*\{[^}]*color:\s*var\(--color-void-black\)[^}]*background:\s*var\(--color-bone-cream\)/
      );
      expect(sessionCss).not.toMatch(
         /\.app__workspace-nav button\[aria-current="page"\]::after/
      );
   });

   it("keeps page framing, text feedback, and input focus visually quiet", () => {
      expect(appCss).not.toMatch(/\.app::after\s*\{/);
      expect(sessionCss).toMatch(
         /\.app \[role="status"\]\s*\{[^}]*color:\s*var\(--color-bone-cream\)/
      );
      expect(sessionCss).not.toMatch(
         /\.app \[role="status"\]\s*\{[^}]*text-decoration/
      );
      expect(sessionCss).toMatch(
         /\.app__input:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--color-bone-cream\)/
      );
      expect(sessionCss).not.toMatch(/\.app__input:focus\s*\{/);
   });

   it("separates filled primary actions from outlined secondary actions", () => {
      expect(sessionCss).toMatch(
         /\.app__primary-button\s*\{[^}]*background:\s*var\(--color-bone-cream\)[^}]*box-shadow:\s*0 4px 0 var\(--color-ash-taupe\)/
      );
      expect(sessionCss).toMatch(
         /\.app__secondary-button\s*\{[^}]*color:\s*var\(--color-bone-cream\)[^}]*background:\s*rgb\(0 0 0 \/ 82%\)[^}]*box-shadow:\s*none/
      );
      expect(recommendationCss).toMatch(
         /\.reference-game-card__facet,[\s\S]*min-height:\s*2\.5rem[^}]*font-size:\s*0\.875rem/
      );
      expect(recommendationCss).toMatch(
         /\.preference-validation button:not\(\.app__primary-button\)/
      );
   });

   it("uses fast recommendation-card feedback without lift, blur, or an offset shadow", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card\s*\{[^}]*transition:[^}]*120ms ease/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card:focus-within:not\(:focus\)\s*\{[^}]*box-shadow:\s*0 0 0 2px var\(--color-alarm-red\)/
      );
      expect(recommendationCss).not.toMatch(
         /\.recommendation-result-card:focus-within:not\(:focus\)\s*\{[^}]*transform:/
      );
      expect(recommendationCss).not.toMatch(
         /\.recommendation-result-card:hover\s*\{[^}]*transform:/
      );
      expect(recommendationCss).not.toMatch(/0 18px 42px/);
      expect(recommendationCss).not.toMatch(
         /6px 6px 0 rgb\(195 189 179 \/ 55%\)/
      );
   });

   it("keeps recommendation heading feedback and reset controls aligned", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-results__header\s*\{[^}]*margin-bottom:\s*1\.5rem[^}]*text-align:\s*center/
      );
   });

   it("gives available game, facet, and keyword choices cream hover feedback", () => {
      expect(recommendationCss).toMatch(
         /@media \(hover:\s*hover\)[\s\S]*\.reference-game-suggestions \[role="option"\]:hover:not\(\[aria-disabled="true"\]\),[\s\S]*\.reference-game-card__facet:hover:not\(:disabled\),[\s\S]*\.reference-keywords__options button:hover:not\(:disabled\)\s*\{[^}]*color:\s*var\(--color-void-black\)[^}]*background:\s*var\(--color-bone-cream\)/
      );
   });

   it("uses opaque editing surfaces over the moving library backdrop", () => {
      expect(recommendationCss).toMatch(
         /\.reference-game-card\s*\{[^}]*background:\s*rgb\(0 0 0 \/ 96%\)/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-constraints\s*\{[^}]*background:\s*rgb\(0 0 0 \/ 94%\)/
      );
      expect(recommendationCss).toMatch(
         /\.preference-validation\s*\{[^}]*background:\s*rgb\(0 0 0 \/ 94%\)/
      );
   });

   it("organizes reference preferences with dividers instead of nested boxes", () => {
      expect(recommendationCss).toMatch(
         /\.reference-game-card__preferences\s*\{[^}]*margin-top:\s*1\.25rem[^}]*border-top:\s*1px solid rgb\(195 189 179 \/ 65%\)/
      );
      expect(recommendationCss).toMatch(
         /\.reference-game-card__facet-group\s*\{[^}]*margin:\s*0[^}]*padding:\s*1rem 0 0[^}]*border:\s*0[^}]*border-top:\s*1px solid rgb\(195 189 179 \/ 45%\)/
      );
      expect(recommendationCss).toMatch(
         /\.reference-game-card__facet-group:first-child\s*\{[^}]*padding-top:\s*0[^}]*border-top:\s*0/
      );
      expect(recommendationCss).toMatch(
         /\.reference-keywords\s*\{[^}]*margin-top:\s*1rem[^}]*padding-top:\s*1rem[^}]*border-top:\s*1px solid rgb\(195 189 179 \/ 45%\)/
      );
   });

   it("presents recommendation constraints as flat, selectable control groups", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-constraints__content\s*\{[^}]*display:\s*grid[^}]*gap:\s*1\.25rem[^}]*border-top:\s*1px solid var\(--color-ash-taupe\)/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-constraints__group\s*\{[^}]*margin:\s*0[^}]*padding:\s*0[^}]*border:\s*0/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-constraints__choices\s*\{[^}]*display:\s*flex[^}]*flex-wrap:\s*wrap/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-constraints__choices button,\s*\.recommendation-constraints__clear\s*\{[^}]*min-height:\s*2\.5rem[^}]*border:\s*1px solid var\(--color-bone-cream\)[^}]*background:\s*transparent/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-constraints__choices button\[aria-pressed="true"\]\s*\{[^}]*color:\s*var\(--color-void-black\)[^}]*background:\s*var\(--color-bone-cream\)/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-constraints__unknown-note\s*\{[^}]*color:\s*var\(--color-ash-taupe\)/
      );
   });

   it("gives the reference identity more room without inflating its controls", () => {
      expect(recommendationCss).toMatch(
         /\.reference-game-card__header\s*\{[^}]*grid-template-columns:\s*6rem minmax\(0,\s*1fr\)/
      );
      expect(recommendationCss).toMatch(
         /\.reference-game-card__cover,\s*\.reference-game-card__cover-fallback\s*\{[^}]*width:\s*6rem/
      );
      expect(recommendationCss).toMatch(
         /\.reference-game-card__identity\s*\{[^}]*align-self:\s*center/
      );
      expect(recommendationCss).toMatch(
         /\.reference-game-card__facets\s*\{[^}]*gap:\s*0\.75rem[^}]*margin-top:\s*0\.75rem/
      );
   });

   it("shows details keyboard focus without drawing a second card outline", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__details > summary:focus-visible\s*\{[^}]*outline:\s*none[^}]*box-shadow:\s*inset 0 -3px 0 var\(--color-bone-cream\)/
      );
   });
});
