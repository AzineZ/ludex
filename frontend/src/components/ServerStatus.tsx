import type { ConnectionState } from "../hooks/useBackendHealth";

type ServerStatusProps = {
   connectionState: ConnectionState;
};

const STATUS_LABELS: Record<ConnectionState, string> = {
   checking: "pending",
   connected: "connected",
   unavailable: "unavailable",
};

/** Presents backend availability independently from the centered hero content. */
function ServerStatus({ connectionState }: ServerStatusProps) {
   return (
      <p
         className={`app__status app__status--${connectionState}`}
         role="status"
         aria-live="polite"
      >
         Server: {STATUS_LABELS[connectionState]}
      </p>
   );
}

export default ServerStatus;
