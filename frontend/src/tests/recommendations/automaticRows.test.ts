import { describe, expect, it } from "vitest";

import {
   addMoreLikeRow,
   createAutomaticRow,
   formatPlayedHours,
   remainingAlternatives,
   rowHeading,
   shownSteamAppIds,
   showAnotherInRow,
   suggestedSteamAppIds,
} from "../../features/recommendations/automatic/automaticRows";
import { automaticRowResponse } from "./automaticFixtures";

function ids(items: readonly { steam_app_id: number }[]): number[] {
   return items.map((item) => item.steam_app_id);
}

describe("automatic rows", () => {
   it("shows three games per row and keeps the rest waiting", () => {
      const row = createAutomaticRow(
         automaticRowResponse(101, [201, 202, 203, 204, 205, 206]),
         "played",
         "played-101"
      );

      expect(ids(row.visible)).toEqual([201, 202, 203]);
      expect(ids(row.waiting)).toEqual([204, 205, 206]);
   });

   it("names the played game and its hours, or the More like source", () => {
      const played = createAutomaticRow(
         automaticRowResponse(101, [201], 2520),
         "played",
         "played-101"
      );
      const moreLike = createAutomaticRow(
         automaticRowResponse(201, [301]),
         "more-like",
         "more-201-1"
      );

      expect(rowHeading(played)).toBe("Because you played Source 101 · 42 h");
      expect(
         rowHeading({
            ...played,
            sourceGame: { ...played.sourceGame, achievement_percent: 87 },
         })
      ).toBe("Because you played Source 101 · 42 h · 87% achievements");
      expect(rowHeading(moreLike)).toBe("More like Source 201");
      expect(formatPlayedHours(60)).toBe("1 h");
      expect(formatPlayedHours(90_000)).toBe("1,500 h");
   });

   it("skips waiting games already visible in another row", () => {
      const first = createAutomaticRow(
         automaticRowResponse(101, [201, 202, 203, 301, 204]),
         "played",
         "played-101"
      );
      const second = createAutomaticRow(
         automaticRowResponse(102, [301, 302, 303]),
         "played",
         "played-102"
      );
      const rows = [first, second];

      expect(remainingAlternatives(rows, first)).toBe(1);
      const result = showAnotherInRow(rows, "played-101", 202);

      expect(result?.replacementSteamAppId).toBe(204);
      expect(ids(result?.rows[0].visible ?? [])).toEqual([201, 204, 203]);
      expect(result?.rows[1]).toBe(second);
      expect(showAnotherInRow(rows, "missing", 202)).toBeNull();
   });

   it("keeps only the newest three More like rows", () => {
      const moreLikeRows = [1, 2, 3, 4].reduce(
         (rows, index) =>
            addMoreLikeRow(
               rows,
               createAutomaticRow(
                  automaticRowResponse(index, [index * 10]),
                  "more-like",
                  `more-${index}`
               )
            ),
         [] as ReturnType<typeof addMoreLikeRow>
      );

      expect(moreLikeRows.map((row) => row.key)).toEqual([
         "more-4",
         "more-3",
         "more-2",
      ]);
   });

   it("lists shown games by priority without duplicates and caps them at 60", () => {
      const row = createAutomaticRow(
         automaticRowResponse(101, [201, 202, 203, 204]),
         "played",
         "played-101"
      );

      expect(shownSteamAppIds([row], [999, 201])).toEqual([
         201, 202, 203, 101, 999, 204,
      ]);

      const rejected = Array.from({ length: 70 }, (_, index) => 5000 + index);
      expect(shownSteamAppIds([row], rejected)).toHaveLength(60);
   });

   it("lists suggested games for Ask Ludex without queued alternatives", () => {
      const row = createAutomaticRow(
         automaticRowResponse(101, [201, 202, 203, 204]),
         "played",
         "played-101"
      );

      expect(suggestedSteamAppIds([row], [999, 201])).toEqual([
         201, 202, 203, 101, 999,
      ]);
      const rejected = Array.from({ length: 70 }, (_, index) => 5000 + index);
      expect(suggestedSteamAppIds([row], rejected)).toHaveLength(60);
   });
});
