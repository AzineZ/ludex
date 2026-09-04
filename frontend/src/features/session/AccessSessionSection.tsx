import "./session.css";
import ReferenceSelectionSection from "../recommendations/ReferenceSelectionSection";
import SessionGameLibrary from "./SessionGameLibrary";
import SteamSessionForm from "./SteamSessionForm";
import { useAccessSession } from "./useAccessSession";

/** Composes the single browser-authorized Steam profile experience. */
function AccessSessionSection() {
   const session = useAccessSession();
   const currentProfile = session.status === "ready" ? session.profile : null;

   return (
      <section className="app__session" aria-labelledby="steam-session-heading">
         <h2 id="steam-session-heading">
            {currentProfile === null
               ? "Connect your Steam library"
               : "What should you play next?"}
         </h2>

         {session.status === "loading" && (
            <p role="status">Checking your Steam session…</p>
         )}

         {(session.status === "signed_out" || session.status === "unavailable") && (
            <>
               {session.startupError !== null && (
                  <div className="app__session-recovery">
                     <p role="alert">{session.startupError}</p>
                     <button
                        className="app__secondary-button"
                        type="button"
                        onClick={() => void session.retrySessionRestore()}
                        disabled={session.isRestoringSession}
                     >
                        {session.isRestoringSession ? "Checking…" : "Try again"}
                     </button>
                  </div>
               )}
               <p>Enter a Steam ID or profile URL to use Ludex on this browser.</p>
               <SteamSessionForm
                  error={session.startError}
                  isStarting={session.isStarting}
                  onStart={session.startSession}
               />
            </>
         )}

         {currentProfile !== null && (
            <>
               <div className="app__current-profile">
                  <div className="app__profile-summary">
                     <p className="app__step-label">Step 1 of 3 · Steam connected</p>
                     <p className="app__selection">
                        Current Steam profile: <strong>{currentProfile.display_name}</strong>
                     </p>
                     {currentProfile.games.length === 0 ? (
                        <p className="app__game-count">This Steam library is empty.</p>
                     ) : (
                        <p className="app__game-count">
                           {currentProfile.games.length}{" "}
                           {currentProfile.games.length === 1 ? "game" : "games"}{" "}
                           in your library
                        </p>
                     )}
                  </div>

                  <div className="app__profile-actions">
                     <button
                        className="app__secondary-button"
                        type="button"
                        onClick={() => void session.endSession()}
                        disabled={session.isEnding}
                     >
                        {session.isEnding
                           ? "Ending session…"
                           : "Use another Steam ID"}
                     </button>

                     <SessionGameLibrary
                        key={currentProfile.steam_id}
                        profile={currentProfile}
                        isRefreshing={session.isRefreshing}
                        refreshError={session.refreshError}
                        refreshSucceeded={session.refreshSucceeded}
                        onRefresh={session.refreshSessionProfile}
                     />
                  </div>
                  {session.endError !== null && <p role="alert">{session.endError}</p>}
               </div>

               <ReferenceSelectionSection sessionEpoch={session.sessionEpoch} />
            </>
         )}
      </section>
   );
}

export default AccessSessionSection;
