// @ts-expect-error Vitest runs this contract in Node; app builds exclude Node globals.
import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
   FinalRecommendationItemResponse,
   SessionProfileResponse,
} from "../api";
import RecommendationResultCard from "../features/recommendations/RecommendationResultCard";
import SessionGameLibrary from "../features/session/SessionGameLibrary";

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

const profile: SessionProfileResponse = {
   steam_id: "76561198000000001",
   display_name: longToken,
   profile_url: null,
   avatar_url: null,
   created_at: "2026-09-03T12:00:00Z",
   last_synced_at: null,
   games: [{
      steam_app_id: 620,
      name: longToken,
      icon_url: null,
      playtime_minutes: 120,
      recent_playtime_minutes: null,
      last_played_at: null,
   }],
};

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
      render(
         <SessionGameLibrary
            profile={profile}
            isRefreshing={false}
            refreshError={null}
            refreshSucceeded={false}
            onRefresh={vi.fn().mockResolvedValue(true)}
         />
      );
      expect(screen.getByText(longToken)).toBeInTheDocument();

      render(<RecommendationResultCard item={recommendation} />);
      expect(screen.getByRole("article", { name: longToken }))
         .toBeInTheDocument();
   });

   it("keeps bounded scroll regions and overflow-resistant text at every width", () => {
      expect(appCss).toMatch(/\.app__content[\s\S]*width:\s*min\(100%,\s*42\.5rem\)/);
      expect(sessionCss).toMatch(/\.app__selection strong\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(sessionCss).toMatch(/\.app__game-name\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(sessionCss).toMatch(/\.app__game-list[\s\S]*max-height:\s*32rem[\s\S]*overflow-y:\s*auto/);
      expect(recommendationCss).toMatch(/\.reference-keywords__options[\s\S]*max-height:\s*16rem[\s\S]*overflow-y:\s*auto/);
      expect(recommendationCss).toMatch(/\.reference-game-suggestions span\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(recommendationCss).toMatch(/\.recommendation-result-card__content h3\s*\{[^}]*overflow-wrap:\s*anywhere/);
   });

   it("switches forms, game rows, cards, facts, and evidence to narrow layouts", () => {
      expect(sessionCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.app__session-form[\s\S]*grid-template-columns:\s*1fr/);
      expect(sessionCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.app__game[\s\S]*grid-template-columns:\s*1fr/);
      expect(recommendationCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.recommendation-result-card[\s\S]*grid-template-columns:\s*5rem minmax\(0,\s*1fr\)/);
      expect(recommendationCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.recommendation-result-card__facts[\s\S]*grid-template-columns:\s*1fr/);
      expect(recommendationCss).toMatch(/@media \(max-width:\s*36rem\)[\s\S]*\.recommendation-evidence__list li[\s\S]*grid-template-columns:\s*1fr/);
   });
});
