import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   searchReferenceKeywords,
   type KeywordSearchResponse,
} from "../../api";
import { useReferenceKeywordSearch } from "../../features/recommendations/references/useReferenceKeywordSearch";

vi.mock("../../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../../api")>();
   return { ...actual, searchReferenceKeywords: vi.fn() };
});

type Deferred<Value> = {
   promise: Promise<Value>;
   resolve: (value: Value) => void;
   reject: (reason: unknown) => void;
};

function deferred<Value>(): Deferred<Value> {
   let resolve!: (value: Value) => void;
   let reject!: (reason: unknown) => void;
   const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
      resolve = resolvePromise;
      reject = rejectPromise;
   });
   return { promise, resolve, reject };
}

const response: KeywordSearchResponse = {
   items: [{ id: 41, name: "Exploration" }],
};

const mockedSearchReferenceKeywords = vi.mocked(searchReferenceKeywords);

describe("useReferenceKeywordSearch", () => {
   beforeEach(() => {
      vi.useFakeTimers();
      mockedSearchReferenceKeywords.mockReset();
   });

   afterEach(() => {
      vi.useRealTimers();
   });

   it("stays idle without a profile, reference, or meaningful query", () => {
      const { result, rerender } = renderHook(
         ({ sessionEpoch, steamAppId, query }) =>
            useReferenceKeywordSearch(sessionEpoch, steamAppId, query),
         {
            initialProps: {
               sessionEpoch: null as number | null,
               steamAppId: 100 as number | null,
               query: "explore",
            },
         }
      );
      expect(result.current.status).toBe("idle");

      rerender({ sessionEpoch: 1, steamAppId: null, query: "explore" });
      expect(result.current.status).toBe("idle");
      rerender({ sessionEpoch: 1, steamAppId: 100, query: "   " });
      expect(result.current.status).toBe("idle");
      expect(mockedSearchReferenceKeywords).not.toHaveBeenCalled();
   });

   it("waits 250 milliseconds and forwards the raw query", () => {
      const request = deferred<KeywordSearchResponse>();
      mockedSearchReferenceKeywords.mockReturnValue(request.promise);
      const { result } = renderHook(() =>
         useReferenceKeywordSearch(1, 100, "  explore  ")
      );

      expect(result.current.status).toBe("waiting");
      act(() => vi.advanceTimersByTime(249));
      expect(mockedSearchReferenceKeywords).not.toHaveBeenCalled();
      act(() => vi.advanceTimersByTime(1));
      expect(mockedSearchReferenceKeywords).toHaveBeenCalledWith(
         100,
         "  explore  "
      );
      expect(result.current.status).toBe("loading");
   });

   it("returns exact suggestions and successful empty results", async () => {
      mockedSearchReferenceKeywords.mockResolvedValueOnce(response);
      const { result, rerender } = renderHook(
         ({ query }) => useReferenceKeywordSearch(1, 100, query),
         { initialProps: { query: "explore" } }
      );
      await act(async () => {
         vi.advanceTimersByTime(250);
         await Promise.resolve();
      });
      expect(result.current).toEqual({
         status: "ready",
         items: response.items,
         error: null,
      });

      mockedSearchReferenceKeywords.mockResolvedValueOnce({ items: [] });
      rerender({ query: "unknown" });
      await act(async () => {
         vi.advanceTimersByTime(250);
         await Promise.resolve();
      });
      expect(result.current).toEqual({
         status: "ready",
         items: [],
         error: null,
      });
   });

   it("exposes backend failures", async () => {
      mockedSearchReferenceKeywords.mockRejectedValue(
         new ApiError(404, "Reference game not found.")
      );
      const { result } = renderHook(() =>
         useReferenceKeywordSearch(1, 100, "explore")
      );
      await act(async () => {
         vi.advanceTimersByTime(250);
         await Promise.resolve();
      });
      expect(result.current).toEqual({
         status: "unavailable",
         items: [],
         error: "Reference game not found.",
      });
   });

   it("ignores stale query, profile, and reference responses", async () => {
      const first = deferred<KeywordSearchResponse>();
      const second = deferred<KeywordSearchResponse>();
      mockedSearchReferenceKeywords
         .mockReturnValueOnce(first.promise)
         .mockReturnValueOnce(second.promise);
      const { result, rerender } = renderHook(
         ({ sessionEpoch, steamAppId, query }) =>
            useReferenceKeywordSearch(sessionEpoch, steamAppId, query),
         {
            initialProps: { sessionEpoch: 1, steamAppId: 100, query: "first" },
         }
      );

      act(() => vi.advanceTimersByTime(250));
      rerender({ sessionEpoch: 2, steamAppId: 200, query: "second" });
      act(() => vi.advanceTimersByTime(250));
      await act(async () => {
         first.resolve(response);
         await first.promise;
      });
      expect(result.current.status).toBe("loading");

      await act(async () => {
         second.resolve({ items: [{ id: 42, name: "Choices" }] });
         await second.promise;
      });
      expect(result.current.items).toEqual([{ id: 42, name: "Choices" }]);
   });
});
