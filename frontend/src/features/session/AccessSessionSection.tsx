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
         <h2 id="steam-session-heading">Your Steam library</h2>

         {session.status === "loading" && (
            <p role="status">Checking your Steam session…</p>
         )}

         {(session.status === "signed_out" || session.status === "unavailable") && (
            <>
               {session.startupError !== null && (
                  <p role="alert">{session.startupError}</p>
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
                  <p className="app__selection">
                     Current Steam profile: <strong>{currentProfile.display_name}</strong>
                  </p>
                  <button
                     className="app__secondary-button"
                     type="button"
                     onClick={() => void session.endSession()}
                     disabled={session.isEnding}
                  >
                     {session.isEnding ? "Ending session…" : "Use another Steam ID"}
                  </button>
                  {session.endError !== null && <p role="alert">{session.endError}</p>}
               </div>

               <SessionGameLibrary
                  profile={currentProfile}
                  isRefreshing={session.isRefreshing}
                  refreshError={session.refreshError}
                  refreshSucceeded={session.refreshSucceeded}
                  onRefresh={session.refreshSessionProfile}
               />

               <ReferenceSelectionSection sessionEpoch={session.sessionEpoch} />
            </>
         )}
      </section>
   );
}

export default AccessSessionSection;
