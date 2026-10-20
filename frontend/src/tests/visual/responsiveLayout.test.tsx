// @ts-expect-error Vitest runs this contract in Node; app builds exclude Node globals.
import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
   FinalRecommendationItemResponse,
} from "../../api";
import RecommendationResultCard from "../../features/recommendations/results/RecommendationResultCard";

const appCss = readFileSync("src/App.css", "utf8");
const recommendationCss = [
   "src/features/recommendations/styles/workspace.css",
   "src/features/recommendations/styles/shared-controls.css",
   "src/features/recommendations/references/references.css",
   "src/features/recommendations/preferences/preferences.css",
   "src/features/recommendations/results/results.css",
   "src/features/recommendations/assistant/assistant.css",
   "src/features/recommendations/automatic/automatic.css",
].map((path) => readFileSync(path, "utf8")).join("\n");
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
   ratings: { headline: null, critics: null, total: null },
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

   it("stacks automatic rows on phones and wraps their toggles without fixed widths", () => {
      const automaticCss = readFileSync(
         "src/features/recommendations/automatic/automatic.css",
         "utf8"
      );

      expect(automaticCss).toMatch(
         /\.automatic-recommendations__cards\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*24rem\)[^}]*justify-content:\s*center/
      );
      expect(automaticCss).toMatch(
         /@media \(min-width:\s*64rem\)\s*\{\s*\.automatic-recommendations__cards\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/
      );
      expect(automaticCss).toMatch(
         /\.automatic-toggles\s*\{[^}]*flex-wrap:\s*wrap/
      );
      expect(automaticCss).toMatch(
         /\.automatic-toggles__choices\s*\{[^}]*flex-wrap:\s*wrap/
      );
      expect(automaticCss).toMatch(
         /\.automatic-recommendations__row h4\s*\{[^}]*overflow-wrap:\s*anywhere/
      );
      expect(automaticCss).not.toMatch(/(?:^|[\s;{])(?:min-)?width:\s*\d+(?:px|rem)/m);
      expect(automaticCss).not.toMatch(/min-width:\s*48rem/);
      expect(automaticCss).not.toMatch(/overflow-x:\s*auto/);
   });

   it("keeps bounded scroll regions and overflow-resistant text at every width", () => {
      expect(appCss).toMatch(/\.app__content[\s\S]*width:\s*min\(100%,\s*42\.5rem\)/);
      expect(sessionCss).toMatch(/\.app__selection strong\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(sessionCss).toMatch(/\.app__library-backdrop\s*\{[^}]*position:\s*fixed[^}]*inset:\s*0[^}]*overflow:\s*hidden/);
      expect(sessionCss).toMatch(/\.app__library-card-fallback\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(recommendationCss).toMatch(/\.reference-keywords__options[\s\S]*max-height:\s*16rem[\s\S]*overflow-y:\s*auto/);
      expect(recommendationCss).toMatch(/\.reference-game-suggestions span\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(recommendationCss).toMatch(/\.recommendation-result-card__title\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(recommendationCss).toMatch(/\.recommendation-result-card__meta\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(recommendationCss).not.toMatch(/\.assistant-result-card__explanation\s*\{[^}]*(?:^|[\s;])height:/m);
      expect(recommendationCss).toMatch(/\.assistant-result-card__scroll-region\s*\{[^}]*height:\s*calc\(5 \* 1\.45em\)[^}]*overflow-y:\s*auto[^}]*scrollbar-gutter:\s*stable/);
      expect(recommendationCss).toMatch(/\.assistant-result-card__explanation \.assistant-scroll-frame\s*\{[^}]*--assistant-scroll-fade-height:\s*1\.5rem/);
      expect(recommendationCss).toMatch(/\.assistant-scroll-frame\[data-has-overflow="true"\]\[data-at-end="false"\]::after\s*\{[^}]*opacity:\s*1/);
   });

   it("switches forms, game rows, cards, facts, and evidence to narrow layouts", () => {
      expect(sessionCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.app__session-form[\s\S]*grid-template-columns:\s*1fr/);
      expect(sessionCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.app__profile-actions[\s\S]*flex-direction:\s*column/);
      expect(recommendationCss).toMatch(/\.recommendation-result-card__actions\s*\{[^}]*display:\s*flex[^}]*flex-wrap:\s*wrap/);
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

   it("keeps Steam entry in a compact retro access surface", () => {
      expect(appCss).toMatch(
         /\.app:has\(\.app__session--access\)\s*\{[^}]*padding-bottom:\s*clamp\(2rem,\s*5vw,\s*3rem\)/
      );
      expect(appCss).toMatch(
         /\.app:has\(\.app__session--access\) \.app__hero\s*\{[^}]*min-height:\s*auto/
      );
      expect(appCss).toMatch(
         /\.app:has\(\.app__session--access\) \.app__logo-heading\s*\{[^}]*width:\s*min\(100%,\s*22rem\)/
      );
      expect(sessionCss).toMatch(
         /\.app__session--access\s*\{[^}]*margin-top:\s*clamp\(2rem,\s*5vh,\s*3\.5rem\)[^}]*border:\s*1px solid var\(--color-bone-cream\)[^}]*background:\s*rgb\(0 0 0 \/ 94%\)/
      );
      expect(sessionCss).not.toMatch(
         /\.app__session--access\s*\{[^}]*border-top:/
      );
      expect(sessionCss).toMatch(
         /\.app__session--access h2\s*\{[^}]*font-size:\s*clamp\(2\.75rem,\s*7vw,\s*4\.25rem\)/
      );
      expect(sessionCss).toMatch(
         /\.app__session--access \.app__session-form\s*\{[^}]*margin-bottom:\s*0/
      );
      expect(sessionCss).toMatch(
         /\.app__input\s*\{[^}]*border-radius:\s*0/
      );
      expect(sessionCss).toMatch(
         /\.app__session-form-help\s*\{[^}]*grid-column:\s*1 \/ -1[^}]*color:\s*var\(--color-ash-taupe\)/
      );
      expect(sessionCss).toMatch(
         /\.app__session-form-guide\s*\{[^}]*grid-column:\s*1 \/ -1[^}]*border:\s*1px solid rgb\(239 226 192 \/ 45%\)[^}]*color:\s*var\(--color-ash-taupe\)/
      );
      expect(sessionCss).not.toMatch(
         /\.app__session-form-guide[^{]*\{[^}]*(?:^|[\s;])(?:min-)?width:\s*\d/m
      );
      expect(sessionCss).toMatch(
         /\.app__session-form-error\s*\{[^}]*grid-column:\s*1 \/ -1[^}]*border-left:\s*3px solid var\(--color-alarm-red\)/
      );
      expect(sessionCss).toMatch(
         /\.app__session-recovery\s*\{[^}]*padding:\s*0\.85rem 1rem[^}]*border-left:\s*3px solid var\(--color-alarm-red\)[^}]*text-align:\s*left/
      );
      expect(sessionCss).toMatch(
         /@media \(max-width:\s*36rem\)[\s\S]*\.app__session--access\s*\{[^}]*margin-top:\s*1\.5rem[^}]*padding:\s*1\.25rem[^}]*\}[\s\S]*\.app__session--access \.app__primary-button\s*\{[^}]*width:\s*100%[^}]*justify-self:\s*stretch/
      );
   });

   it("places a state-colored server indicator at the top right", () => {
      expect(appCss).toMatch(
         /\.app__status\s*\{[^}]*position:\s*absolute[^}]*top:[^}]*right:[^}]*margin:\s*0/
      );
      expect(appCss).toMatch(
         /\.app__status--connected::before\s*\{[^}]*background:\s*var\(--color-status-connected\)/
      );
      expect(appCss).toMatch(
         /\.app__status--checking::before\s*\{[^}]*background:\s*var\(--color-status-pending\)/
      );
      expect(appCss).toMatch(
         /\.app__status--unavailable::before\s*\{[^}]*background:\s*var\(--color-alarm-red\)/
      );
      expect(appCss).not.toMatch(/\.app__step-label\s*\{/);
   });

   it("keeps the workspace navigation in normal document flow", () => {
      expect(sessionCss).not.toMatch(/\.app__workspace-nav-anchor\s*\{/);
      expect(sessionCss).not.toMatch(
         /\.app__recommendation-workspace__body--nav-floating\s*\{/
      );
      expect(sessionCss).not.toMatch(/\.app__workspace-nav--side\s*\{/);
      expect(sessionCss).not.toMatch(/\.app__workspace-nav\s*\{[^}]*position:\s*(?:sticky|fixed)/);
      expect(sessionCss).toMatch(
         /\.app__workspace-nav button\[aria-current="page"\]\s*\{[^}]*border-bottom-color:\s*var\(--color-alarm-red\)[^}]*color:\s*var\(--color-bone-cream\)/
      );
   });

   it("keeps Ask Ludex and shared choice controls fluid and aligned with Ludex", () => {
      const automaticCss = readFileSync(
         "src/features/recommendations/automatic/automatic.css",
         "utf8"
      );
      expect(automaticCss).toMatch(
         /\.ask-ludex__field\s*\{[^}]*display:\s*flex[^}]*flex-wrap:\s*wrap/
      );
      expect(automaticCss).toMatch(
         /\.ask-ludex__field input\s*\{[^}]*flex:\s*1 1 14rem[^}]*min-width:\s*0/
      );
      expect(automaticCss).toMatch(
         /\.ask-ludex__choices\s*\{[^}]*flex-wrap:\s*wrap[^}]*max-height:\s*16rem[^}]*overflow-y:\s*auto/
      );
      expect(automaticCss).toMatch(
         /\.ask-ludex__note,\s*\.ask-ludex__status,\s*\.ask-ludex__error\s*\{[^}]*overflow-wrap:\s*anywhere/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-choice-pill\s*\{[^}]*border:\s*2px solid var\(--color-bone-cream\)[^}]*border-radius:\s*999px/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-constraints\s*\{[^}]*border:\s*0[^}]*background:\s*transparent/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-choice-grid--equal\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)[^}]*grid-auto-rows:\s*4\.25rem/
      );
      expect(recommendationCss).toMatch(
         /\.assistant-scroll-frame\[data-has-overflow="true"\]\[data-at-end="false"\]::after\s*\{[^}]*opacity:\s*1/
      );
      expect(recommendationCss).not.toMatch(
         /\.assistant-(?:workspace|step|filters|option-grid|prompt|data-use|state)\b/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__cover-fallback\s*\{[^}]*place-items:\s*center/
      );
      expect(recommendationCss).not.toMatch(/!important/);
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
         /\.recommendation-result-card\s*\{[^}]*display:\s*flex[^}]*box-sizing:\s*border-box[^}]*min-width:\s*0[^}]*flex-direction:\s*column/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__title\s*\{[^}]*font-size:\s*clamp\(/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__actions button\s*\{[^}]*flex:\s*1 1 11rem[^}]*min-width:\s*0/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-results__cards--accepted\s*\{[^}]*width:\s*min\(100%,\s*24rem\)[^}]*margin-inline:\s*auto/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-results__cards--accepted \.recommendation-result-card__cover\s*\{[^}]*object-fit:\s*contain/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-results__start-over\s*\{[^}]*display:\s*block[^}]*margin:\s*1rem auto 0/
      );
   });

   it("keeps card text on a solid surface below the cover with a clear action hierarchy", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card\s*\{[^}]*overflow:\s*hidden[^}]*border:\s*1px solid var\(--color-bone-cream\)[^}]*background:\s*var\(--color-void-black\)/
      );
      expect(recommendationCss).not.toMatch(/\.recommendation-result-card::(?:before|after)/);
      expect(recommendationCss).not.toMatch(/\.recommendation-result-card[\w-]*\s*\{[^}]*text-shadow/);
      expect(recommendationCss).not.toMatch(/--recommendation-card-height/);
      expect(recommendationCss).not.toMatch(/\.recommendation-result-card__(?:stage|rank|content)\b/);
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card:focus\s*\{[^}]*outline:\s*none/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card:focus-within:not\(:focus\)\s*\{[^}]*border-color:\s*var\(--color-alarm-red\)[^}]*box-shadow:/
      );
      expect(recommendationCss).toMatch(
         /@media \(hover:\s*hover\)[\s\S]*\.recommendation-result-card:hover\s*\{[^}]*border-color:\s*var\(--color-alarm-red\)[^}]*box-shadow:/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card\[data-selection-state="accepted"\]\s*\{[^}]*border-color:\s*var\(--color-alarm-red\)[^}]*box-shadow:/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card\[data-selection-state="accepted"\] \.recommendation-result-card__cover\s*\{[^}]*filter:\s*brightness\(1\.08\) saturate\(1\.05\)/
      );
      expect(recommendationCss).toMatch(
         /@media \(prefers-reduced-motion:\s*reduce\)[\s\S]*\.recommendation-result-card,\s*\.recommendation-result-card__cover\s*\{[^}]*transition:\s*none/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__actions \.app__secondary-button\s*\{[^}]*color:\s*var\(--color-bone-cream\)[^}]*background:\s*transparent[^}]*box-shadow:\s*none/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__match\s*\{[^}]*overflow:\s*hidden[^}]*-webkit-line-clamp:\s*2/
      );
   });

   it("keeps card text slots fixed so cards in a row line up", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card \.recommendation-result-card__title\s*\{[^}]*overflow:\s*hidden[^}]*white-space:\s*nowrap/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__title\[data-overflowing="true"\]:not\(\[data-marquee="active"\]\)\s*\{[^}]*mask-image:\s*linear-gradient/
      );
      expect(recommendationCss).toMatch(
         /@media \(prefers-reduced-motion:\s*reduce\)\s*\{\s*\.recommendation-result-card \.recommendation-result-card__title\s*\{[^}]*white-space:\s*normal[^}]*-webkit-line-clamp:\s*2/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__meta\s*\{[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__match\s*\{[^}]*min-height:\s*calc\(2 \* 1\.4em\)/
      );
      // Titles scroll from script; the only CSS animations are Ask Ludex's
      // waiting placeholders and spinner.
      expect(
         [...recommendationCss.matchAll(/@keyframes\s+([\w-]+)/g)]
            .map((match) => match[1])
            .sort()
      ).toEqual(["ask-ludex-pulse", "ask-ludex-spin", "ask-ludex-sweep"]);
   });

   it("keeps the whole portrait cover visible above the card text", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__cover-frame\s*\{[^}]*aspect-ratio:\s*264 \/ 374[^}]*overflow:\s*hidden/
      );
      expect(recommendationCss).not.toMatch(
         /\.recommendation-result-card__cover-frame\s*\{[^}]*position:\s*absolute/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__cover,\s*\.recommendation-result-card__cover-fallback\s*\{[^}]*width:\s*100%[^}]*height:\s*100%/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__cover\s*\{[^}]*object-fit:\s*cover/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card \.recommendation-result-card__title\s*\{[^}]*margin:\s*0[^}]*overflow-wrap:\s*anywhere[^}]*font-family:\s*var\(--font-display\)[^}]*text-align:\s*left/
      );
   });

   it("keeps expanded recommendation details visually simple", () => {
      expect(recommendationCss).toMatch(
         /\.recommendation-evidence__list\s*\{[^}]*display:\s*grid[^}]*list-style:\s*none/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-evidence__list li\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\) auto auto[^}]*gap:\s*0\.75rem/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-evidence :is\(h4, h5, h6\)\s*\{[^}]*text-transform:\s*uppercase/
      );
      expect(recommendationCss).toMatch(
         /\.recommendation-result-card__details > summary:focus-visible\s*\{[^}]*outline:\s*none[^}]*box-shadow:\s*inset 0 -3px 0 var\(--color-bone-cream\)/
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
         /\.recommendation-result-card__details\s*\{[^}]*border-top:\s*1px solid var\(--color-ash-taupe\)/
      );
      expect(recommendationCss).not.toMatch(
         /\.recommendation-result-card__details\s*\{[^}]*border-bottom:/
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
         /\.reference-game-card__header\s*\{[^}]*grid-template-columns:\s*6rem minmax\(0,\s*1fr\)/
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
