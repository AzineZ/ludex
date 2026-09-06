import { useCallback, useState } from "react";

import "./recommendations.css";
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
            Recommendations
         </button>
      </nav>
   );
}

function RecommendationWorkspaceSession({
   sessionEpoch,
}: RecommendationWorkspaceProps) {
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
