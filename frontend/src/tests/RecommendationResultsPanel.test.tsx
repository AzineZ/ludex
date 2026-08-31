import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
   FinalRecommendationItemResponse,
   FinalRecommendationResponse,
   RecommendationPreference,
} from "../api";
import RecommendationResultsPanel from "../features/recommendations/RecommendationResultsPanel";
import {
   acceptRecommendation,
   createRecommendationSession,
} from "../features/recommendations/recommendationSession";


const preference: RecommendationPreference = {
   references: [
      {
         steam_app_id: 100,
         facets: {
            genre_ids: [10],
            theme_ids: [],
            keyword_ids: [],
            game_mode_ids: [],
         },
      },
   ],
   constraints: {
      maximum_completion_minutes: null,
      play_status: "either",
   },
};

function recommendationItem(rank: number): FinalRecommendationItemResponse {
   return {
      rank,
      steam_app_id: 1000 + rank,
      title: `Game ${rank}`,
      cover_url: null,
      profile_playtime_minutes: 0,
      normal_completion_seconds: null,
      factual_evidence: {
         version: "factual-overlap-v1",
         score_basis_points: 10000 - rank,
         active_budget: 100,
         contributions: [],
      },
      facet_labels: [],
      match_summary: {
         reasons: [],
         additional_match_count: 0,
         text: `Game ${rank} matches your selected preferences.`,
      },
      tradeoff: null,
   };
}

function recommendationResponse(
   outcome: FinalRecommendationResponse["outcome"],
   itemCount: number
): FinalRecommendationResponse {
   return {
      outcome,
      eligible_count: itemCount,
      returned_count: itemCount,
      items: Array.from({ length: itemCount }, (_, index) => (
         recommendationItem(index + 1)
      )),
   };
}

describe("RecommendationResultsPanel", () => {
   it("renders nothing before a recommendation request begins", () => {
      const { container } = render(
         <RecommendationResultsPanel
            status="idle"
            response={null}
            error={null}
         />
      );

      expect(container).toBeEmptyDOMElement();
   });

   it("announces the exact loading state", () => {
      render(
         <RecommendationResultsPanel
            status="loading"
            response={null}
            error={null}
         />
      );

      expect(screen.getByRole("status")).toHaveTextContent(
         "Finding recommendations in your cached library…"
      );
   });

   it("renders the top three complete results and keeps waiting games hidden", () => {
      render(
         <RecommendationResultsPanel
            status="ready"
            response={recommendationResponse("complete", 6)}
            error={null}
         />
      );

      expect(
         screen.getByRole("region", { name: "Your recommendations" })
      ).toHaveAttribute("aria-live", "polite");
      expect(screen.getByRole("status")).toHaveTextContent(
         "6 recommendations found. Showing the top 3."
      );
      expect(screen.getAllByRole("article")).toHaveLength(3);
      expect(screen.getByRole("article", { name: "Game 1" })).toBeInTheDocument();
      expect(screen.getByRole("article", { name: "Game 3" })).toBeInTheDocument();
      expect(screen.queryByText("Game 4")).not.toBeInTheDocument();
   });

   it("reports and renders every sparse result", () => {
      render(
         <RecommendationResultsPanel
            status="ready"
            response={recommendationResponse("sparse", 2)}
            error={null}
         />
      );

      expect(screen.getByRole("status")).toHaveTextContent(
         "2 recommendations found."
      );
      expect(screen.getAllByRole("article")).toHaveLength(2);
   });

   it("uses singular sparse-count wording", () => {
      render(
         <RecommendationResultsPanel
            status="ready"
            response={recommendationResponse("sparse", 1)}
            error={null}
         />
      );

      expect(screen.getByRole("status")).toHaveTextContent(
         "1 recommendation found."
      );
   });

   it("treats an empty outcome as success with refinement guidance", () => {
      render(
         <RecommendationResultsPanel
            status="ready"
            response={recommendationResponse("empty", 0)}
            error={null}
         />
      );

      const status = screen.getByRole("status");
      expect(status).toHaveTextContent("No recommendations found.");
      expect(status).toHaveTextContent(
         "No owned games match these preferences. Try changing your "
         + "reference games, selected facets, or constraints."
      );
      expect(screen.queryByRole("article")).not.toBeInTheDocument();
   });

   it("preserves an actionable backend error and the current draft", () => {
      render(
         <RecommendationResultsPanel
            status="error"
            response={null}
            error="The selected preference is no longer valid."
         />
      );

      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent("Recommendations unavailable");
      expect(alert).toHaveTextContent(
         "The selected preference is no longer valid."
      );
      expect(alert).toHaveTextContent(
         "Your preference choices are still here. Try again when you’re ready."
      );
   });

   it("uses exact fallback copy for an unexpected missing error", () => {
      render(
         <RecommendationResultsPanel
            status="error"
            response={null}
            error={null}
         />
      );

      expect(screen.getByRole("alert")).toHaveTextContent(
         "Something went wrong while loading recommendations."
      );
   });

   it("renders the browser-local queue and identifies each chosen action", () => {
      const response = recommendationResponse("complete", 6);
      const session = createRecommendationSession(preference, response.items);
      const onShowAnother = vi.fn();
      const onPlayThis = vi.fn();
      const onStartOver = vi.fn();

      render(
         <RecommendationResultsPanel
            status="ready"
            response={response}
            error={null}
            session={session}
            onShowAnother={onShowAnother}
            onPlayThis={onPlayThis}
            onStartOver={onStartOver}
         />
      );

      const gameTwo = screen.getByRole("article", { name: "Game 2" });
      fireEvent.click(
         within(gameTwo).getByRole("button", { name: "Show another" })
      );
      fireEvent.click(
         within(gameTwo).getByRole("button", { name: "Play this" })
      );
      fireEvent.click(screen.getByRole("button", { name: "Start over" }));

      expect(onShowAnother).toHaveBeenCalledWith(1002);
      expect(onPlayThis).toHaveBeenCalledWith(1002);
      expect(onStartOver).toHaveBeenCalledOnce();
      expect(screen.queryByText("Game 4")).not.toBeInTheDocument();
   });

   it("keeps Play this available and explains an exhausted bounded queue", () => {
      const response = recommendationResponse("complete", 3);
      const session = createRecommendationSession(preference, response.items);

      render(
         <RecommendationResultsPanel
            status="ready"
            response={response}
            error={null}
            session={session}
            onShowAnother={vi.fn()}
            onPlayThis={vi.fn()}
            onStartOver={vi.fn()}
         />
      );

      expect(screen.getAllByRole("button", { name: "Show another" }))
         .toHaveLength(3);
      for (const button of screen.getAllByRole("button", {
         name: "Show another",
      })) {
         expect(button).toBeDisabled();
      }
      expect(screen.getAllByRole("button", { name: "Play this" }))
         .toHaveLength(3);
      expect(screen.getByRole("status")).toHaveTextContent(
         "You’ve seen every recommendation in this bounded queue. "
         + "Choose a game, refine your preferences, or start over."
      );
   });

   it("shows only the accepted game as the terminal Play this state", () => {
      const response = recommendationResponse("sparse", 2);
      const activeSession = createRecommendationSession(
         preference,
         response.items
      );
      const session = acceptRecommendation(activeSession, 1002);

      render(
         <RecommendationResultsPanel
            status="ready"
            response={response}
            error={null}
            session={session}
            onShowAnother={vi.fn()}
            onPlayThis={vi.fn()}
            onStartOver={vi.fn()}
         />
      );

      expect(screen.getByRole("status")).toHaveTextContent(
         "You chose Game 2."
      );
      expect(screen.getAllByRole("article")).toHaveLength(1);
      expect(screen.getByRole("article", { name: "Game 2" }))
         .toBeInTheDocument();
      expect(screen.queryByText("Game 1")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Play this" }))
         .not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Show another" }))
         .not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Start over" }))
         .toBeEnabled();
   });
});
