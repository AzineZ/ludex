import {
   act,
   fireEvent,
   render,
   screen,
   waitFor,
   within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   getAutomaticRecommendations,
   getMoreLikeThisRecommendations,
   type AutomaticRecommendationResponse,
} from "../../api";
import AutomaticRecommendations from "../../features/recommendations/automatic/AutomaticRecommendations";
import {
   MAX_PREPARING_RETRIES,
   PREPARING_RETRY_DELAY_MS,
} from "../../features/recommendations/automatic/useAutomaticRecommendations";
import {
   AUTOMATIC_SUGGESTED_PREFERENCE,
   automaticRowResponse,
   readyAutomaticResponse,
} from "./automaticFixtures";

vi.mock("../../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../../api")>();
   return {
      ...actual,
      getAutomaticRecommendations: vi.fn(),
      getMoreLikeThisRecommendations: vi.fn(),
   };
});

const mockedAutomatic = vi.mocked(getAutomaticRecommendations);
const mockedMoreLike = vi.mocked(getMoreLikeThisRecommendations);

const PREPARING: AutomaticRecommendationResponse = {
   status: "preparing",
   rows: [],
   suggested_preference: null,
};

function renderAutomatic() {
   const onCustomize = vi.fn();
   const onUnavailable = vi.fn();
   render(
      <AutomaticRecommendations
         onCustomize={onCustomize}
         onUnavailable={onUnavailable}
      />
   );
   return { onCustomize, onUnavailable };
}

function rowRegion(name: string | RegExp): HTMLElement {
   return screen.getByRole("region", { name });
}

function cardTitles(region: HTMLElement): string[] {
   return within(region)
      .getAllByRole("heading", { level: 5 })
      .map((heading) => heading.textContent ?? "");
}

function rowHeadings(): string[] {
   return Array.from(
      document.querySelectorAll<HTMLElement>(".automatic-recommendations__row")
   ).map((row) => row.dataset.rowTitle ?? "");
}

function lastAutomaticRequest() {
   return mockedAutomatic.mock.calls.at(-1)?.[0];
}

describe("AutomaticRecommendations", () => {
   beforeEach(() => {
      mockedAutomatic.mockReset();
      mockedMoreLike.mockReset();
   });

   afterEach(() => {
      vi.useRealTimers();
   });

   it("shows nine games as three Because you played rows", async () => {
      mockedAutomatic.mockResolvedValue(readyAutomaticResponse());
      renderAutomatic();

      expect(screen.getByRole("status")).toHaveTextContent(
         "Finding recommendations in your library…"
      );
      const first = await screen.findByRole("region", {
         name: "Because you played Source 101 · 42 h",
      });

      expect(cardTitles(first)).toEqual(["Game 201", "Game 202", "Game 203"]);
      expect(cardTitles(rowRegion("Because you played Source 102 · 10 h")))
         .toEqual(["Game 207", "Game 208", "Game 209"]);
      expect(cardTitles(rowRegion("Because you played Source 103 · 2 h")))
         .toEqual(["Game 213", "Game 214", "Game 215"]);
      expect(lastAutomaticRequest()).toEqual({
         constraints: {
            maximum_completion_minutes: null,
            play_status: "unplayed",
         },
         rejected_steam_app_ids: [],
         wait_for_pending: true,
      });
      expect(screen.getByRole("button", { name: "Not started" }))
         .toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "Any length" }))
         .toHaveAttribute("aria-pressed", "true");
   });

   it("waits while top games are prepared, then stops waiting", async () => {
      vi.useFakeTimers();
      mockedAutomatic.mockResolvedValue(PREPARING);
      renderAutomatic();
      await act(async () => {});

      expect(screen.getByRole("status")).toHaveTextContent(
         "Preparing your recommendations…"
      );
      for (let retry = 1; retry <= MAX_PREPARING_RETRIES; retry += 1) {
         await act(async () => {
            await vi.advanceTimersByTimeAsync(PREPARING_RETRY_DELAY_MS);
         });
      }
      expect(mockedAutomatic).toHaveBeenCalledTimes(MAX_PREPARING_RETRIES + 1);
      expect(
         mockedAutomatic.mock.calls.every(([request]) => request.wait_for_pending)
      ).toBe(true);

      mockedAutomatic.mockResolvedValue(readyAutomaticResponse());
      await act(async () => {
         await vi.advanceTimersByTimeAsync(PREPARING_RETRY_DELAY_MS);
      });

      expect(lastAutomaticRequest()?.wait_for_pending).toBe(false);
      expect(
         screen.getByRole("region", {
            name: "Because you played Source 101 · 42 h",
         })
      ).toBeInTheDocument();
   });

   it("reports an unavailable library to the workspace", async () => {
      mockedAutomatic.mockResolvedValue({
         status: "unavailable",
         rows: [],
         suggested_preference: null,
      });
      const { onUnavailable } = renderAutomatic();

      await waitFor(() => expect(onUnavailable).toHaveBeenCalledOnce());
   });

   it("opens Customize with the suggested preference", async () => {
      mockedAutomatic.mockResolvedValue(readyAutomaticResponse());
      const { onCustomize } = renderAutomatic();
      await screen.findByRole("region", {
         name: "Because you played Source 101 · 42 h",
      });

      fireEvent.click(screen.getByRole("button", { name: "Customize" }));

      expect(onCustomize).toHaveBeenCalledWith(AUTOMATIC_SUGGESTED_PREFERENCE);
   });

   it("replaces one card per row and keeps dismissed games excluded after toggles", async () => {
      mockedAutomatic.mockResolvedValue(readyAutomaticResponse());
      renderAutomatic();
      const first = await screen.findByRole("region", {
         name: "Because you played Source 101 · 42 h",
      });

      fireEvent.click(
         within(first).getByRole("button", {
            name: /Show another instead of Game 202/,
         })
      );
      expect(cardTitles(first)).toEqual(["Game 201", "Game 204", "Game 203"]);
      expect(cardTitles(rowRegion("Because you played Source 102 · 10 h")))
         .toEqual(["Game 207", "Game 208", "Game 209"]);

      fireEvent.click(screen.getByRole("button", { name: "Up to 10 hours" }));

      expect(lastAutomaticRequest()).toEqual({
         constraints: {
            maximum_completion_minutes: 600,
            play_status: "unplayed",
         },
         rejected_steam_app_ids: [202],
         wait_for_pending: true,
      });
      expect(screen.getByRole("button", { name: "Up to 10 hours" }))
         .toBeDisabled();
      expect(
         await screen.findByText(
            /Games without a known completion time won’t be included/
         )
      ).toBeInTheDocument();
   });

   it("re-filters with toggles and restores the earlier rows", async () => {
      mockedAutomatic.mockResolvedValueOnce(readyAutomaticResponse());
      renderAutomatic();
      await screen.findByRole("region", {
         name: "Because you played Source 101 · 42 h",
      });

      mockedAutomatic.mockResolvedValueOnce({
         ...readyAutomaticResponse(),
         rows: [automaticRowResponse(101, [301, 302], 2520)],
      });
      fireEvent.click(screen.getByRole("button", { name: "Played before" }));
      await waitFor(() => {
         expect(cardTitles(rowRegion("Because you played Source 101 · 42 h")))
            .toEqual(["Game 301", "Game 302"]);
      });
      expect(lastAutomaticRequest()?.constraints.play_status)
         .toBe("previously_played");

      mockedAutomatic.mockResolvedValueOnce(readyAutomaticResponse());
      fireEvent.click(screen.getByRole("button", { name: "Not started" }));
      await waitFor(() => {
         expect(cardTitles(rowRegion("Because you played Source 101 · 42 h")))
            .toEqual(["Game 201", "Game 202", "Game 203"]);
      });
      expect(lastAutomaticRequest()?.rejected_steam_app_ids).toEqual([]);
   });

   it("adds More like rows on top, excluding every shown game, up to three", async () => {
      mockedAutomatic.mockResolvedValue(readyAutomaticResponse());
      renderAutomatic();
      await screen.findByRole("region", {
         name: "Because you played Source 101 · 42 h",
      });

      for (const [index, steamAppId] of [201, 202, 203, 207].entries()) {
         mockedMoreLike.mockResolvedValueOnce(
            automaticRowResponse(steamAppId, [400 + index * 10, 401 + index * 10])
         );
         fireEvent.click(
            screen.getByRole("button", { name: `More games like Game ${steamAppId}` })
         );
         await screen.findByText(`Added more games like Game ${steamAppId}.`);
      }

      const firstRequest = mockedMoreLike.mock.calls[0][0];
      expect(firstRequest.steam_app_id).toBe(201);
      expect(firstRequest.excluded_steam_app_ids.slice(0, 12)).toEqual([
         201, 202, 203, 207, 208, 209, 213, 214, 215, 101, 102, 103,
      ]);
      expect(firstRequest.excluded_steam_app_ids).toContain(218);

      expect(rowHeadings()).toEqual([
         "More like Source 207",
         "More like Source 203",
         "More like Source 202",
         "Because you played Source 101 · 42 h",
         "Because you played Source 102 · 10 h",
         "Because you played Source 103 · 2 h",
      ]);

      // Only the newest More like row stays open; older ones are one line.
      const newest = rowRegion("More like Source 207");
      expect(newest.querySelector(".automatic-recommendations__collapsed"))
         .toBeNull();
      expect(cardTitles(newest)).toEqual(["Game 430", "Game 431"]);
      for (const name of ["More like Source 203", "More like Source 202"]) {
         const collapsed = rowRegion(name);
         const disclosure = collapsed.querySelector(
            ".automatic-recommendations__collapsed"
         );
         expect(disclosure).not.toBeNull();
         expect(disclosure).not.toHaveAttribute("open");
         expect(within(collapsed).getByText("2 games")).toBeInTheDocument();
      }

      const older = rowRegion("More like Source 202");
      fireEvent.click(within(older).getByText("More like Source 202"));
      expect(older.querySelector(".automatic-recommendations__collapsed"))
         .toHaveAttribute("open");
      expect(cardTitles(older)).toEqual(["Game 410", "Game 411"]);

      mockedAutomatic.mockResolvedValueOnce(readyAutomaticResponse());
      fireEvent.click(screen.getByRole("button", { name: "Either" }));
      await waitFor(() => {
         expect(screen.queryByText("More like Source 207")).toBeNull();
      });
   });

   it("explains when More like this finds nothing new", async () => {
      mockedAutomatic.mockResolvedValue(readyAutomaticResponse());
      mockedMoreLike.mockResolvedValue(automaticRowResponse(201, []));
      renderAutomatic();
      await screen.findByRole("region", {
         name: "Because you played Source 101 · 42 h",
      });

      fireEvent.click(
         screen.getByRole("button", { name: "More games like Game 201" })
      );

      expect(
         await screen.findByText(
            "No other games like Game 201 match these filters."
         )
      ).toBeInTheDocument();
      expect(screen.queryByText("More like Source 201")).toBeNull();
   });

   it("suggests loosening filters when every row is empty", async () => {
      mockedAutomatic.mockResolvedValue({
         ...readyAutomaticResponse(),
         rows: [automaticRowResponse(101, []), automaticRowResponse(102, [])],
      });
      renderAutomatic();

      expect(
         await screen.findByText(/No games in your library match these filters\./)
      ).toBeInTheDocument();
      expect(rowHeadings()).toEqual([]);
   });

   it("offers a retry when loading fails", async () => {
      mockedAutomatic.mockRejectedValueOnce(
         new ApiError(503, "Recommendations are temporarily unavailable.")
      );
      renderAutomatic();

      expect(await screen.findByRole("alert")).toHaveTextContent(
         "Recommendations are temporarily unavailable."
      );
      mockedAutomatic.mockResolvedValueOnce(readyAutomaticResponse());
      fireEvent.click(screen.getByRole("button", { name: "Try again" }));

      expect(
         await screen.findByRole("region", {
            name: "Because you played Source 101 · 42 h",
         })
      ).toBeInTheDocument();
   });

   it("scrolls to and focuses a new More like row", async () => {
      const scrollIntoView = vi.fn();
      const original = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = scrollIntoView;
      try {
         mockedAutomatic.mockResolvedValue(readyAutomaticResponse());
         mockedMoreLike.mockResolvedValue(automaticRowResponse(213, [401, 402]));
         renderAutomatic();
         await screen.findByRole("region", {
            name: "Because you played Source 101 · 42 h",
         });
         expect(scrollIntoView).not.toHaveBeenCalled();

         fireEvent.click(
            screen.getByRole("button", { name: "More games like Game 213" })
         );

         const heading = await screen.findByRole("heading", {
            name: "More like Source 213",
         });
         await waitFor(() => expect(heading).toHaveFocus());
         expect(scrollIntoView).toHaveBeenCalledOnce();
         expect(scrollIntoView.mock.contexts[0]).toBe(heading);
         expect(scrollIntoView).toHaveBeenCalledWith({
            behavior: "smooth",
            block: "start",
         });
      } finally {
         Element.prototype.scrollIntoView = original;
      }
   });
});
