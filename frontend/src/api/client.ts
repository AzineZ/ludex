const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

if (!apiBaseUrl) {
   throw new Error("VITE_API_BASE_URL is not configured.");
}

/** Represents an unsuccessful response returned by the Ludex API. */
export class ApiError extends Error {
   readonly status: number;

   constructor(status: number, message: string) {
      super(message);
      this.name = "ApiError";
      this.status = status;
   }
}

/** Extracts a useful message from an unsuccessful API response. */
async function getErrorMessage(response: Response): Promise<string> {
   const fallbackMessage = `Request failed with status ${response.status}.`;
   const responseData: unknown = await response.json().catch(() => null);

   if (
      typeof responseData === "object" &&
      responseData !== null &&
      "detail" in responseData &&
      typeof responseData.detail === "string"
   ) {
      return responseData.detail;
   }

   return fallbackMessage;
}

/** Sends a request to the Ludex API and returns its decoded JSON response. */
export async function requestJson<ResponseType>(
   path: string,
   options?: RequestInit
): Promise<ResponseType> {
   const response = await fetch(`${apiBaseUrl}${path}`, options);

   if (!response.ok) {
      throw new ApiError(response.status, await getErrorMessage(response));
   }

   return response.json() as Promise<ResponseType>;
}
