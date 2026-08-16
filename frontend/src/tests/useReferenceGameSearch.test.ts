import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   searchReferenceGames,
   type OwnedGameSearchResponse,
} from "../api";
import { useReferenceGameSearch } from "../features/recommendations/useReferenceGameSearch";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();

   return {
      ...actual,
      searchReferenceGames: vi.fn(),
   };
});

type Deferred<Value> = {
   promise: Promise<Value>;
   resolve: (value: Value) => void;
   reject: (reason: unknown) => void;
};

const readyResponse: OwnedGameSearchResponse = {
   items: [
      {
         steam_app_id: 100,
         name: "Alpha Game",
         cover_url: null,
         metadata_status: "ready",
      },
   ],
};

const secondResponse: OwnedGameSearchResponse = {
   items: [
      {
         steam_app_id: 200,
         name: "Beta Game",
         cover_url: null,
         metadata_status: "ready",
      },
   ],
};

const thirdResponse: OwnedGameSearchResponse = {
   items: [
      {
         steam_app_id: 300,
         name: "Gamma Game",
         cover_url: null,
         metadata_status: "ready",
      },
   ],
};

const mockedSearchReferenceGames = vi.mocked(searchReferenceGames);

function deferred<Value>(): Deferred<Value> {
   let resolve!: (value: Value) => void;
   let reject!: (reason: unknown) => void;
   const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
      resolve = resolvePromise;
      reject = rejectPromise;
   });

   return {
      promise,
      resolve,
      reject,
   };
}

describe("useReferenceGameSearch", () => {
   beforeEach(() => {
      vi.useFakeTimers();
      mockedSearchReferenceGames.mockReset();
   });

   afterEach(() => {
      vi.useRealTimers();
   });

   it("stays idle without a profile or meaningful query", () => {
      const { result, rerender } = renderHook(
         ({ profileId, query }) => useReferenceGameSearch(profileId, query),
         {
            initialProps: {
               profileId: null as number | null,
               query: "alpha",
            },
         }
      );

      expect(result.current).toEqual({
         status: "idle",
         items: [],
         error: null,
      });

      rerender({
         profileId: 1,
         query: "  \t  ",
      });
      act(() => {
         vi.runAllTimers();
      });

      expect(result.current).toEqual({
         status: "idle",
         items: [],
         error: null,
      });
      expect(mockedSearchReferenceGames).not.toHaveBeenCalled();
   });

   it("waits 250 milliseconds and forwards the raw query", () => {
      const request = deferred<OwnedGameSearchResponse>();
      mockedSearchReferenceGames.mockReturnValue(request.promise);

      const { result } = renderHook(() =>
         useReferenceGameSearch(1, "  alpha  ")
      );

      expect(result.current.status).toBe("waiting");

      act(() => {
         vi.advanceTimersByTime(249);
      });
      expect(mockedSearchReferenceGames).not.toHaveBeenCalled();

      act(() => {
         vi.advanceTimersByTime(1);
      });

      expect(mockedSearchReferenceGames).toHaveBeenCalledOnce();
      expect(mockedSearchReferenceGames).toHaveBeenCalledWith(1, "  alpha  ");
      expect(result.current).toEqual({
         status: "loading",
         items: [],
         error: null,
      });
   });

   it("returns ready suggestions after a successful search", async () => {
      const request = deferred<OwnedGameSearchResponse>();
      mockedSearchReferenceGames.mockReturnValue(request.promise);
      const { result } = renderHook(() => useReferenceGameSearch(1, "alpha"));

      act(() => {
         vi.advanceTimersByTime(250);
      });
      await act(async () => {
         request.resolve(readyResponse);
         await request.promise;
      });

      expect(result.current).toEqual({
         status: "ready",
         items: readyResponse.items,
         error: null,
      });
   });

   it("keeps a successful empty result distinct from failure", async () => {
      const request = deferred<OwnedGameSearchResponse>();
      mockedSearchReferenceGames.mockReturnValue(request.promise);
      const { result } = renderHook(() => useReferenceGameSearch(1, "unknown"));

      act(() => {
         vi.advanceTimersByTime(250);
      });
      await act(async () => {
         request.resolve({ items: [] });
         await request.promise;
      });

      expect(result.current).toEqual({
         status: "ready",
         items: [],
         error: null,
      });
   });

   it("returns immediately to idle when a populated query becomes blank", async () => {
      const request = deferred<OwnedGameSearchResponse>();
      mockedSearchReferenceGames.mockReturnValue(request.promise);
      const { result, rerender } = renderHook(
         ({ query }) => useReferenceGameSearch(1, query),
         {
            initialProps: { query: "alpha" },
         }
      );

      act(() => {
         vi.advanceTimersByTime(250);
      });
      await act(async () => {
         request.resolve(readyResponse);
         await request.promise;
      });
      expect(result.current.items).toEqual(readyResponse.items);

      rerender({ query: "   " });

      expect(result.current).toEqual({
         status: "idle",
         items: [],
         error: null,
      });
   });

   it("exposes the backend message when search fails", async () => {
      const request = deferred<OwnedGameSearchResponse>();
      mockedSearchReferenceGames.mockReturnValue(request.promise);
      const { result } = renderHook(() => useReferenceGameSearch(1, "alpha"));

      act(() => {
         vi.advanceTimersByTime(250);
      });
      await act(async () => {
         request.reject(new ApiError(404, "The profile no longer exists."));
         await request.promise.catch(() => undefined);
      });

      expect(result.current).toEqual({
         status: "unavailable",
         items: [],
         error: "The profile no longer exists.",
      });
   });

   it("clears suggestions and ignores a stale query response", async () => {
      const firstRequest = deferred<OwnedGameSearchResponse>();
      const secondRequest = deferred<OwnedGameSearchResponse>();
      const thirdRequest = deferred<OwnedGameSearchResponse>();
      mockedSearchReferenceGames
         .mockReturnValueOnce(firstRequest.promise)
         .mockReturnValueOnce(secondRequest.promise)
         .mockReturnValueOnce(thirdRequest.promise);

      const { result, rerender } = renderHook(
         ({ query }) => useReferenceGameSearch(1, query),
         {
            initialProps: { query: "alpha" },
         }
      );

      act(() => {
         vi.advanceTimersByTime(250);
      });
      await act(async () => {
         firstRequest.resolve(readyResponse);
         await firstRequest.promise;
      });
      expect(result.current.items).toEqual(readyResponse.items);

      rerender({ query: "beta" });
      expect(result.current).toEqual({
         status: "waiting",
         items: [],
         error: null,
      });

      act(() => {
         vi.advanceTimersByTime(250);
      });
      rerender({ query: "gamma" });
      act(() => {
         vi.advanceTimersByTime(250);
      });

      await act(async () => {
         secondRequest.resolve(secondResponse);
         await secondRequest.promise;
      });

      expect(result.current).toEqual({
         status: "loading",
         items: [],
         error: null,
      });

      await act(async () => {
         thirdRequest.resolve(thirdResponse);
         await thirdRequest.promise;
      });
      expect(result.current.items).toEqual(thirdResponse.items);
   });

   it("ignores a late response from a previously selected profile", async () => {
      const firstRequest = deferred<OwnedGameSearchResponse>();
      const secondRequest = deferred<OwnedGameSearchResponse>();
      mockedSearchReferenceGames
         .mockReturnValueOnce(firstRequest.promise)
         .mockReturnValueOnce(secondRequest.promise);

      const { result, rerender } = renderHook(
         ({ profileId }) => useReferenceGameSearch(profileId, "game"),
         {
            initialProps: { profileId: 1 },
         }
      );

      act(() => {
         vi.advanceTimersByTime(250);
      });
      rerender({ profileId: 2 });
      act(() => {
         vi.advanceTimersByTime(250);
      });

      await act(async () => {
         firstRequest.resolve(readyResponse);
         await firstRequest.promise;
      });
      expect(result.current).toEqual({
         status: "loading",
         items: [],
         error: null,
      });

      await act(async () => {
         secondRequest.resolve(secondResponse);
         await secondRequest.promise;
      });
      expect(result.current).toEqual({
         status: "ready",
         items: secondResponse.items,
         error: null,
      });
   });
});
