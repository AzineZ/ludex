const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

if (!apiBaseUrl) {
   throw new Error("VITE_API_BASE_URL is not configured.");
}

type ErrorDetails = {
   message: string;
   code: string | null;
   field: string | null;
};

/** Represents an unsuccessful response returned by the Ludex API. */
export class ApiError extends Error {
   readonly status: number;
   readonly code: string | null;
   readonly field: string | null;

   constructor(
      status: number,
      message: string,
      code: string | null = null,
      field: string | null = null
   ) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.code = code;
      this.field = field;
   }
}

/** Extracts safe details from an unsuccessful API response. */
async function getErrorDetails(response: Response): Promise<ErrorDetails> {
   const fallbackDetails: ErrorDetails = {
      message: `Request failed with status ${response.status}.`,
      code: null,
      field: null,
   };
   const responseData: unknown = await response.json().catch(() => null);

   if (typeof responseData !== "object" || responseData === null) {
      return fallbackDetails;
   }

   if ("error" in responseData) {
      const error = responseData.error;

      if (
         typeof error === "object" &&
         error !== null &&
         "code" in error &&
         typeof error.code === "string" &&
         "field" in error &&
         typeof error.field === "string" &&
         "message" in error &&
         typeof error.message === "string"
      ) {
         return {
            message: error.message,
            code: error.code,
            field: error.field,
         };
      }
   }

   if ("detail" in responseData && typeof responseData.detail === "string") {
      return {
         message: responseData.detail,
         code: null,
         field: null,
      };
   }

   return fallbackDetails;
}

/** Sends a request to the Ludex API and returns its decoded JSON response. */
export async function requestJson<ResponseType>(
   path: string,
   options?: RequestInit
): Promise<ResponseType> {
   const response = await fetch(`${apiBaseUrl}${path}`, options);

   if (!response.ok) {
      const error = await getErrorDetails(response);

      throw new ApiError(
         response.status,
         error.message,
         error.code,
         error.field
      );
   }

   return response.json() as Promise<ResponseType>;
}
