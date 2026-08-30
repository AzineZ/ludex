import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { FinalRecommendationItemResponse } from "../api";
import RecommendationResultCard from "../features/recommendations/RecommendationResultCard";


const recommendation: FinalRecommendationItemResponse = {
   rank: 1,
   steam_app_id: 620,
   title: "Portal 2",
   cover_url: "https://images.example/portal-2.jpg",
   profile_playtime_minutes: 90,
   normal_completion_seconds: 18000,
   factual_evidence: {
      version: "factual-overlap-v1",
      score_basis_points: 8765,
      active_budget: 100,
      contributions: [],
   },
   facet_labels: [
      {
         facet_kind: "genre",
         facet_igdb_id: 9,
         name: "Puzzle",
      },
   ],
   match_summary: {
      reasons: [],
      additional_match_count: 0,
      text: "Matches your Puzzle and Science fiction preferences.",
   },
   tradeoff: {
      type: "unmatched_preference",
      reason: {
         facet_kind: "keyword",
         facet_igdb_id: 4928,
         name: "Environmental puzzles",
         reference_steam_app_ids: [400],
      },
      text: "Does not match your Environmental puzzles preference.",
   },
};

describe("RecommendationResultCard", () => {
   it("renders the ranked identity and cached cover", () => {
      render(<RecommendationResultCard item={recommendation} />);

      const card = screen.getByRole("article", { name: "Portal 2" });
      expect(within(card).getByText("Recommendation 1")).toBeInTheDocument();
      expect(
         within(card).getByRole("img", { name: "Portal 2 cover" })
      ).toHaveAttribute("src", "https://images.example/portal-2.jpg");
   });

   it("formats known selected-profile playtime and completion time", () => {
      render(<RecommendationResultCard item={recommendation} />);

      expect(screen.getByText("1 hr 30 min played")).toBeInTheDocument();
      expect(screen.getByText("5 hr")).toBeInTheDocument();
   });

   it("shows the backend match summary and optional tradeoff unchanged", () => {
      render(<RecommendationResultCard item={recommendation} />);

      expect(
         screen.getByText(
            "Matches your Puzzle and Science fiction preferences."
         )
      ).toBeInTheDocument();
      expect(
         screen.getByText(
            "Does not match your Environmental puzzles preference."
         )
      ).toBeInTheDocument();
   });

   it("renders honest fallbacks for zero playtime and missing metadata", () => {
      render(
         <RecommendationResultCard
            item={{
               ...recommendation,
               rank: 2,
               title: "Unknown Game",
               cover_url: null,
               profile_playtime_minutes: 0,
               normal_completion_seconds: null,
               tradeoff: null,
            }}
         />
      );

      expect(
         screen.getByRole("img", { name: "Unknown Game cover unavailable" })
      ).toHaveTextContent("Cover unavailable");
      expect(screen.getByText("Not played yet")).toBeInTheDocument();
      expect(screen.getByText("Unavailable")).toBeInTheDocument();
      expect(screen.queryByText("Keep in mind")).not.toBeInTheDocument();
   });

   it("does not expose raw scoring evidence or inactive controls", () => {
      render(<RecommendationResultCard item={recommendation} />);

      expect(screen.queryByText("8765")).not.toBeInTheDocument();
      expect(screen.queryByText("factual-overlap-v1")).not.toBeInTheDocument();
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
   });
});
