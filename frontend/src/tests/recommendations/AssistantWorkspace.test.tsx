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
      candidate_limit: 400,
      message: null,
      guided_fallback_available: true,
      items: Array.from({ length: 6 }, (_, index) => ({
         rank: index + 1,
         steam_app_id: 100 + index,
         title: `Game ${index + 1}`,
         cover_url: null,
         profile_playtime_minutes: index * 60,
         normal_completion_seconds: index === 0 ? null : 7_200,
         summary: `Game summary ${index + 1}.`,
         reasoning: `It matches your request for relaxing play ${index + 1}.`,
         content_source: "ai_generated" as const,
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
      mockedFilters.mockImplementation(async (context) => ({
         eligible_count: context.theme_ids.includes(17) ? 16 : 42,
         candidate_limit: 400,
         themes: [
            { igdb_id: 17, name: "Fantasy", eligible_count: 16 },
            { igdb_id: 18, name: "Science fiction", eligible_count: 9 },
         ],
         game_modes: [
            { igdb_id: 1, name: "Single player", eligible_count: 35 },
         ],
      }));
      mockedRecommendations.mockResolvedValue(rankedResponse());
   });

   it("loads profile genres and provider-free filters", async () => {
      render(<AssistantWorkspace sessionEpoch={7} onUseGuided={vi.fn()} />);

      const navigation = screen.getByRole("navigation", {
         name: "AI recommendation workspace",
      });
      expect(within(navigation).getByRole("button", { name: "Prompt" }))
         .toHaveAttribute("aria-current", "page");
      expect(within(navigation).getByRole("button", {
         name: "AI results",
      })).toBeDisabled();
      await chooseAdventure();

      expect(mockedGenres).toHaveBeenCalledOnce();
      expect(mockedFilters).toHaveBeenCalledWith({
         selected_genre_id: 31,
         play_status: "either",
         maximum_completion_minutes: null,
         theme_ids: [],
         game_mode_ids: [],
         rejected_steam_app_ids: [],
      });
      expect(screen.getByText("42")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Fantasy, 16 eligible games" }))
         .toBeInTheDocument();
      fireEvent.click(screen.getByText("Narrow your results"));
      expect(screen.getByRole("button", { name: "Either" }))
         .toHaveAttribute("aria-pressed", "true");
   });

   it("submits one bounded prompt and runs the returned queue locally", async () => {
      render(<AssistantWorkspace sessionEpoch={7} onUseGuided={vi.fn()} />);
      await chooseAdventure();

      fireEvent.click(screen.getByRole("button", {
         name: "Fantasy, 16 eligible games",
      }));
      expect(await screen.findByText("16")).toBeInTheDocument();
      expect(mockedFilters).toHaveBeenLastCalledWith({
         selected_genre_id: 31,
         play_status: "either",
         maximum_completion_minutes: null,
         theme_ids: [17],
         game_mode_ids: [],
         rejected_steam_app_ids: [],
      });
      expect(mockedRecommendations).not.toHaveBeenCalled();
      fireEvent.change(screen.getByLabelText("What are you in the mood to play?"), {
         target: { value: "Something relaxing after work" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Ask Ludex" }));

      const firstCard = await screen.findByRole("article", { name: "Game 1" });
      await waitFor(() => {
         expect(screen.getByRole("region", {
            name: "Your AI recommendations",
         })).toHaveFocus();
      });
      const navigation = screen.getByRole("navigation", {
         name: "AI recommendation workspace",
      });
      expect(within(navigation).getByRole("button", {
         name: "AI results",
      })).toHaveAttribute("aria-current", "page");
      expect(within(navigation).getByRole("button", { name: "Prompt" }))
         .toBeEnabled();
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
      expect(within(firstCard).getByText("Game summary 1."))
         .toBeInTheDocument();
      expect(within(firstCard).getByText(
         "It matches your request for relaxing play 1."
      )).toBeInTheDocument();
      expect(within(firstCard).getByRole("region", {
         name: "Game 1 summary",
      })).toHaveClass("assistant-result-card__scroll-region");
      expect(within(firstCard).getByRole("region", {
         name: "Game 1 reasoning",
      })).toHaveClass("assistant-result-card__scroll-region");
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
         eligible_count: 242,
         candidate_limit: 400,
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

      expect(await screen.findByRole("status")).toBeInTheDocument();
      expect(screen.queryByRole("article")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Ask Ludex" })).toBeEnabled();
   });

   it("hands unavailable AI requests to the complete guided flow", async () => {
      const onUseGuided = vi.fn();
      mockedRecommendations.mockResolvedValue({
         status: "unavailable",
         eligible_count: 18,
         candidate_limit: 400,
         items: [],
         message: "Ludex AI has reached Gemini's current usage limit. Please try again tomorrow, or use guided recommendations now.",
         diagnostic_reference: "GEM-1A2B3C4D5E6F",
         guided_fallback_available: true,
      });
      render(<AssistantWorkspace sessionEpoch={7} onUseGuided={onUseGuided} />);
      await chooseAdventure();
      fireEvent.change(screen.getByLabelText("What are you in the mood to play?"), {
         target: { value: "Something thoughtful" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Ask Ludex" }));

      await waitFor(() => {
         expect(document.querySelector(".assistant-state--error"))
            .toHaveAttribute("role", "status");
      });
      expect(screen.getByText("GEM-1A2B3C4D5E6F")).toBeInTheDocument();
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
