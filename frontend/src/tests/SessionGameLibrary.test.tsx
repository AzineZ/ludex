import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SessionProfileResponse } from "../api";
import SessionGameLibrary from "../features/session/SessionGameLibrary";

function profileWithGames(
   games: SessionProfileResponse["games"]
): SessionProfileResponse {
   return {
      steam_id: "76561198000000001",
      display_name: "Test Player",
      profile_url: null,
      avatar_url: null,
      created_at: "2026-09-03T12:00:00Z",
      last_synced_at: null,
      games,
   };
}

function game(steamAppId: number, coverUrl: string | null) {
   return {
      steam_app_id: steamAppId,
      name: `Game ${steamAppId}`,
      icon_url: null,
      cover_url: coverUrl,
      playtime_minutes: steamAppId,
      recent_playtime_minutes: null,
      last_played_at: null,
   };
}

describe("SessionGameLibrary", () => {
   it("renders cached covers and title fallbacks as a decorative page backdrop", () => {
      const { container } = render(
         <SessionGameLibrary
            profile={profileWithGames([
               game(10, "https://images.example/game-10.jpg"),
               game(20, null),
            ])}
            isRefreshing={false}
            refreshError={null}
            refreshSucceeded={false}
            onRefresh={vi.fn().mockResolvedValue(true)}
         />
      );

      const backdrop = container.querySelector(".app__library-backdrop");
      expect(backdrop).toHaveAttribute("aria-hidden", "true");
      expect(container.querySelectorAll(".app__library-track")).toHaveLength(3);
      expect(container.querySelector('img[src="https://images.example/game-10.jpg"]'))
         .toHaveAttribute("alt", "");
      expect(screen.getAllByText("Game 20").length).toBeGreaterThan(0);
      expect(container.querySelector(".app__game-list")).toBeNull();
      expect(screen.queryByText(/minutes played/)).toBeNull();
      expect(screen.getByRole("button", { name: "Pause background" }))
         .toHaveAttribute("aria-pressed", "false");
   });

   it("pauses and resumes the cover animation only through its dedicated control", () => {
      const { container } = render(
         <SessionGameLibrary
            profile={profileWithGames([game(10, null)])}
            isRefreshing={false}
            refreshError={null}
            refreshSucceeded={false}
            onRefresh={vi.fn().mockResolvedValue(true)}
         />
      );

      fireEvent.click(screen.getByRole("button", { name: "Pause background" }));
      expect(container.querySelector(".app__library-backdrop"))
         .toHaveClass("app__library-backdrop--paused");
      expect(screen.getByRole("button", { name: "Resume background" }))
         .toHaveAttribute("aria-pressed", "true");

      fireEvent.click(screen.getByRole("button", { name: "Resume background" }));
      expect(container.querySelector(".app__library-backdrop"))
         .not.toHaveClass("app__library-backdrop--paused");
   });

   it("bounds the animated source set to the first 24 deterministic games", () => {
      render(
         <SessionGameLibrary
            profile={profileWithGames(
               Array.from({ length: 25 }, (_, index) => game(index + 1, null))
            )}
            isRefreshing={false}
            refreshError={null}
            refreshSucceeded={false}
            onRefresh={vi.fn().mockResolvedValue(true)}
         />
      );

      expect(screen.getAllByText("Game 24").length).toBeGreaterThan(0);
      expect(screen.queryByText("Game 25")).toBeNull();
   });

   it("keeps refresh feedback and the empty-library state accessible", () => {
      const onRefresh = vi.fn().mockResolvedValue(true);
      render(
         <SessionGameLibrary
            profile={profileWithGames([])}
            isRefreshing={false}
            refreshError={null}
            refreshSucceeded
            onRefresh={onRefresh}
         />
      );

      expect(document.querySelector(".app__library-backdrop")).toBeNull();
      expect(screen.queryByRole("button", { name: /background/ })).toBeNull();
      expect(screen.getByRole("status", { name: "refresh-result" }))
         .toHaveTextContent("Steam library refreshed.");
      fireEvent.click(screen.getByRole("button", { name: "Refresh library" }));
      expect(onRefresh).toHaveBeenCalledOnce();
   });
});
