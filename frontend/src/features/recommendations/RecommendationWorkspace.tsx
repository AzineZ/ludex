import { useCallback, useState } from "react";

import "./recommendations.css";
import AssistantWorkspace from "./assistant/AssistantWorkspace";
import ReferenceSelectionSection from "./references/ReferenceSelectionSection";
import type { RecommendationWorkspaceView } from "./recommendationWorkspaceTypes";

type RecommendationWorkspaceProps = {
   sessionEpoch: number | null;
};

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
            Guided results
         </button>
      </nav>
   );
}

function RecommendationWorkspaceSession({
   sessionEpoch,
}: RecommendationWorkspaceProps) {
   const [mode, setMode] = useState<"guided" | "assistant">("guided");
   const [activeView, setActiveView] =
      useState<RecommendationWorkspaceView>("preferences");
   const [recommendationsAvailable, setRecommendationsAvailable] =
      useState(false);

   const handleRecommendationsReady = useCallback(() => {
      setRecommendationsAvailable(true);
      setActiveView("recommendations");
   }, []);

   const handleRecommendationsReset = useCallback(() => {
      setRecommendationsAvailable(false);
      setActiveView("preferences");
   }, []);

   return (
      <div className="app__recommendation-workspace">
         <nav
            className="app__recommendation-mode-nav"
            aria-label="Recommendation method"
         >
            <button
               type="button"
               aria-current={mode === "guided" ? "page" : undefined}
               onClick={() => setMode("guided")}
            >
               Guided recommendations
            </button>
            <button
               type="button"
               aria-current={mode === "assistant" ? "page" : undefined}
               onClick={() => setMode("assistant")}
            >
               Ask Ludex AI
            </button>
         </nav>

         {mode === "guided" ? (
            <>
               <WorkspaceNavigation
                  activeView={activeView}
                  recommendationsAvailable={recommendationsAvailable}
                  onSelect={setActiveView}
               />
               <div className="app__recommendation-workspace__body">
                  <ReferenceSelectionSection
                     sessionEpoch={sessionEpoch}
                     activeView={activeView}
                     onRecommendationsReady={handleRecommendationsReady}
                     onRecommendationsReset={handleRecommendationsReset}
                  />
               </div>
            </>
         ) : (
            <AssistantWorkspace
               sessionEpoch={sessionEpoch}
               onUseGuided={() => {
                  setActiveView("preferences");
                  setMode("guided");
               }}
            />
         )}
      </div>
   );
}

/** Owns browser-local navigation for one authorized recommendation session. */
function RecommendationWorkspace(props: RecommendationWorkspaceProps) {
   return (
      <RecommendationWorkspaceSession
         key={props.sessionEpoch ?? "no-session"}
         {...props}
      />
   );
}

export default RecommendationWorkspace;
