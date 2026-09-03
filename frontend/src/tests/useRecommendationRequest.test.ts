import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
   getFinalRecommendations,
   refineFinalRecommendations,
   type FinalRecommendationResponse,
   type RecommendationPreference,
} from "../api";
import {
   recommendationRequestFailure,
   useRecommendationRequest,
} from "../features/recommendations/useRecommendationRequest";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();

   return {
      ...actual,
      getFinalRecommendations: vi.fn(),
      refineFinalRecommendations: vi.fn(),
   };
});

type Deferred<Value> = {
   promise: Promise<Value>;
   resolve: (value: Value) => void;
   reject: (reason: unknown) => void;
};

const preference: RecommendationPreference = {
   references: [
      {
         steam_app_id: 100,
         facets: {
            genre_ids: [11],
            theme_ids: [],
            keyword_ids: [],
            game_mode_ids: [],
         },
      },
   ],
   constraints: {
      maximum_completion_minutes: null,
      play_status: "either",
   },
};

const response: FinalRecommendationResponse = {
   outcome: "empty",
   eligible_count: 0,
   returned_count: 0,
   items: [],
};

const mockedGetFinalRecommendations = vi.mocked(getFinalRecommendations);
const mockedRefineFinalRecommendations = vi.mocked(
   refineFinalRecommendations
);

function deferred<Value>(): Deferred<Value> {
   let resolve!: (value: Value) => void;
   let reject!: (reason: unknown) => void;
   const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
      resolve = resolvePromise;
      reject = rejectPromise;
   });
   return { promise, resolve, reject };
}

describe("useRecommendationRequest", () => {
   beforeEach(() => {
      mockedGetFinalRecommendations.mockReset();
      mockedRefineFinalRecommendations.mockReset();
   });

   it("stays idle and does not request without a canonical preference", () => {
      const { result, rerender } = renderHook(
         ({ sessionEpoch, value }) => useRecommendationRequest(sessionEpoch, value),
         {
            initialProps: {
               sessionEpoch: 7 as number | null,
               value: null as RecommendationPreference | null,
            },
         }
      );

      act(() => result.current.request());
      act(() => result.current.refine([201]));
      expect(result.current).toMatchObject({
         status: "idle",
         response: null,
         error: null,
      });

      rerender({ sessionEpoch: null, value: preference });
      act(() => result.current.request());
      expect(result.current.status).toBe("idle");
      expect(mockedGetFinalRecommendations).not.toHaveBeenCalled();
      expect(mockedRefineFinalRecommendations).not.toHaveBeenCalled();
   });

   it("exposes loading and then the successful response", async () => {
      const request = deferred<FinalRecommendationResponse>();
      mockedGetFinalRecommendations.mockReturnValue(request.promise);
      const { result } = renderHook(() => (
         useRecommendationRequest(7, preference)
      ));
      await act(async () => {
         result.current.request();
         await Promise.resolve();
      });

      expect(result.current).toMatchObject({
         status: "loading",
         response: null,
         error: null,
      });
      expect(mockedGetFinalRecommendations).toHaveBeenCalledWith(preference);

      await act(async () => {
         request.resolve(response);
         await request.promise;
      });

      expect(result.current).toMatchObject({
         status: "ready",
         response,
         error: null,
      });
   });

   it("locks duplicate submissions while the same request is loading", async () => {
      const request = deferred<FinalRecommendationResponse>();
      mockedGetFinalRecommendations.mockReturnValue(request.promise);
      const { result } = renderHook(() => (
         useRecommendationRequest(7, preference)
      ));
      await act(async () => {
         result.current.request();
         result.current.request();
         await Promise.resolve();
      });

      expect(mockedGetFinalRecommendations).toHaveBeenCalledOnce();

      await act(async () => {
         request.resolve(response);
         await request.promise;
      });
   });

   it("exposes a stale-safe refinement request with exact rejected IDs", async () => {
      const request = deferred<FinalRecommendationResponse>();
      mockedRefineFinalRecommendations.mockReturnValue(request.promise);
      const { result } = renderHook(() => (
         useRecommendationRequest(7, preference)
      ));
      await act(async () => {
         result.current.refine([201, 203]);
         await Promise.resolve();
      });

      expect(result.current.status).toBe("loading");
      expect(mockedRefineFinalRecommendations).toHaveBeenCalledWith(
         preference,
         [201, 203]
      );

      await act(async () => {
         request.resolve(response);
         await request.promise;
      });

      expect(result.current).toMatchObject({
         status: "ready",
         response,
         error: null,
      });
   });

   it("locks duplicate refinement submissions while one is loading", async () => {
      const request = deferred<FinalRecommendationResponse>();
      mockedRefineFinalRecommendations.mockReturnValue(request.promise);
      const { result } = renderHook(() => (
         useRecommendationRequest(7, preference)
      ));
      await act(async () => {
         result.current.refine([201]);
         result.current.refine([201]);
         await Promise.resolve();
      });

      expect(mockedRefineFinalRecommendations).toHaveBeenCalledOnce();

      await act(async () => {
         request.resolve(response);
         await request.promise;
      });
   });

   it("ignores a late refinement after its canonical key becomes stale", async () => {
      const staleRequest = deferred<FinalRecommendationResponse>();
      mockedRefineFinalRecommendations.mockReturnValue(staleRequest.promise);
      const { result, rerender } = renderHook(
         ({ value }) => useRecommendationRequest(7, value),
         {
            initialProps: {
               value: preference as RecommendationPreference | null,
            },
         }
      );
      await act(async () => {
         result.current.refine([201]);
         await Promise.resolve();
      });

      rerender({ value: null });
      expect(result.current.status).toBe("idle");

      await act(async () => {
         staleRequest.resolve(response);
         await staleRequest.promise;
      });

      expect(result.current).toMatchObject({
         status: "idle",
         response: null,
         error: null,
      });
   });

   it("builds an API failure state without retaining a result", () => {
      expect(
         recommendationRequestFailure(
            "request-key",
            new Error("The selected preference is no longer valid.")
         )
      ).toEqual({
         key: "request-key",
         status: "error",
         response: null,
         error: "The selected preference is no longer valid.",
      });
   });

   it("returns to idle when the profile or canonical preference changes", async () => {
      const request = deferred<FinalRecommendationResponse>();
      mockedGetFinalRecommendations.mockReturnValue(request.promise);
      const { result, rerender } = renderHook(
         ({ sessionEpoch, value }) => useRecommendationRequest(sessionEpoch, value),
         {
            initialProps: {
               sessionEpoch: 7 as number | null,
               value: preference as RecommendationPreference | null,
            },
         }
      );
      await act(async () => {
         result.current.request();
         await Promise.resolve();
      });
      await act(async () => {
         request.resolve(response);
         await request.promise;
      });
      expect(result.current.status).toBe("ready");

      rerender({
         sessionEpoch: 8,
         value: {
            ...preference,
            constraints: {
               ...preference.constraints,
               play_status: "unplayed",
            },
         },
      });

      expect(result.current).toMatchObject({
         status: "idle",
         response: null,
         error: null,
      });
   });

   it("ignores a late response after its request key becomes stale", async () => {
      const staleRequest = deferred<FinalRecommendationResponse>();
      mockedGetFinalRecommendations.mockReturnValue(staleRequest.promise);
      const { result, rerender } = renderHook(
         ({ value }) => useRecommendationRequest(7, value),
         {
            initialProps: {
               value: preference as RecommendationPreference | null,
            },
         }
      );
      await act(async () => {
         result.current.request();
         await Promise.resolve();
      });

      rerender({ value: null });
      expect(result.current.status).toBe("idle");

      await act(async () => {
         staleRequest.resolve(response);
         await staleRequest.promise;
      });

      expect(result.current).toMatchObject({
         status: "idle",
         response: null,
         error: null,
      });
   });
});
