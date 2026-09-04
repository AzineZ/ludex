import {
   fireEvent,
   render,
   screen,
   waitFor,
   within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
   getFinalRecommendations,
   refineFinalRecommendations,
   validateRecommendationPreference,
   type FinalRecommendationResponse,
   type RecommendationPreference,
} from "../api";
import PreferenceValidationPanel from "../features/recommendations/PreferenceValidationPanel";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();

   return {
      ...actual,
      getFinalRecommendations: vi.fn(),
      refineFinalRecommendations: vi.fn(),
      validateRecommendationPreference: vi.fn(),
   };
});

type Deferred<Value> = {
   promise: Promise<Value>;
   resolve: (value: Value) => void;
};

const draft: RecommendationPreference = {
   references: [
      {
         steam_app_id: 100,
         facets: {
            genre_ids: [11],
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

const canonicalPreference: RecommendationPreference = {
   ...draft,
   constraints: {
      maximum_completion_minutes: 1800,
      play_status: "unplayed",
   },
};

const refinedDraft: RecommendationPreference = {
   ...draft,
   constraints: {
      maximum_completion_minutes: 1200,
      play_status: "either",
   },
};

const refinedCanonicalPreference: RecommendationPreference = {
   ...refinedDraft,
   constraints: {
      maximum_completion_minutes: 1200,
      play_status: "unplayed",
   },
};

const response: FinalRecommendationResponse = {
   outcome: "sparse",
   eligible_count: 1,
   returned_count: 1,
   items: [
      {
         rank: 1,
         steam_app_id: 620,
         title: "Portal 2",
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
            text: "Matches your Puzzle preference.",
         },
         tradeoff: null,
      },
   ],
};

const completeResponse: FinalRecommendationResponse = {
   outcome: "complete",
   eligible_count: 4,
   returned_count: 4,
   items: Array.from({ length: 4 }, (_, index) => ({
      ...response.items[0],
      rank: index + 1,
      steam_app_id: 620 + index,
      title: index === 0 ? "Portal 2" : `Game ${index + 1}`,
   })),
};

const sixItemResponse: FinalRecommendationResponse = {
   outcome: "complete",
   eligible_count: 6,
   returned_count: 6,
   items: Array.from({ length: 6 }, (_, index) => ({
      ...response.items[0],
      rank: index + 1,
      steam_app_id: 620 + index,
      title: index === 0 ? "Portal 2" : `Game ${index + 1}`,
   })),
};

const refinedResponse: FinalRecommendationResponse = {
   outcome: "sparse",
   eligible_count: 2,
   returned_count: 2,
   items: Array.from({ length: 2 }, (_, index) => ({
      ...response.items[0],
      rank: index + 1,
      steam_app_id: 700 + index,
      title: `Refined Game ${index + 1}`,
   })),
};

const mockedValidate = vi.mocked(validateRecommendationPreference);
const mockedGetRecommendations = vi.mocked(getFinalRecommendations);
const mockedRefineRecommendations = vi.mocked(refineFinalRecommendations);

function deferred<Value>(): Deferred<Value> {
   let resolve!: (value: Value) => void;
   const promise = new Promise<Value>((resolvePromise) => {
      resolve = resolvePromise;
   });

   return { promise, resolve };
}

async function completeWorkflow(): Promise<void> {
   fireEvent.click(
      screen.getByRole("button", { name: "Get recommendations" })
   );
   await screen.findByRole(
      "article",
      { name: "Portal 2" },
      { timeout: 5000 }
   );
}

describe("preference recommendation workflow", () => {
   beforeEach(() => {
      mockedValidate.mockReset();
      mockedGetRecommendations.mockReset();
      mockedRefineRecommendations.mockReset();
      mockedValidate.mockResolvedValue(canonicalPreference);
      mockedGetRecommendations.mockResolvedValue(response);
      mockedRefineRecommendations.mockResolvedValue(refinedResponse);
   });

   it("submits only the canonical preference and renders its result", async () => {
      render(<PreferenceValidationPanel sessionEpoch={7} preference={draft} />);

      expect(
         screen.getByRole("button", { name: "Get recommendations" })
      ).toBeEnabled();

      await completeWorkflow();

      expect(mockedValidate).toHaveBeenCalledWith(draft);
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
      expect(mockedGetRecommendations).toHaveBeenCalledWith(
         canonicalPreference
      );
      expect(screen.getByText("1 recommendation found.")).toBeInTheDocument();
      await waitFor(
         () => {
            expect(screen.getByRole("article", { name: "Portal 2" }))
               .toHaveFocus();
         },
         { timeout: 5000 }
      );
   });

   it("preserves the draft and retries preference validation", async () => {
      mockedValidate
         .mockRejectedValueOnce(new Error("Validation temporarily unavailable."))
         .mockResolvedValueOnce(canonicalPreference);
      render(<PreferenceValidationPanel sessionEpoch={7} preference={draft} />);

      fireEvent.click(
         screen.getByRole("button", { name: "Get recommendations" })
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Validation temporarily unavailable."
      );
      expect(screen.queryByText(/steam_app_id/)).toBeNull();

      fireEvent.click(
         screen.getByRole("button", { name: "Get recommendations" })
      );
      await screen.findByRole("article", { name: "Portal 2" });
      expect(mockedValidate).toHaveBeenCalledTimes(2);
   });

   it("preserves preference controls and retries an initial recommendation failure", async () => {
      mockedGetRecommendations
         .mockRejectedValueOnce(new Error("Recommendations are temporarily unavailable."))
         .mockResolvedValueOnce(response);
      render(<PreferenceValidationPanel sessionEpoch={7} preference={draft} />);

      fireEvent.click(screen.getByRole("button", { name: "Get recommendations" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Recommendations are temporarily unavailable."
      );
      expect(screen.queryByText(/steam_app_id/)).toBeNull();
      fireEvent.click(
         screen.getByRole("button", { name: "Try recommendations again" })
      );

      await screen.findByRole("article", { name: "Portal 2" });
      expect(mockedGetRecommendations).toHaveBeenCalledTimes(2);
   });

   it("locks and announces recommendation submission while it is pending", async () => {
      const pendingRequest = deferred<FinalRecommendationResponse>();
      mockedGetRecommendations.mockReturnValue(pendingRequest.promise);
      render(<PreferenceValidationPanel sessionEpoch={7} preference={draft} />);

      fireEvent.click(
         screen.getByRole("button", { name: "Get recommendations" })
      );

      expect(
         screen.getByRole("button", { name: "Checking preferences…" })
      ).toBeDisabled();
      expect(
         await screen.findByRole("button", { name: "Finding recommendations…" })
      ).toBeDisabled();
      expect(
         screen.getByText("Finding recommendations in your cached library…")
      ).toHaveAttribute("role", "status");
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();

      pendingRequest.resolve(response);
      await screen.findByRole("article", { name: "Portal 2" });
   });

   it("invalidates validation but retains results when the draft changes", async () => {
      const { rerender } = render(
         <PreferenceValidationPanel sessionEpoch={7} preference={draft} />
      );
      await completeWorkflow();

      rerender(
         <PreferenceValidationPanel
            sessionEpoch={7}
            preference={{
               ...draft,
               constraints: {
                  ...draft.constraints,
                  play_status: "previously_played",
               },
            }}
         />
      );

      expect(screen.getByRole("article", { name: "Portal 2" }))
         .toBeInTheDocument();
      await waitFor(() => {
         expect(
            screen.getByRole("button", { name: "Refine recommendations" })
         ).toBeEnabled();
      });
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
   });

   it("invalidates validation and results when the profile changes", async () => {
      const { rerender } = render(
         <PreferenceValidationPanel sessionEpoch={7} preference={draft} />
      );
      await completeWorkflow();

      rerender(
         <PreferenceValidationPanel sessionEpoch={8} preference={draft} />
      );

      await waitFor(() => {
         expect(screen.queryByRole("article", { name: "Portal 2" })).toBeNull();
      });
      expect(
         screen.getByRole("button", { name: "Get recommendations" })
      ).toBeEnabled();
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
   });

   it("owns Show another, Play this, and Start over without another request", async () => {
      mockedGetRecommendations.mockResolvedValue(completeResponse);
      render(<PreferenceValidationPanel sessionEpoch={7} preference={draft} />);
      await completeWorkflow();

      const portalCard = screen.getByRole("article", { name: "Portal 2" });
      const showAnotherButton = within(portalCard).getByRole("button", {
         name: /^Show another instead of/,
      });
      showAnotherButton.focus();
      fireEvent.click(showAnotherButton);

      expect(screen.queryByRole("article", { name: "Portal 2" })).toBeNull();
      const replacementCard = screen.getByRole("article", { name: "Game 4" });
      expect(replacementCard).toHaveFocus();
      for (const button of screen.getAllByRole("button", {
         name: /^Show another instead of/,
      })) {
         expect(button).toBeDisabled();
      }
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();

      const gameTwoCard = screen.getByRole("article", { name: "Game 2" });
      const playThisButton = within(gameTwoCard).getByRole("button", {
         name: "Play Game 2",
      });
      playThisButton.focus();
      fireEvent.click(playThisButton);

      expect(screen.getByText("You chose Game 2.")).toHaveAttribute(
         "role",
         "status"
      );
      const acceptedCard = screen.getByRole("article", { name: "Game 2" });
      expect(acceptedCard).toHaveFocus();
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();

      fireEvent.click(screen.getByRole("button", { name: "Start over" }));

      expect(screen.queryByRole("article")).not.toBeInTheDocument();
      expect(
         screen.getByRole("button", { name: "Get recommendations" })
      ).toHaveFocus();
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
   });

   it("retains the queue while editing and refines with rejected IDs", async () => {
      mockedGetRecommendations.mockResolvedValue(completeResponse);
      const { rerender } = render(
         <PreferenceValidationPanel sessionEpoch={7} preference={draft} />
      );
      await completeWorkflow();

      const portalCard = screen.getByRole("article", { name: "Portal 2" });
      fireEvent.click(
         within(portalCard).getByRole("button", {
            name: "Show another instead of Portal 2",
         })
      );
      expect(screen.getByRole("article", { name: "Game 4" }))
         .toBeInTheDocument();

      rerender(
         <PreferenceValidationPanel sessionEpoch={7} preference={refinedDraft} />
      );

      expect(screen.getByRole("article", { name: "Game 4" }))
         .toBeInTheDocument();
      expect(screen.queryByRole("article", { name: "Portal 2" })).toBeNull();

      mockedValidate.mockResolvedValueOnce(refinedCanonicalPreference);
      fireEvent.click(
         screen.getByRole("button", { name: "Refine recommendations" })
      );

      await screen.findByRole("article", { name: "Refined Game 1" });
      await waitFor(
         () => {
            expect(screen.getByRole("article", { name: "Refined Game 1" }))
               .toHaveFocus();
         },
         { timeout: 5000 }
      );
      expect(mockedRefineRecommendations).toHaveBeenCalledOnce();
      expect(mockedRefineRecommendations).toHaveBeenCalledWith(
         refinedCanonicalPreference,
         [620]
      );
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
      expect(screen.queryByRole("article", { name: "Game 4" })).toBeNull();
   });

   it("preserves the queue when edited preferences fail validation", async () => {
      mockedGetRecommendations.mockResolvedValue(completeResponse);
      const { rerender } = render(
         <PreferenceValidationPanel sessionEpoch={7} preference={draft} />
      );
      await completeWorkflow();
      fireEvent.click(
         within(screen.getByRole("article", { name: "Portal 2" }))
            .getByRole("button", { name: /^Show another instead of/ })
      );

      rerender(
         <PreferenceValidationPanel sessionEpoch={7} preference={refinedDraft} />
      );
      mockedValidate.mockRejectedValueOnce(
         new Error("The edited preference is invalid.")
      );
      fireEvent.click(
         screen.getByRole("button", { name: "Refine recommendations" })
      );

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "The edited preference is invalid."
      );
      expect(screen.getByRole("article", { name: "Game 4" }))
         .toBeInTheDocument();
      expect(screen.queryByRole("article", { name: "Portal 2" })).toBeNull();
      expect(mockedRefineRecommendations).not.toHaveBeenCalled();
   });

   it("preserves rejected history and the queue when refinement is retried", async () => {
      mockedGetRecommendations.mockResolvedValue(completeResponse);
      const { rerender } = render(
         <PreferenceValidationPanel sessionEpoch={7} preference={draft} />
      );
      await completeWorkflow();
      fireEvent.click(
         within(screen.getByRole("article", { name: "Portal 2" }))
            .getByRole("button", { name: /^Show another instead of/ })
      );
      rerender(
         <PreferenceValidationPanel sessionEpoch={7} preference={refinedDraft} />
      );
      mockedValidate.mockResolvedValueOnce(refinedCanonicalPreference);
      mockedRefineRecommendations.mockRejectedValueOnce(
         new Error("Refinement temporarily unavailable.")
      );

      fireEvent.click(
         screen.getByRole("button", { name: "Refine recommendations" })
      );

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Refinement temporarily unavailable."
      );
      expect(screen.getByRole("article", { name: "Game 4" }))
         .toBeInTheDocument();
      expect(screen.queryByRole("article", { name: "Portal 2" })).toBeNull();

      fireEvent.click(
         screen.getByRole("button", { name: "Try refinement again" })
      );

      await screen.findByRole("article", { name: "Refined Game 1" });
      expect(mockedRefineRecommendations).toHaveBeenCalledTimes(2);
      expect(mockedRefineRecommendations).toHaveBeenNthCalledWith(
         1,
         refinedCanonicalPreference,
         [620]
      );
      expect(mockedRefineRecommendations).toHaveBeenNthCalledWith(
         2,
         refinedCanonicalPreference,
         [620]
      );
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
   });

   it("consumes the complete queue once and refines with every rejection", async () => {
      mockedGetRecommendations.mockResolvedValue(sixItemResponse);
      const { rerender } = render(
         <PreferenceValidationPanel sessionEpoch={7} preference={draft} />
      );
      await completeWorkflow();

      for (const [rejectedTitle, replacementTitle] of [
         ["Portal 2", "Game 4"],
         ["Game 4", "Game 5"],
         ["Game 5", "Game 6"],
      ]) {
         const rejectedCard = screen.getByRole("article", {
            name: rejectedTitle,
         });
         fireEvent.click(
            within(rejectedCard).getByRole("button", {
               name: /^Show another instead of/,
            })
         );

         expect(screen.queryByRole("article", { name: rejectedTitle }))
            .not.toBeInTheDocument();
         expect(screen.getByRole("article", { name: replacementTitle }))
            .toHaveFocus();
      }

      expect(screen.getAllByRole("article").map((card) => (
         within(card).getByRole("heading", { level: 3 }).textContent
      ))).toEqual(["Game 6", "Game 2", "Game 3"]);
      for (const button of screen.getAllByRole("button", {
         name: /^Show another instead of/,
      })) {
         expect(button).toBeDisabled();
      }
      expect(screen.getByText(/seen every recommendation in this bounded/))
         .toBeInTheDocument();
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
      expect(mockedRefineRecommendations).not.toHaveBeenCalled();

      rerender(
         <PreferenceValidationPanel sessionEpoch={7} preference={refinedDraft} />
      );
      mockedValidate.mockResolvedValueOnce(refinedCanonicalPreference);
      fireEvent.click(
         screen.getByRole("button", { name: "Refine recommendations" })
      );

      await screen.findByRole("article", { name: "Refined Game 1" });
      expect(mockedRefineRecommendations).toHaveBeenCalledWith(
         refinedCanonicalPreference,
         [620, 623, 624]
      );
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();
      expect(screen.queryByRole("article", { name: "Game 6" }))
         .not.toBeInTheDocument();
   });

   it("drops the browser-local session across a refresh boundary", async () => {
      mockedGetRecommendations.mockResolvedValue(sixItemResponse);
      const firstRender = render(
         <PreferenceValidationPanel sessionEpoch={7} preference={draft} />
      );
      await completeWorkflow();
      fireEvent.click(
         within(screen.getByRole("article", { name: "Portal 2" }))
            .getByRole("button", { name: /^Show another instead of/ })
      );
      expect(screen.queryByRole("article", { name: "Portal 2" }))
         .not.toBeInTheDocument();

      firstRender.unmount();
      render(<PreferenceValidationPanel sessionEpoch={7} preference={draft} />);

      expect(screen.queryByRole("article")).not.toBeInTheDocument();
      expect(
         screen.getByRole("button", { name: "Get recommendations" })
      ).toBeEnabled();
      expect(mockedGetRecommendations).toHaveBeenCalledOnce();

      await completeWorkflow();
      expect(screen.getByRole("article", { name: "Portal 2" }))
         .toBeInTheDocument();
      expect(mockedGetRecommendations).toHaveBeenCalledTimes(2);
      expect(mockedRefineRecommendations).not.toHaveBeenCalled();
   });
});
