import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

const localStorageValues = new Map<string, string>();

/** Provides the browser Storage contract during frontend tests. */
const localStorageMock: Storage = {
   get length() {
      return localStorageValues.size;
   },

   clear() {
      localStorageValues.clear();
   },

   getItem(key: string) {
      return localStorageValues.get(key) ?? null;
   },

   key(index: number) {
      return Array.from(localStorageValues.keys())[index] ?? null;
   },

   removeItem(key: string) {
      localStorageValues.delete(key);
   },

   setItem(key: string, value: string) {
      localStorageValues.set(key, String(value));
   },
};

Object.defineProperty(window, "localStorage", {
   configurable: true,
   value: localStorageMock,
});

afterEach(() => {
   cleanup();
});
