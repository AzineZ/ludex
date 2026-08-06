import { requestJson } from "./client";

export type HealthResponse = {
   status: string;
   database: string;
};

/** Checks whether the backend and database are available. */
export function getHealth(): Promise<HealthResponse> {
   return requestJson<HealthResponse>("/health");
}
