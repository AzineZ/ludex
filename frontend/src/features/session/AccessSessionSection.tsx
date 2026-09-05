import { useCallback, useState } from "react";

import "./session.css";
import ReferenceSelectionSection from "../recommendations/ReferenceSelectionSection";
import type { RecommendationWorkspaceView } from "../recommendations/recommendationWorkspace";
import SessionGameLibrary from "./SessionGameLibrary";
import SteamSessionForm from "./SteamSessionForm";
import { useAccessSession } from "./useAccessSession";

type WorkspaceNavigationProps = {
   activeView: RecommendationWorkspaceView;
   recommendationsAvailable: boolean;
   onSelect: (view: RecommendationWorkspaceView) => void;
};

function WorkspaceNavigation({
   activeView,
   recommendationsAvailable,
   onSelect,
}: WorkspaceNavigationProps) {
   return (
      <nav
         className="app__workspace-nav"
         aria-label="Recommendation workspace"
      >
         <button
            type="button"
            aria-current={activeView === "preferences" ? "page" : undefined}
            onClick={() => onSelect("preferences")}
         >
            Preferences
         </button>
         <button
            type="button"
            aria-current={
               activeView === "recommendations" ? "page" : undefined
            }
            disabled={!recommendationsAvailable}
            onClick={() => onSelect("recommendations")}
         >
            Recommendations
         </button>
      </nav>
   );
}

/** Composes the single browser-authorized Steam profile experience. */
function AccessSessionSection() {
   const session = useAccessSession();
   const currentProfile = session.status === "ready" ? session.profile : null;
   const [workspaceState, setWorkspaceState] = useState<{
      sessionEpoch: number | null;
      activeView: RecommendationWorkspaceView;
      recommendationsAvailable: boolean;
   }>({
      sessionEpoch: session.sessionEpoch,
      activeView: "preferences",
      recommendationsAvailable: false,
   });
   const currentWorkspace =
      workspaceState.sessionEpoch === session.sessionEpoch
         ? workspaceState
         : {
              sessionEpoch: session.sessionEpoch,
              activeView: "preferences" as const,
              recommendationsAvailable: false,
           };

   const handleRecommendationsReady = useCallback(() => {
      setWorkspaceState({
         sessionEpoch: session.sessionEpoch,
         activeView: "recommendations",
         recommendationsAvailable: true,
      });
   }, [session.sessionEpoch]);

   const handleRecommendationsReset = useCallback(() => {
      setWorkspaceState({
         sessionEpoch: session.sessionEpoch,
         activeView: "preferences",
         recommendationsAvailable: false,
      });
   }, [session.sessionEpoch]);

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

               <div
                  className="app__recommendation-workspace"
               >
                  <WorkspaceNavigation
                     activeView={currentWorkspace.activeView}
                     recommendationsAvailable={
                        currentWorkspace.recommendationsAvailable
                     }
                     onSelect={(activeView) =>
                        setWorkspaceState({
                           ...currentWorkspace,
                           activeView,
                        })
                     }
                  />

                  <div className="app__recommendation-workspace__body">
                     <ReferenceSelectionSection
                        sessionEpoch={session.sessionEpoch}
                        activeView={currentWorkspace.activeView}
                        onRecommendationsReady={handleRecommendationsReady}
                        onRecommendationsReset={handleRecommendationsReset}
                     />
                  </div>
               </div>
            </>
         )}
      </section>
   );
}

export default AccessSessionSection;
