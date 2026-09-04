import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
   ApiError,
   getReferenceKeywords,
   type KeywordBrowseResponse,
} from "../api";
import { useReferenceKeywordBrowse } from "../features/recommendations/useReferenceKeywordBrowse";

vi.mock("../api", async (importOriginal) => {
   const actual = await importOriginal<typeof import("../api")>();
   return { ...actual, getReferenceKeywords: vi.fn() };
});

type Deferred<Value> = {
   promise: Promise<Value>;
   resolve: (value: Value) => void;
};

function deferred<Value>(): Deferred<Value> {
   let resolve!: (value: Value) => void;
   const promise = new Promise<Value>((resolvePromise) => {
      resolve = resolvePromise;
   });
   return { promise, resolve };
}

const response: KeywordBrowseResponse = {
   items: [{ id: 41, name: "Exploration" }],
   truncated: false,
};
const mockedGetReferenceKeywords = vi.mocked(getReferenceKeywords);

describe("useReferenceKeywordBrowse", () => {
   beforeEach(() => {
      mockedGetReferenceKeywords.mockReset();
   });

   it("stays idle without both a profile and reference", () => {
      const { result, rerender } = renderHook(
         ({ sessionEpoch, steamAppId }) =>
            useReferenceKeywordBrowse(sessionEpoch, steamAppId),
         {
            initialProps: {
               sessionEpoch: null as number | null,
               steamAppId: 100 as number | null,
            },
         }
      );
      expect(result.current.status).toBe("idle");

      rerender({ sessionEpoch: 1, steamAppId: null });
      expect(result.current.status).toBe("idle");
      expect(mockedGetReferenceKeywords).not.toHaveBeenCalled();
   });

   it("loads the bounded collection immediately and preserves truncation", async () => {
      mockedGetReferenceKeywords.mockResolvedValueOnce({
         ...response,
         truncated: true,
      });
      const { result } = renderHook(() =>
         useReferenceKeywordBrowse(1, 100)
      );

      expect(result.current.status).toBe("loading");
      expect(mockedGetReferenceKeywords).toHaveBeenCalledWith(100);
      await act(async () => {
         await Promise.resolve();
      });
      expect(result.current).toEqual({
         status: "ready",
         items: response.items,
         truncated: true,
         error: null,
         retry: expect.any(Function),
      });
   });

   it("treats an empty collection as a successful ready state", async () => {
      mockedGetReferenceKeywords.mockResolvedValueOnce({
         items: [],
         truncated: false,
      });
      const { result } = renderHook(() =>
         useReferenceKeywordBrowse(1, 100)
      );

      await act(async () => {
         await Promise.resolve();
      });
      expect(result.current).toEqual({
         status: "ready",
         items: [],
         truncated: false,
         error: null,
         retry: expect.any(Function),
      });
   });

   it("exposes browse failures without inventing keyword data", async () => {
      mockedGetReferenceKeywords.mockRejectedValueOnce(
         new ApiError(404, "Reference game not found.")
      );
      const { result } = renderHook(() =>
         useReferenceKeywordBrowse(1, 100)
      );

      await act(async () => {
         await Promise.resolve();
      });
      expect(result.current).toEqual({
         status: "unavailable",
         items: [],
         truncated: false,
         error: "Reference game not found.",
         retry: expect.any(Function),
      });
   });

   it("retries the same cached keyword browse after failure", async () => {
      mockedGetReferenceKeywords
         .mockRejectedValueOnce(new ApiError(503, "Temporarily unavailable."))
         .mockResolvedValueOnce(response);
      const { result } = renderHook(() => useReferenceKeywordBrowse(1, 100));

      await act(async () => Promise.resolve());
      expect(result.current.status).toBe("unavailable");

      act(() => result.current.retry());
      expect(result.current.status).toBe("loading");
      await act(async () => Promise.resolve());

      expect(result.current.items).toEqual(response.items);
      expect(mockedGetReferenceKeywords).toHaveBeenCalledTimes(2);
   });

   it("ignores stale profile and reference responses", async () => {
      const first = deferred<KeywordBrowseResponse>();
      const second = deferred<KeywordBrowseResponse>();
      mockedGetReferenceKeywords
         .mockReturnValueOnce(first.promise)
         .mockReturnValueOnce(second.promise);
      const { result, rerender } = renderHook(
         ({ sessionEpoch, steamAppId }) =>
            useReferenceKeywordBrowse(sessionEpoch, steamAppId),
         { initialProps: { sessionEpoch: 1, steamAppId: 100 } }
      );

      rerender({ sessionEpoch: 2, steamAppId: 200 });
      await act(async () => {
         first.resolve(response);
         await first.promise;
      });
      expect(result.current.status).toBe("loading");

      await act(async () => {
         second.resolve({
            items: [{ id: 42, name: "Choices" }],
            truncated: false,
         });
         await second.promise;
      });
      expect(result.current.items).toEqual([{ id: 42, name: "Choices" }]);
   });
});
