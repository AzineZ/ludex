import { useCallback, useState } from "react";

import type { RecommendationPreference } from "../../api";
import "./recommendations.css";
import AutomaticRecommendations from "./automatic/AutomaticRecommendations";
import ReferenceSelectionSection from "./references/ReferenceSelectionSection";
import type { RecommendationWorkspaceView } from "./recommendationWorkspaceTypes";

type RecommendationWorkspaceProps = {
   sessionEpoch: number | null;
};

type GuidedView = "suggestions" | "customize";

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
   const [guidedView, setGuidedView] = useState<GuidedView>("suggestions");
   const [prefill, setPrefill] = useState<RecommendationPreference | null>(
      null
   );
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

   function openCustomize(preference: RecommendationPreference | null): void {
      if (preference !== null) {
         setPrefill(preference);
      }
      setActiveView("preferences");
      setGuidedView("customize");
   }

   return (
      <div className="app__recommendation-workspace">
         <div hidden={guidedView !== "suggestions"}>
            <AutomaticRecommendations onCustomize={openCustomize} />
         </div>
         <div hidden={guidedView !== "customize"}>
            <button
               className="app__secondary-button app__recommendation-workspace__back"
               type="button"
               onClick={() => setGuidedView("suggestions")}
            >
               ← Back to recommendations
            </button>
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
                  prefill={prefill}
               />
            </div>
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
