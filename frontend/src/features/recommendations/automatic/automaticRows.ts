import type {
   AutomaticRecommendationRowResponse,
   AutomaticSourceGameResponse,
   FinalRecommendationItemResponse,
} from "../../../api";
import {
   createReplacementQueue,
   replaceVisibleItem,
} from "../results/replacementQueue";

export const MAX_MORE_LIKE_ROWS = 3;
export const MAX_REJECTED_GAMES = 30;
export const MAX_MORE_LIKE_EXCLUDED_GAMES = 60;

export type AutomaticRowKind = "played" | "more-like";

export type AutomaticRow = {
   key: string;
   kind: AutomaticRowKind;
   sourceGame: AutomaticSourceGameResponse;
   visible: readonly FinalRecommendationItemResponse[];
   waiting: readonly FinalRecommendationItemResponse[];
};

export type ShowAnotherResult = {
   rows: AutomaticRow[];
   replacementSteamAppId: number;
};

/** Builds one row, splitting its ranked items into visible and waiting. */
export function createAutomaticRow(
   response: AutomaticRecommendationRowResponse,
   kind: AutomaticRowKind,
   key: string
): AutomaticRow {
   const queue = createReplacementQueue(response.recommendations.items);
   return {
      key,
      kind,
      sourceGame: response.source_game,
      visible: queue.visible,
      waiting: queue.waiting,
   };
}

/** Describes the playtime shown after "Because you played …". */
export function formatPlayedHours(playtimeMinutes: number): string {
   return `${Math.max(1, Math.round(playtimeMinutes / 60)).toLocaleString("en-US")} h`;
}

export function rowHeading(row: AutomaticRow): string {
   return row.kind === "played"
      ? `Because you played ${row.sourceGame.title} · ${formatPlayedHours(row.sourceGame.playtime_minutes)}`
      : `More like ${row.sourceGame.title}`;
}

function visibleSteamAppIds(rows: readonly AutomaticRow[]): Set<number> {
   return new Set(
      rows.flatMap((row) => row.visible.map((item) => item.steam_app_id))
   );
}

/**
 * Replaces one visible card with the next waiting game in its row,
 * skipping waiting games already visible elsewhere on the page.
 */
export function showAnotherInRow(
   rows: readonly AutomaticRow[],
   rowKey: string,
   rejectedSteamAppId: number
): ShowAnotherResult | null {
   const rowIndex = rows.findIndex((row) => row.key === rowKey);
   if (rowIndex < 0) {
      return null;
   }

   const row = rows[rowIndex];
   const shownElsewhere = visibleSteamAppIds(rows);
   const waiting = row.waiting.filter(
      (item) => !shownElsewhere.has(item.steam_app_id)
   );
   const replacement = replaceVisibleItem(
      row.visible,
      waiting,
      rejectedSteamAppId
   );
   if (replacement === null) {
      return null;
   }

   const nextRows = [...rows];
   nextRows[rowIndex] = {
      ...row,
      visible: replacement.visible,
      waiting: replacement.waiting,
   };
   return {
      rows: nextRows,
      replacementSteamAppId: replacement.replacement.steam_app_id,
   };
}

/** Counts the alternatives a row can still show without duplicates. */
export function remainingAlternatives(
   rows: readonly AutomaticRow[],
   row: AutomaticRow
): number {
   const shown = visibleSteamAppIds(rows);
   return row.waiting.filter((item) => !shown.has(item.steam_app_id)).length;
}

/** Adds a "More like" row on top, keeping only the newest three. */
export function addMoreLikeRow(
   moreLikeRows: readonly AutomaticRow[],
   row: AutomaticRow
): AutomaticRow[] {
   return [row, ...moreLikeRows].slice(0, MAX_MORE_LIKE_ROWS);
}

/**
 * Lists every game already shown on the page, most important first:
 * visible cards, row source games, dismissed games, then waiting games.
 */
export function shownSteamAppIds(
   rows: readonly AutomaticRow[],
   rejectedSteamAppIds: readonly number[]
): number[] {
   const ordered = [
      ...rows.flatMap((row) => row.visible.map((item) => item.steam_app_id)),
      ...rows.map((row) => row.sourceGame.steam_app_id),
      ...rejectedSteamAppIds,
      ...rows.flatMap((row) => row.waiting.map((item) => item.steam_app_id)),
   ];
   return [...new Set(ordered)].slice(0, MAX_MORE_LIKE_EXCLUDED_GAMES);
}
