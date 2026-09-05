import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

const recommendationWithEvidence: FinalRecommendationItemResponse = {
   ...recommendation,
   factual_evidence: {
      ...recommendation.factual_evidence,
      contributions: [
         {
            reference_steam_app_id: 400,
            facet_kind: "genre",
            facet_igdb_id: 9,
            match_state: "matched",
            points_numerator: 3000,
            points_denominator: 1,
         },
         {
            reference_steam_app_id: 400,
            facet_kind: "keyword",
            facet_igdb_id: 4928,
            match_state: "not_matched",
            points_numerator: 0,
            points_denominator: 1,
         },
         {
            reference_steam_app_id: 500,
            facet_kind: "game_mode",
            facet_igdb_id: 44,
            match_state: "unknown",
            points_numerator: 0,
            points_denominator: 1,
         },
      ],
   },
   facet_labels: [
      ...recommendation.facet_labels,
      {
         facet_kind: "keyword",
         facet_igdb_id: 4928,
         name: "Environmental puzzles",
      },
      {
         facet_kind: "game_mode",
         facet_igdb_id: 44,
         name: "Single player",
      },
   ],
};

describe("RecommendationResultCard", () => {
   it("renders the ranked identity and cached cover", () => {
      render(<RecommendationResultCard item={recommendation} />);

      const card = screen.getByRole("article", { name: "Portal 2" });
      expect(card).not.toHaveAttribute("data-selection-state");
      expect(within(card).getByText("Recommendation 1")).toBeInTheDocument();
      expect(
         within(card).getByRole("img", { name: "Portal 2 cover" })
      ).toHaveAttribute("src", "https://images.example/portal-2.jpg");
   });

   it("marks an accepted recommendation as the user's persistent pick", () => {
      render(<RecommendationResultCard item={recommendation} isAccepted />);

      const card = screen.getByRole("article", { name: "Portal 2" });
      expect(card).toHaveAttribute("data-selection-state", "accepted");
      expect(within(card).getByText("Your pick")).toBeInTheDocument();
      expect(within(card).queryByText("Recommendation 1")).not.toBeInTheDocument();
   });

   it("requests a sharper IGDB cover without rewriting other image hosts", () => {
      const { rerender } = render(
         <RecommendationResultCard
            item={{
               ...recommendation,
               cover_url:
                  "https://images.igdb.com/igdb/image/upload/t_cover_big/coay61.jpg",
            }}
         />
      );

      expect(screen.getByRole("img", { name: "Portal 2 cover" })).toHaveAttribute(
         "src",
         "https://images.igdb.com/igdb/image/upload/t_cover_big_2x/coay61.jpg"
      );

      rerender(<RecommendationResultCard item={recommendation} />);
      expect(screen.getByRole("img", { name: "Portal 2 cover" })).toHaveAttribute(
         "src",
         "https://images.example/portal-2.jpg"
      );
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

   it("keeps decision essentials outside one collapsed secondary-details area", () => {
      render(
         <RecommendationResultCard
            item={recommendation}
            onPlayThis={vi.fn()}
            onShowAnother={vi.fn()}
            remainingAlternatives={3}
         />
      );

      const card = screen.getByRole("article", { name: "Portal 2" });
      const details = within(card).getByText("Game details").closest("details");
      const actions = card.querySelector(".recommendation-result-card__actions");
      expect(details).not.toHaveAttribute("open");
      expect(within(card).getByText(
         "Matches your Puzzle and Science fiction preferences."
      )).toBeInTheDocument();
      expect(within(card).getByRole("button", { name: "Choose Portal 2" }))
         .toBeInTheDocument();
      expect(within(card).getByRole("button", {
         name: "Show another instead of Portal 2. 3 alternatives remaining.",
      })).toBeInTheDocument();
      expect(details).toContainElement(within(card).getByText("1 hr 30 min played"));
      expect(details).toContainElement(within(card).getByText("5 hr"));
      expect(details).toContainElement(within(card).getByText(
         "Does not match your Environmental puzzles preference."
      ));
      expect(
         actions?.compareDocumentPosition(details as Node)
         ?? 0
      ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

      fireEvent.click(within(card).getByText("Game details"));
      expect(details).toHaveAttribute("open");
   });

   it("keeps the primary card layout in a fixed stage above expanding details", () => {
      render(
         <RecommendationResultCard
            item={recommendation}
            onPlayThis={vi.fn()}
            onShowAnother={vi.fn()}
            remainingAlternatives={3}
         />
      );

      const card = screen.getByRole("article", { name: "Portal 2" });
      const stage = card.querySelector(".recommendation-result-card__stage");
      const details = within(card).getByText("Game details").closest("details");

      expect(stage).toContainElement(within(card).getByRole("heading", {
         name: "Portal 2",
      }));
      expect(stage).toContainElement(within(card).getByRole("button", {
         name: "Choose Portal 2",
      }));
      expect(stage).not.toContainElement(details);
      expect(
         stage?.compareDocumentPosition(details as Node) ?? 0
      ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
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

   it("offers explicit Choose this game and Show another session actions", () => {
      const onPlayThis = vi.fn();
      const onShowAnother = vi.fn();

      render(
         <RecommendationResultCard
            item={recommendation}
            onPlayThis={onPlayThis}
            onShowAnother={onShowAnother}
            remainingAlternatives={3}
         />
      );

      fireEvent.click(screen.getByRole("button", { name: "Choose Portal 2" }));
      fireEvent.click(screen.getByRole("button", {
         name: "Show another instead of Portal 2. 3 alternatives remaining.",
      }));

      expect(onPlayThis).toHaveBeenCalledOnce();
      expect(onShowAnother).toHaveBeenCalledOnce();
   });

   it("gives repeated recommendation actions game-specific accessible names", () => {
      render(
         <RecommendationResultCard
            item={recommendation}
            onPlayThis={vi.fn()}
            onShowAnother={vi.fn()}
            remainingAlternatives={1}
         />
      );

      expect(screen.getByRole("button", { name: "Choose Portal 2" }))
         .toHaveTextContent("Choose this game");
      expect(screen.getByRole("button", {
         name: "Show another instead of Portal 2. 1 alternative remaining.",
      })).toHaveTextContent("Show another · 1 left");
   });

   it("disables Show another when the bounded waiting queue is exhausted", () => {
      render(
         <RecommendationResultCard
            item={recommendation}
            onPlayThis={vi.fn()}
            onShowAnother={vi.fn()}
            showAnotherDisabled
            remainingAlternatives={0}
         />
      );

      expect(
         screen.getByRole("button", {
            name: "Show another instead of Portal 2. No alternatives remaining.",
         })
      ).toBeDisabled();
      expect(screen.getByRole("button", { name: "Choose Portal 2" })).toBeEnabled();
   });

   it("discloses authoritative contribution labels and states in backend order", () => {
      render(<RecommendationResultCard item={recommendationWithEvidence} />);

      fireEvent.click(screen.getByText("Game details"));
      expect(screen.getByRole("heading", { name: "Preference comparison" }))
         .toBeInTheDocument();
      expect(screen.queryByText("Why this game?")).not.toBeInTheDocument();
      expect(screen.getAllByRole("listitem").map((item) => item.textContent))
         .toEqual([
            "PuzzleGenreMatched",
            "Environmental puzzlesKeywordDid not match",
            "Single playerGame modeMetadata unavailable",
         ]);
   });

   it("keeps raw scoring and provider identities out of the disclosure", () => {
      render(<RecommendationResultCard item={recommendationWithEvidence} />);
      fireEvent.click(screen.getByText("Game details"));

      expect(screen.queryByText("8765")).not.toBeInTheDocument();
      expect(screen.queryByText("factual-overlap-v1")).not.toBeInTheDocument();
      expect(screen.queryByText("3000")).not.toBeInTheDocument();
      expect(screen.queryByText("400")).not.toBeInTheDocument();
      expect(screen.queryByText("4928")).not.toBeInTheDocument();
   });

   it("explains an honestly empty contribution collection", () => {
      render(<RecommendationResultCard item={recommendation} />);
      fireEvent.click(screen.getByText("Game details"));

      expect(screen.getByText(
         "No factual contribution details are available for this comparison."
      )).toBeInTheDocument();
      expect(screen.queryByRole("list")).not.toBeInTheDocument();
   });
});
