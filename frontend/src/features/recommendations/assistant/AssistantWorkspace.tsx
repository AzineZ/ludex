import AssistantPromptWorkspace from "./AssistantPromptWorkspace";
import AssistantResults from "./AssistantResults";
import useAssistantWorkflow from "./useAssistantWorkflow";

type AssistantWorkspaceProps = {
   sessionEpoch: number | null;
   onUseGuided: () => void;
};

function AssistantNavigation({
   activeView,
   onOpenPrompt,
}: {
   activeView: "prompt" | "recommendations";
   onOpenPrompt: () => void;
}) {
   return (
      <nav
         className="app__workspace-nav"
         aria-label="AI recommendation workspace"
      >
         <button
            type="button"
            aria-current={activeView === "prompt" ? "page" : undefined}
            onClick={onOpenPrompt}
         >
            Prompt
         </button>
         <button
            type="button"
            aria-current={activeView === "recommendations" ? "page" : undefined}
            disabled={activeView !== "recommendations"}
         >
            AI results
         </button>
      </nav>
   );
}

function AssistantWorkspaceSession({
   sessionEpoch,
   onUseGuided,
}: AssistantWorkspaceProps) {
   const workflow = useAssistantWorkflow(sessionEpoch);
   const { reject, resetResults, response } = workflow;

   if (response?.status === "ranked" && response.items.length > 0) {
      return (
         <>
            <AssistantNavigation
               activeView="recommendations"
               onOpenPrompt={resetResults}
            />
            <AssistantResults
               key={response.items.map((item) => item.steam_app_id).join("-")}
               items={response.items}
               eligibleCount={response.eligible_count}
               onStartOver={resetResults}
               onReject={reject}
            />
         </>
      );
   }

   return (
      <>
         <AssistantNavigation activeView="prompt" onOpenPrompt={() => {}} />
         <AssistantPromptWorkspace
            workflow={workflow}
            onUseGuided={onUseGuided}
         />
      </>
   );
}

function AssistantWorkspace(props: AssistantWorkspaceProps) {
   return (
      <AssistantWorkspaceSession
         key={props.sessionEpoch ?? "no-session"}
         {...props}
      />
   );
}

export default AssistantWorkspace;
