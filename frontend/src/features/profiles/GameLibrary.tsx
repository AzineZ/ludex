import type { ProfileDetailResponse } from "../../api";
import type { ProfileDetailState, RefreshState } from "./types";

type GameLibraryProps = {
   detailState: ProfileDetailState;
   error: string | null;
   profile: ProfileDetailResponse | null;
   refreshError: string | null;
   refreshState: RefreshState;
   onRefresh: () => Promise<void>;
};

/** Displays the selected profile's cached Steam library and refresh controls. */
function GameLibrary({
   detailState,
   error,
   profile,
   refreshError,
   refreshState,
   onRefresh,
}: GameLibraryProps) {
   if (detailState === "loading") {
      return <p>Loading game library...</p>;
   }

   if (detailState === "unavailable") {
      return <p role="alert">{error ?? "The game library could not be loaded."}</p>;
   }

   if (detailState !== "ready" || profile === null) {
      return null;
   }

   return (
      <section className="app__library" aria-labelledby="library-heading">
         <h3 id="library-heading">Game library</h3>
         <button
            className="app__secondary-button"
            type="button"
            onClick={onRefresh}
            disabled={refreshState === "refreshing"}
         >
            {refreshState === "refreshing"
               ? "Refreshing library..."
               : "Refresh library"}
         </button>

         {refreshState === "succeeded" && (
            <p role="status">Steam library refreshed.</p>
         )}

         {refreshState === "failed" && (
            <p role="alert">
               {refreshError ?? "The Steam library could not be refreshed."}
            </p>
         )}

         <p className="app__game-count">
            {profile.games.length} {profile.games.length === 1 ? "game" : "games"}
         </p>

         {profile.games.length === 0 && <p>This Steam library is empty.</p>}

         {profile.games.length > 0 && (
            <ul className="app__game-list">
               {profile.games.map((game) => (
                  <li className="app__game" key={game.steam_app_id}>
                     <span className="app__game-name">{game.name}</span>
                     <span className="app__playtime">
                        {game.playtime_minutes} minutes played
                     </span>
                  </li>
               ))}
            </ul>
         )}
      </section>
   );
}

export default GameLibrary;
