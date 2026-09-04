// @ts-expect-error Vitest runs this contract in Node; app builds exclude Node globals.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const appCss = readFileSync("src/App.css", "utf8");
const recommendationCss = readFileSync(
   "src/features/recommendations/recommendations.css",
   "utf8"
);
const sessionCss = readFileSync(
   "src/features/session/session.css",
   "utf8"
);

function channel(value: number): number {
   const normalized = value / 255;
   return normalized <= 0.04045
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
   const value = Number.parseInt(hex.slice(1), 16);
   return (
      0.2126 * channel((value >> 16) & 255)
      + 0.7152 * channel((value >> 8) & 255)
      + 0.0722 * channel(value & 255)
   );
}

function contrast(first: string, second: string): number {
   const lighter = Math.max(luminance(first), luminance(second));
   const darker = Math.min(luminance(first), luminance(second));
   return (lighter + 0.05) / (darker + 0.05);
}

function colorToken(name: string): string {
   const match = appCss.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]+)`));
   if (match === null) throw new Error(`Missing color token ${name}.`);
   return match[1];
}

describe("visual accessibility contract", () => {
   it("keeps every text color pairing above WCAG AA normal-text contrast", () => {
      const black = colorToken("void-black");
      for (const foreground of [
         colorToken("bone-cream"),
         colorToken("ash-taupe"),
         colorToken("alarm-red"),
      ]) {
         expect(contrast(foreground, black)).toBeGreaterThanOrEqual(4.5);
      }
      expect(contrast(black, colorToken("alarm-red"))).toBeGreaterThanOrEqual(4.5);
   });

   it("keeps visible keyboard focus and reduced-motion overrides", () => {
      expect(recommendationCss).toMatch(/button:focus-visible[\s\S]*outline:/);
      expect(sessionCss).toMatch(/button:focus-visible[\s\S]*outline:/);
      expect(recommendationCss).toContain("prefers-reduced-motion: reduce");
      expect(recommendationCss).toContain("scroll-behavior: auto");
      expect(sessionCss).toContain("prefers-reduced-motion: reduce");
      expect(sessionCss).toContain("transition: none");
   });
});
