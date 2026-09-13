import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
   getAssistantFilterOptions,
   getAssistantGenres,
   getAssistantRecommendations,
   type AssistantRecommendationResponse,
} from "../../api";
import AssistantWorkspace from "../../features/recommendations/assistant/AssistantWorkspace";

vi.mock("../../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../../api")>();

   return {
      ...actual,
      getAssistantFilterOptions: vi.fn(),
      getAssistantGenres: vi.fn(),
      getAssistantRecommendations: vi.fn(),
   };
});

const mockedGenres = vi.mocked(getAssistantGenres);
const mockedFilters = vi.mocked(getAssistantFilterOptions);
const mockedRecommendations = vi.mocked(getAssistantRecommendations);

function rankedResponse(): AssistantRecommendationResponse {
   return {
      status: "ranked",
      eligible_count: 6,
      candidate_limit: 30,
      message: null,
      guided_fallback_available: true,
      items: Array.from({ length: 6 }, (_, index) => ({
         rank: index + 1,
         steam_app_id: 100 + index,
         title: `Game ${index + 1}`,
         cover_url: null,
         profile_playtime_minutes: index * 60,
         normal_completion_seconds: index === 0 ? null : 7_200,
         reason: `AI reason ${index + 1}.`,
         reason_source: "ai_generated" as const,
      })),
   };
}

async function chooseAdventure(): Promise<void> {
   fireEvent.click(await screen.findByRole("button", {
      name: "Adventure, 42 eligible games",
   }));
   await screen.findByRole("group", { name: "Theme filters" });
}

describe("AssistantWorkspace", () => {
   beforeEach(() => {
      mockedGenres.mockReset();
      mockedFilters.mockReset();
      mockedRecommendations.mockReset();
      mockedGenres.mockResolvedValue({
         items: [
            { igdb_id: 31, name: "Adventure", eligible_count: 42 },
            { igdb_id: 12, name: "Role-playing", eligible_count: 18 },
         ],
      });
      mockedFilters.mockResolvedValue({
         themes: [
            { igdb_id: 17, name: "Fantasy", eligible_count: 16 },
            { igdb_id: 18, name: "Science fiction", eligible_count: 9 },
         ],
         game_modes: [
            { igdb_id: 1, name: "Single player", eligible_count: 35 },
         ],
      });
      mockedRecommendations.mockResolvedValue(rankedResponse());
   });

   it("loads profile genres and provider-free filters", async () => {
      render(<AssistantWorkspace sessionEpoch={7} onUseGuided={vi.fn()} />);

      expect(await screen.findByText("Choose a genre from your library"))
         .toBeInTheDocument();
      await chooseAdventure();

      expect(mockedGenres).toHaveBeenCalledOnce();
      expect(mockedFilters).toHaveBeenCalledWith({
         selected_genre_id: 31,
         play_status: "either",
         maximum_completion_minutes: null,
         rejected_steam_app_ids: [],
      });
      expect(screen.getByRole("button", { name: "Fantasy, 16 eligible games" }))
         .toBeInTheDocument();
   });

   it("submits one bounded prompt and runs the returned queue locally", async () => {
      render(<AssistantWorkspace sessionEpoch={7} onUseGuided={vi.fn()} />);
      await chooseAdventure();

      fireEvent.click(screen.getByRole("button", {
         name: "Fantasy, 16 eligible games",
      }));
      fireEvent.change(screen.getByLabelText("What are you in the mood to play?"), {
         target: { value: "Something relaxing after work" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Ask Ludex" }));

      const firstCard = await screen.findByRole("article", { name: "Game 1" });
      expect(mockedRecommendations).toHaveBeenCalledWith({
         prompt: "Something relaxing after work",
         selected_genre_id: 31,
         filters: {
            play_status: "either",
            maximum_completion_minutes: null,
            theme_ids: [17],
            game_mode_ids: [],
         },
         rejected_steam_app_ids: [],
      });
      expect(within(firstCard).getByText("AI-generated reason"))
         .toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(3);

      fireEvent.click(within(firstCard).getByRole("button", {
         name: /show another instead of game 1/i,
      }));

      expect(screen.queryByRole("article", { name: "Game 1" }))
         .not.toBeInTheDocument();
      expect(screen.getByRole("article", { name: "Game 4" }))
         .toBeInTheDocument();
      expect(mockedRecommendations).toHaveBeenCalledOnce();

      fireEvent.click(within(screen.getByRole("article", { name: "Game 2" }))
         .getByRole("button", { name: "Choose Game 2" }));
      expect(screen.getByRole("heading", { name: "Your choice" }))
         .toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(1);
   });

   it("keeps an oversized pool provider-free and asks for factual refinement", async () => {
      mockedRecommendations.mockResolvedValue({
         status: "needs_refinement",
         eligible_count: 42,
         candidate_limit: 30,
         items: [],
         message: "Choose another factual filter so every eligible game can be considered.",
         guided_fallback_available: true,
      });
      render(<AssistantWorkspace sessionEpoch={7} onUseGuided={vi.fn()} />);
      await chooseAdventure();
      fireEvent.change(screen.getByLabelText("What are you in the mood to play?"), {
         target: { value: "Something adventurous" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Ask Ludex" }));

      expect(await screen.findByRole("heading", {
         name: "Narrow your 42-game pool",
      })).toBeInTheDocument();
      expect(screen.getByText(/30-game assistant limit/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Ask Ludex" })).toBeEnabled();
   });

   it("hands unavailable AI requests to the complete guided flow", async () => {
      const onUseGuided = vi.fn();
      mockedRecommendations.mockResolvedValue({
         status: "unavailable",
         eligible_count: 18,
         candidate_limit: 30,
         items: [],
         message: "AI recommendations are temporarily unavailable. Try guided recommendations instead.",
         guided_fallback_available: true,
      });
      render(<AssistantWorkspace sessionEpoch={7} onUseGuided={onUseGuided} />);
      await chooseAdventure();
      fireEvent.change(screen.getByLabelText("What are you in the mood to play?"), {
         target: { value: "Something thoughtful" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Ask Ludex" }));

      expect(await screen.findByRole("heading", {
         name: "AI recommendations unavailable",
      })).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", {
         name: "Use guided recommendations",
      }));
      expect(onUseGuided).toHaveBeenCalledOnce();
   });

   it("ignores genre results from an older access session", async () => {
      let resolveOld!: (value: Awaited<ReturnType<typeof getAssistantGenres>>) => void;
      mockedGenres.mockReturnValueOnce(new Promise((resolve) => {
         resolveOld = resolve;
      }));
      const { rerender } = render(
         <AssistantWorkspace sessionEpoch={7} onUseGuided={vi.fn()} />
      );
      rerender(<AssistantWorkspace sessionEpoch={8} onUseGuided={vi.fn()} />);

      await screen.findByRole("button", { name: "Adventure, 42 eligible games" });
      resolveOld({
         items: [{ igdb_id: 99, name: "Old genre", eligible_count: 1 }],
      });
      await waitFor(() => {
         expect(screen.queryByRole("button", { name: /old genre/i }))
            .not.toBeInTheDocument();
      });
   });
});
