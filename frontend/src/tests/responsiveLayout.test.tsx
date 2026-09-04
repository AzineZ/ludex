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
      expect(recommendationCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.recommendation-result-card[\s\S]*grid-template-columns:\s*5rem minmax\(0,\s*1fr\)/);
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
});
