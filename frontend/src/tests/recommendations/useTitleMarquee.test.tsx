import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CardTitle } from "../../features/recommendations/results/ResultCardParts";
import {
   MARQUEE_END_PAUSE_MS,
   MARQUEE_PIXELS_PER_SECOND,
   MARQUEE_TOUCH_PASSES,
} from "../../features/recommendations/results/useTitleMarquee";

type FakeAnimation = {
   cancel: ReturnType<typeof vi.fn>;
   onfinish: (() => void) | null;
};

const LONG_TITLE = "An Extraordinarily Long Game Title";
const animations: { keyframes: Keyframe[]; options: KeyframeAnimationOptions; animation: FakeAnimation }[] = [];
const originalAnimate = HTMLElement.prototype.animate;
const originalMatchMedia = window.matchMedia;

function mediaQueries(active: string[]): void {
   window.matchMedia = vi.fn((query: string) => ({
      matches: active.includes(query),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
   })) as unknown as typeof window.matchMedia;
}

function sizeElements(textWidth: number, containerWidth = 200): void {
   vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockImplementation(
      function (this: HTMLElement) {
         return this.classList.contains("recommendation-result-card__title-text")
            ? textWidth
            : 0;
      }
   );
   vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(
      function (this: HTMLElement) {
         return this.classList.contains("recommendation-result-card__title")
            ? containerWidth
            : 0;
      }
   );
}

function renderTitle(title = LONG_TITLE) {
   render(
      <article className="recommendation-result-card" aria-labelledby="title">
         <CardTitle level={3} id="title" title={title} />
         <button type="button">Show another</button>
      </article>
   );
   return {
      card: screen.getByRole("article"),
      heading: screen.getByRole("heading", { level: 3 }),
   };
}

describe("CardTitle marquee", () => {
   beforeEach(() => {
      animations.length = 0;
      HTMLElement.prototype.animate = vi.fn(function (
         keyframes: Keyframe[],
         options: KeyframeAnimationOptions
      ) {
         const animation: FakeAnimation = { cancel: vi.fn(), onfinish: null };
         animations.push({ keyframes, options, animation });
         return animation as unknown as Animation;
      }) as unknown as typeof HTMLElement.prototype.animate;
      mediaQueries([]);
   });

   afterEach(() => {
      HTMLElement.prototype.animate = originalAnimate;
      window.matchMedia = originalMatchMedia;
      vi.restoreAllMocks();
   });

   it("keeps the full title as the heading's accessible name", () => {
      sizeElements(500);
      const { heading, card } = renderTitle();

      expect(heading).toHaveTextContent(LONG_TITLE);
      expect(card).toHaveAccessibleName(LONG_TITLE);
      expect(heading).toHaveAttribute("data-overflowing", "true");
   });

   it("never moves a title that already fits", () => {
      sizeElements(150);
      const { card, heading } = renderTitle("Short");

      fireEvent.mouseEnter(card);

      expect(heading).toHaveAttribute("data-overflowing", "false");
      expect(animations).toHaveLength(0);
   });

   it("scrolls the overflow back and forth while the card is hovered", () => {
      sizeElements(500);
      const { card, heading } = renderTitle();

      fireEvent.mouseEnter(card);

      expect(animations).toHaveLength(1);
      const [{ keyframes, options }] = animations;
      const travel = (300 / MARQUEE_PIXELS_PER_SECOND) * 1_000;
      expect(options).toEqual({
         duration: 2 * travel + 2 * MARQUEE_END_PAUSE_MS,
         iterations: Infinity,
      });
      expect(keyframes.map((frame) => frame.transform)).toEqual([
         "translateX(0)",
         "translateX(0)",
         "translateX(-300px)",
         "translateX(-300px)",
         "translateX(0)",
      ]);
      expect(heading).toHaveAttribute("data-marquee", "active");

      fireEvent.mouseLeave(card);

      expect(animations[0].animation.cancel).toHaveBeenCalledOnce();
      expect(heading).not.toHaveAttribute("data-marquee");
   });

   it("stays still with reduced motion", () => {
      mediaQueries(["(prefers-reduced-motion: reduce)"]);
      sizeElements(500);
      const { card } = renderTitle();

      fireEvent.mouseEnter(card);

      expect(animations).toHaveLength(0);
   });

   it("plays two passes when a touch user taps the title", () => {
      mediaQueries(["(hover: none)"]);
      sizeElements(500);
      const { card, heading } = renderTitle();

      fireEvent.mouseEnter(card);
      expect(animations).toHaveLength(0);

      fireEvent.click(heading);

      expect(animations).toHaveLength(1);
      expect(animations[0].options.iterations).toBe(MARQUEE_TOUCH_PASSES);
   });
});
