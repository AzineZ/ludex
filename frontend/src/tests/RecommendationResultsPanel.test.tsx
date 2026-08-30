import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
   FinalRecommendationItemResponse,
   FinalRecommendationResponse,
} from "../api";
import RecommendationResultsPanel from "../features/recommendations/RecommendationResultsPanel";


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
});
