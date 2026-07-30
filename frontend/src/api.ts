export type HealthResponse = {
   status: string;
   database: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

if (!apiBaseUrl) {
   throw new Error("VITE_API_BASE_URL is not configured.");
}

export async function getHealth(): Promise<HealthResponse> {
   const response = await fetch(`${apiBaseUrl}/health`);
   if (!response.ok) {
      throw new Error(`Health request failed with status ${response.status}.`);
   }
   return response.json() as Promise<HealthResponse>;
}
