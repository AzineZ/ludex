import type { PreferenceConstraints } from "../../../api";

/** True when Played or Length is narrowing what Ask Ludex searches. */
export function isNarrowed(constraints: PreferenceConstraints): boolean {
   return (
      constraints.play_status !== "either"
      || constraints.maximum_completion_minutes !== null
   );
}

function gamesNoun(
   constraints: PreferenceConstraints,
   count?: number,
): string {
   const games = count === 1 ? "game" : "games";
   switch (constraints.play_status) {
      case "unplayed":
         return `${games} you haven’t started`;
      case "previously_played":
         return `${games} you’ve played`;
      default:
         return `${games} in your library`;
   }
}

function lengthPhrase(constraints: PreferenceConstraints): string {
   const minutes = constraints.maximum_completion_minutes;
   if (minutes === null) {
      return "";
   }
   const hours = minutes / 60;
   return ` up to ${hours.toLocaleString("en-US")} ${hours === 1 ? "hour" : "hours"} long`;
}

/** "Searching games you haven't started, any length." */
export function describeScope(constraints: PreferenceConstraints): string {
   const length = constraints.maximum_completion_minutes === null
      ? ", any length"
      : `,${lengthPhrase(constraints)}`;
   return `Searching ${gamesNoun(constraints)}${length}.`;
}

/** "108 games you haven't started" (with any length limit). */
export function describeSearchedGames(
   count: number,
   constraints: PreferenceConstraints,
): string {
   return `${count.toLocaleString("en-US")} ${gamesNoun(constraints, count)}${lengthPhrase(constraints)}`;
}

/** "No games you haven't started up to 5 hours long are left to search." */
export function describeNothingToSearch(
   constraints: PreferenceConstraints,
): string {
   return `No ${gamesNoun(constraints)}${lengthPhrase(constraints)} are left to search.`;
}

/** "Ludex is looking through games you haven't started for “relaxing”…" */
export function describeLooking(
   prompt: string,
   constraints: PreferenceConstraints,
): string {
   return `Ludex is looking through ${gamesNoun(constraints)}${lengthPhrase(constraints)} for “${prompt}”…`;
}
