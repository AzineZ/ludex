import type { SessionProfileResponse } from "../../api";

type SessionGameLibraryProps = {
   profile: SessionProfileResponse;
   isRefreshing: boolean;
   refreshError: string | null;
   refreshSucceeded: boolean;
   onRefresh: () => Promise<boolean>;
};

/** Displays the current session's cached Steam library. */
function SessionGameLibrary({
   profile,
   isRefreshing,
   refreshError,
   refreshSucceeded,
   onRefresh,
}: SessionGameLibraryProps) {
   return (
      <section className="app__library" aria-labelledby="library-heading">
         <h3 id="library-heading">Game library</h3>
         <button
            className="app__secondary-button"
            type="button"
            onClick={() => void onRefresh()}
            disabled={isRefreshing}
         >
            {isRefreshing ? "Refreshing library…" : "Refresh library"}
         </button>

         {refreshSucceeded && (
            <p role="status" aria-label="refresh-result">
               Steam library refreshed.
            </p>
         )}
         {refreshError !== null && <p role="alert">{refreshError}</p>}

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

export default SessionGameLibrary;
