import { useState } from "react";

import type { OwnedGameResponse, SessionProfileResponse } from "../../api";

type SessionGameLibraryProps = {
   profile: SessionProfileResponse;
   isRefreshing: boolean;
   refreshError: string | null;
   refreshSucceeded: boolean;
   onRefresh: () => Promise<boolean>;
};

const LIBRARY_WALL_GAME_LIMIT = 24;
const MINIMUM_GAMES_PER_ROW = 8;
const LIBRARY_WALL_ROW_COUNT = 3;

function fillLibraryRow(games: readonly OwnedGameResponse[]): OwnedGameResponse[] {
   if (games.length === 0) return [];
   const rowLength = Math.max(MINIMUM_GAMES_PER_ROW, games.length);
   return Array.from(
      { length: rowLength },
      (_, index) => games[index % games.length]
   );
}

function LibraryCard({ game }: { game: OwnedGameResponse }) {
   return (
      <span
         className="app__library-card"
         data-steam-app-id={game.steam_app_id}
      >
         <span className="app__library-card-fallback">{game.name}</span>
         {game.cover_url !== null && (
            <img
               src={game.cover_url}
               alt=""
               loading="lazy"
               decoding="async"
               onError={(event) => {
                  event.currentTarget.hidden = true;
               }}
            />
         )}
      </span>
   );
}

function LibraryTrack({
   games,
   reverse = false,
   slow = false,
}: {
   games: readonly OwnedGameResponse[];
   reverse?: boolean;
   slow?: boolean;
}) {
   const modifierClasses = [
      reverse ? "app__library-track--reverse" : "",
      slow ? "app__library-track--slow" : "",
   ].filter(Boolean).join(" ");

   return (
      <div className={`app__library-track ${modifierClasses}`.trim()}>
         {["original", "duplicate"].map((group) => (
            <div className="app__library-track-group" key={group}>
               {games.map((game, index) => (
                  <LibraryCard
                     game={game}
                     key={`${group}-${game.steam_app_id}-${index}`}
                  />
               ))}
            </div>
         ))}
      </div>
   );
}

/** Shows cached library covers as a bounded page backdrop with local controls. */
function SessionGameLibrary({
   profile,
   isRefreshing,
   refreshError,
   refreshSucceeded,
   onRefresh,
}: SessionGameLibraryProps) {
   const [isPaused, setIsPaused] = useState(false);
   const wallGames = profile.games.slice(0, LIBRARY_WALL_GAME_LIMIT);
   const gamesPerRow = Math.ceil(wallGames.length / LIBRARY_WALL_ROW_COUNT);
   const rows = Array.from({ length: LIBRARY_WALL_ROW_COUNT }, (_, index) => {
      const rowGames = wallGames.slice(
         index * gamesPerRow,
         (index + 1) * gamesPerRow
      );
      return fillLibraryRow(rowGames.length === 0 ? wallGames : rowGames);
   });

   return (
      <>
         {wallGames.length > 0 && (
            <div
               className={`app__library-backdrop${
                  isPaused ? " app__library-backdrop--paused" : ""
               }`}
               aria-hidden="true"
            >
               <LibraryTrack games={rows[0]} />
               <LibraryTrack games={rows[1]} reverse />
               <LibraryTrack games={rows[2]} slow />
            </div>
         )}

         <button
            className="app__secondary-button"
            type="button"
            onClick={() => void onRefresh()}
            disabled={isRefreshing}
         >
            {isRefreshing ? "Refreshing library…" : "Refresh library"}
         </button>

         {wallGames.length > 0 && (
            <button
               className="app__secondary-button"
               type="button"
               aria-pressed={isPaused}
               onClick={() => setIsPaused((paused) => !paused)}
            >
               {isPaused ? "Resume background" : "Pause background"}
            </button>
         )}

         {refreshSucceeded && (
            <p className="app__profile-feedback" role="status" aria-label="refresh-result">
               Steam library refreshed.
            </p>
         )}
         {refreshError !== null && (
            <p className="app__profile-feedback" role="alert">{refreshError}</p>
         )}
      </>
   );
}

export default SessionGameLibrary;
