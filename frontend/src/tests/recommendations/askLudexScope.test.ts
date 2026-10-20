import { describe, expect, it } from "vitest";

import {
   describeLooking,
   describeNothingToSearch,
   describeScope,
   describeSearchedGames,
   isNarrowed,
} from "../../features/recommendations/automatic/askLudexScope";
import { cleanMissReason } from "../../features/recommendations/automatic/useAskLudex";

const notStarted = { play_status: "unplayed" as const, maximum_completion_minutes: null };
const played10h = {
   play_status: "previously_played" as const,
   maximum_completion_minutes: 600,
};
const everything = { play_status: "either" as const, maximum_completion_minutes: null };

describe("Ask Ludex scope wording", () => {
   it("names what is being searched", () => {
      expect(describeScope(notStarted)).toBe(
         "Searching games you haven’t started, any length."
      );
      expect(describeScope(played10h)).toBe(
         "Searching games you’ve played, up to 10 hours long."
      );
      expect(describeScope(everything)).toBe(
         "Searching games in your library, any length."
      );
   });

   it("counts the games a miss looked at", () => {
      expect(describeSearchedGames(108, notStarted)).toBe(
         "108 games you haven’t started"
      );
      expect(describeSearchedGames(1, played10h)).toBe(
         "1 game you’ve played up to 10 hours long"
      );
      expect(describeNothingToSearch(played10h)).toBe(
         "No games you’ve played up to 10 hours long are left to search."
      );
   });

   it("knows when the filters narrow the search", () => {
      expect(isNarrowed(notStarted)).toBe(true);
      expect(isNarrowed(played10h)).toBe(true);
      expect(isNarrowed(everything)).toBe(false);
   });

   it("rephrases the model's internal wording", () => {
      expect(
         cleanMissReason(
            "None of the supplied candidate games fit a relaxing play style."
         )
      ).toBe("None of these games fit a relaxing play style.");
      expect(cleanMissReason("The candidates are all shooters.")).toBe(
         "The games are all shooters."
      );
      expect(cleanMissReason("  ")).toBeNull();
   });

   it("describes what Ludex is searching while it waits", () => {
      expect(describeLooking("something calm", notStarted)).toBe(
         "Ludex is looking through games you haven’t started for “something calm”…"
      );
      expect(describeLooking("a short story", played10h)).toBe(
         "Ludex is looking through games you’ve played up to 10 hours long for “a short story”…"
      );
      expect(describeLooking("anything", everything)).toBe(
         "Ludex is looking through games in your library for “anything”…"
      );
   });
});
