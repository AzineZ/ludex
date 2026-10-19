import type {
   GameRatingsResponse,
   MatchReasonResponse,
} from "../../../api";

export function formatMinutes(minutes: number): string {
   const hours = Math.floor(minutes / 60);
   const remainingMinutes = minutes % 60;

   if (hours === 0) {
      return `${remainingMinutes} min`;
   }
   if (remainingMinutes === 0) {
      return `${hours} hr`;
   }
   return `${hours} hr ${remainingMinutes} min`;
}

export function getRecommendationCoverUrl(coverUrl: string): string {
   return coverUrl.replace(
      /^(https:\/\/images\.igdb\.com\/igdb\/image\/upload\/)t_cover_big(?=\/)/,
      "$1t_cover_big_2x"
   );
}

export function describePlaytime(profilePlaytimeMinutes: number): string {
   return profilePlaytimeMinutes === 0
      ? "Not played yet"
      : `${formatMinutes(profilePlaytimeMinutes)} played`;
}

export function describeCompletion(
   normalCompletionSeconds: number | null
): string {
   return normalCompletionSeconds === null
      ? "Unavailable"
      : formatMinutes(Math.round(normalCompletionSeconds / 60));
}

export function showAnotherLabel(
   remainingAlternatives: number | undefined
): string {
   if (remainingAlternatives === 0) {
      return "No alternatives left";
   }
   return remainingAlternatives === undefined
      ? "Show another"
      : `Show another · ${remainingAlternatives} left`;
}

/** Rounds an estimate for the one-line card summary ("~14 h", "~45 min"). */
export function describeLengthShort(
   normalCompletionSeconds: number | null
): string | null {
   if (normalCompletionSeconds === null) {
      return null;
   }
   const minutes = Math.round(normalCompletionSeconds / 60);
   if (minutes < 60) {
      return `~${Math.max(1, minutes)} min`;
   }
   return `~${Math.round(minutes / 60).toLocaleString("en-US")} h`;
}

/** Names the card's thresholded rating, such as "Critics 85". */
export function describeRatingHeadline(
   ratings: GameRatingsResponse
): string | null {
   const headline = ratings.headline;
   if (headline === null) {
      return null;
   }
   return headline.source === "critics"
      ? `Critics ${headline.score}`
      : `Rated ${headline.score}`;
}

function describeVotes(
   score: { score: number; count: number } | null,
   singular: string,
   plural: string
): string | null {
   if (score === null) {
      return null;
   }
   const noun = score.count === 1 ? singular : plural;
   return `${score.score}/100 from ${score.count.toLocaleString("en-US")} ${noun}`;
}

export function describeCriticScore(ratings: GameRatingsResponse): string {
   return describeVotes(ratings.critics, "review", "reviews")
      ?? "No critic reviews";
}

export function describeIgdbRating(ratings: GameRatingsResponse): string {
   return describeVotes(ratings.total, "rating", "ratings") ?? "Not rated";
}

/** Rounds library playtime for the one-line card summary. */
export function describePlaytimeShort(profilePlaytimeMinutes: number): string {
   if (profilePlaytimeMinutes === 0) {
      return "Not played";
   }
   if (profilePlaytimeMinutes < 60) {
      return "Played <1 h";
   }
   return `Played ${Math.round(profilePlaytimeMinutes / 60).toLocaleString("en-US")} h`;
}

/** Joins rating, length, and library playtime for one compact line. */
export function describeCardMeta(
   ratings: GameRatingsResponse,
   normalCompletionSeconds: number | null,
   profilePlaytimeMinutes: number
): string {
   return [
      describeRatingHeadline(ratings),
      describeLengthShort(normalCompletionSeconds),
      describePlaytimeShort(profilePlaytimeMinutes),
   ]
      .filter((part): part is string => part !== null)
      .join(" · ");
}

/** Shortens a factual match to its strongest three facet names. */
export function describeShortMatch(
   reasons: readonly MatchReasonResponse[]
): string {
   const names = reasons.slice(0, 3).map((reason) => reason.name);
   if (names.length === 0) {
      return "No selected preferences matched.";
   }
   if (names.length === 1) {
      return `Matches ${names[0]}`;
   }
   if (names.length === 2) {
      return `Matches ${names[0]} and ${names[1]}`;
   }
   return `Matches ${names[0]}, ${names[1]}, and ${names[2]}`;
}
