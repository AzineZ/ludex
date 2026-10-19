import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { FinalRecommendationItemResponse } from "../../api";
import RecommendationResultCard from "../../features/recommendations/results/RecommendationResultCard";


const recommendation: FinalRecommendationItemResponse = {
   rank: 1,
   steam_app_id: 620,
   title: "Portal 2",
   cover_url: "https://images.example/portal-2.jpg",
   profile_playtime_minutes: 90,
   normal_completion_seconds: 18000,
   ratings: { headline: null, critics: null, total: null },
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

const recommendationWithReasons: FinalRecommendationItemResponse = {
   ...recommendation,
   ratings: {
      headline: { source: "critics", score: 91 },
      critics: { score: 91, count: 12 },
      total: { score: 88, count: 1_204 },
   },
   match_summary: {
      ...recommendation.match_summary,
      reasons: ["Puzzle", "Science fiction", "Co-op", "Physics"].map(
         (name, index) => ({
            facet_kind: "genre" as const,
            facet_igdb_id: index + 1,
            name,
            reference_steam_app_ids: [400],
            points_numerator: 1,
            points_denominator: 1,
         })
      ),
   },
};

function getDetails(card: HTMLElement): HTMLDetailsElement {
   const details = card.querySelector("details");
   if (!(details instanceof HTMLDetailsElement)) {
      throw new Error("Recommendation details were not rendered.");
   }
   return details;
}

function openDetails(card: HTMLElement): HTMLDetailsElement {
   const details = getDetails(card);
   const summary = details.querySelector("summary");
   if (!(summary instanceof HTMLElement)) {
      throw new Error("Recommendation details summary was not rendered.");
   }
   fireEvent.click(summary);
   return details;
}

describe("RecommendationResultCard", () => {
   it("shows the whole cover first, then title, meta, and reason, with no rank label", () => {
      render(<RecommendationResultCard item={recommendationWithReasons} />);

      const card = screen.getByRole("article", { name: "Portal 2" });
      const cover = within(card).getByRole("img", { name: "Portal 2 cover" });
      const body = card.querySelector(".recommendation-result-card__body");
      expect(card).not.toHaveAttribute("data-selection-state");
      expect(card.querySelector(".recommendation-result-card__rank"))
         .not.toBeInTheDocument();
      expect(screen.queryByText(/Recommendation 1/)).not.toBeInTheDocument();
      expect(cover).toHaveAttribute("src", "https://images.example/portal-2.jpg");
      expect(
         cover.compareDocumentPosition(body as Node)
      ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
      expect(body).toContainElement(
         within(card).getByRole("heading", { level: 3, name: "Portal 2" })
      );
      expect(within(card).getByText("Critics 91 · ~5 h · Played 2 h"))
         .toHaveClass("recommendation-result-card__meta");
      expect(within(card).getByText("Matches Puzzle, Science fiction, and Co-op"))
         .toHaveClass("recommendation-result-card__match");
   });

   it("marks an accepted recommendation as the user's persistent pick", () => {
      render(<RecommendationResultCard item={recommendation} isAccepted />);

      const card = screen.getByRole("article", { name: "Portal 2" });
      expect(card).toHaveAttribute("data-selection-state", "accepted");
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
      const details = getDetails(card);
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

      openDetails(card);
      expect(details).toHaveAttribute("open");
   });

   it("keeps the title, facts, and actions in the body above Game details", () => {
      render(
         <RecommendationResultCard
            item={recommendation}
            onPlayThis={vi.fn()}
            onShowAnother={vi.fn()}
            onMoreLikeThis={vi.fn()}
            remainingAlternatives={3}
         />
      );

      const card = screen.getByRole("article", { name: "Portal 2" });
      const body = card.querySelector(".recommendation-result-card__body");
      const details = getDetails(card);

      expect(body).toContainElement(within(card).getByRole("heading", {
         name: "Portal 2",
      }));
      for (const name of [
         "Choose Portal 2",
         "Show another instead of Portal 2. 3 alternatives remaining.",
         "More games like Portal 2",
      ]) {
         expect(body).toContainElement(within(card).getByRole("button", { name }));
      }
      expect(body).not.toContainElement(details);
      expect(
         body?.compareDocumentPosition(details as Node) ?? 0
      ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
   });

   it("uses the requested heading level and nests detail headings below it", () => {
      render(<RecommendationResultCard item={recommendation} headingLevel={5} />);

      const card = screen.getByRole("article", { name: "Portal 2" });
      openDetails(card);
      expect(within(card).getByRole("heading", { level: 5, name: "Portal 2" }))
         .toBeInTheDocument();
      for (const name of ["Why it matches", "Keep in mind", "Preference comparison"]) {
         expect(within(card).getByRole("heading", { level: 6, name }))
            .toBeInTheDocument();
      }
   });

   it("shows a critic, IGDB, or no headline and every score with its count", () => {
      const { rerender } = render(
         <RecommendationResultCard item={recommendationWithReasons} />
      );
      const facts = () => Array.from(
         document.querySelectorAll(".recommendation-result-card__facts dd")
      ).map((value) => value.textContent);

      expect(facts()).toEqual([
         "1 hr 30 min played",
         "5 hr",
         "91/100 from 12 reviews",
         "88/100 from 1,204 ratings",
      ]);

      rerender(
         <RecommendationResultCard
            item={{
               ...recommendationWithReasons,
               ratings: {
                  headline: { source: "total", score: 88 },
                  critics: { score: 40, count: 1 },
                  total: { score: 88, count: 1_204 },
               },
            }}
         />
      );
      expect(screen.getByText("Rated 88 · ~5 h · Played 2 h"))
         .toBeInTheDocument();
      expect(facts()[2]).toBe("40/100 from 1 review");

      rerender(<RecommendationResultCard item={recommendation} />);
      expect(screen.getByText("~5 h · Played 2 h")).toBeInTheDocument();
      expect(facts().slice(2)).toEqual(["No critic reviews", "Not rated"]);
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
               ratings: { headline: null, critics: null, total: null },
               tradeoff: null,
            }}
         />
      );

      expect(
         screen.getByRole("img", { name: "Unknown Game cover unavailable" })
      ).toBeInTheDocument();
      expect(Array.from(document.querySelectorAll(
         ".recommendation-result-card__facts dd"
      )).map((value) => value.textContent)).toEqual([
         "Not played yet",
         "Unavailable",
         "No critic reviews",
         "Not rated",
      ]);
      expect(document.querySelector(".recommendation-result-card__meta"))
         .toHaveTextContent(/^Not played$/);
      expect(document.querySelector(".recommendation-result-card__match"))
         .toHaveTextContent("No selected preferences matched.");
      expect(document.querySelector(
         ".recommendation-result-card__tradeoff"
      )).not.toBeInTheDocument();
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

      openDetails(screen.getByRole("article", { name: "Portal 2" }));
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
      openDetails(screen.getByRole("article", { name: "Portal 2" }));

      expect(screen.queryByText("8765")).not.toBeInTheDocument();
      expect(screen.queryByText("factual-overlap-v1")).not.toBeInTheDocument();
      expect(screen.queryByText("3000")).not.toBeInTheDocument();
      expect(screen.queryByText("400")).not.toBeInTheDocument();
      expect(screen.queryByText("4928")).not.toBeInTheDocument();
   });

   it("explains an honestly empty contribution collection", () => {
      render(<RecommendationResultCard item={recommendation} />);
      openDetails(screen.getByRole("article", { name: "Portal 2" }));

      expect(document.querySelector(".recommendation-evidence"))
         .toBeInTheDocument();
      expect(screen.queryByRole("list")).not.toBeInTheDocument();
   });
});
