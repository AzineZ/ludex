import { useCallback, useState } from "react";

import type { RecommendationPreference } from "../../api";
import "./recommendations.css";
import AssistantWorkspace from "./assistant/AssistantWorkspace";
import AutomaticRecommendations from "./automatic/AutomaticRecommendations";
import ReferenceSelectionSection from "./references/ReferenceSelectionSection";
import type { RecommendationWorkspaceView } from "./recommendationWorkspaceTypes";

type RecommendationWorkspaceProps = {
   sessionEpoch: number | null;
};

type GuidedView = "suggestions" | "customize";

const UNAVAILABLE_NOTICE =
   "Ludex needs at least one game you’ve played for an hour or more, with " +
   "game details loaded, to suggest games automatically. Choose reference " +
   "games below instead.";

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
   const [guidedView, setGuidedView] = useState<GuidedView>("suggestions");
   const [suggestionsAvailable, setSuggestionsAvailable] = useState(true);
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

   const handleSuggestionsUnavailable = useCallback(() => {
      setSuggestionsAvailable(false);
      setGuidedView("customize");
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

         <div hidden={mode !== "guided" || guidedView !== "suggestions"}>
            <AutomaticRecommendations
               onCustomize={openCustomize}
               onUnavailable={handleSuggestionsUnavailable}
            />
         </div>
         <div hidden={mode !== "guided" || guidedView !== "customize"}>
            {suggestionsAvailable ? (
               <button
                  className="app__secondary-button app__recommendation-workspace__back"
                  type="button"
                  onClick={() => setGuidedView("suggestions")}
               >
                  ← Back to suggestions
               </button>
            ) : (
               <p className="app__recommendation-workspace__notice">
                  {UNAVAILABLE_NOTICE}
               </p>
            )}
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
         {mode === "assistant" && (
            <AssistantWorkspace
               sessionEpoch={sessionEpoch}
               onUseGuided={() => {
                  setActiveView("preferences");
                  setGuidedView("customize");
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
