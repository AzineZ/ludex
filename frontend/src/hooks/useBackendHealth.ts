import { useEffect, useState } from "react";
import { getHealth } from "../api";

export type ConnectionState = "checking" | "connected" | "unavailable";

/** Tracks whether the backend and its database are available. */
export function useBackendHealth(): ConnectionState {
   const [connectionState, setConnectionState] =
      useState<ConnectionState>("checking");

   useEffect(() => {
      getHealth()
         .then(() => setConnectionState("connected"))
         .catch(() => setConnectionState("unavailable"));
   }, []);

   return connectionState;
}
