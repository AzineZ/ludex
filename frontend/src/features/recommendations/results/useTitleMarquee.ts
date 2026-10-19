import { useEffect, useRef } from "react";

export const MARQUEE_PIXELS_PER_SECOND = 40;
export const MARQUEE_END_PAUSE_MS = 1_200;
export const MARQUEE_RETURN_MS = 300;
export const MARQUEE_TOUCH_PASSES = 2;

const CARD_SELECTOR = ".recommendation-result-card";

function matches(query: string): boolean {
   return window.matchMedia?.(query).matches ?? false;
}

/**
 * Scrolls a single-line title back and forth when it is too long to fit.
 *
 * Only overflowing titles move. On devices with hover, the whole card's
 * hover or keyboard focus starts it and leaving eases it back to the start.
 * On touch screens it plays two passes the first time the card is mostly in
 * view, and tapping the title replays it. With reduced motion it never
 * moves; CSS wraps the title instead.
 */
export function useTitleMarquee<
   Container extends HTMLElement,
   Text extends HTMLElement,
>(title: string) {
   const containerRef = useRef<Container>(null);
   const textRef = useRef<Text>(null);

   useEffect(() => {
      const container = containerRef.current;
      const text = textRef.current;
      const card = container?.closest<HTMLElement>(CARD_SELECTOR) ?? null;
      if (container === null || text === null || card === null) {
         return;
      }

      let animation: Animation | null = null;

      function overflowDistance(): number {
         return Math.max(
            0,
            (text as Text).scrollWidth - (container as Container).clientWidth
         );
      }

      function markOverflow(): void {
         (container as Container).dataset.overflowing = String(
            overflowDistance() > 1
         );
      }

      function canAnimate(): boolean {
         return (
            typeof (text as Text).animate === "function"
            && !matches("(prefers-reduced-motion: reduce)")
            && overflowDistance() > 1
         );
      }

      function start(passes: number): void {
         if (!canAnimate()) {
            return;
         }
         animation?.cancel();
         const distance = overflowDistance();
         const travel = (distance / MARQUEE_PIXELS_PER_SECOND) * 1_000;
         const duration = 2 * travel + 2 * MARQUEE_END_PAUSE_MS;
         const end = `translateX(${-distance}px)`;
         animation = (text as Text).animate(
            [
               { transform: "translateX(0)", offset: 0 },
               {
                  transform: "translateX(0)",
                  offset: MARQUEE_END_PAUSE_MS / duration,
                  easing: "ease-in-out",
               },
               { transform: end, offset: (MARQUEE_END_PAUSE_MS + travel) / duration },
               {
                  transform: end,
                  offset: (2 * MARQUEE_END_PAUSE_MS + travel) / duration,
                  easing: "ease-in-out",
               },
               { transform: "translateX(0)", offset: 1 },
            ],
            { duration, iterations: passes }
         );
         (container as Container).dataset.marquee = "active";
         const current = animation;
         current.onfinish = () => {
            if (animation === current) {
               animation = null;
               delete (container as Container).dataset.marquee;
            }
         };
      }

      function stop(): void {
         if (animation === null) {
            return;
         }
         const position = getComputedStyle(text as Text).transform;
         animation.cancel();
         animation = null;
         delete (container as Container).dataset.marquee;
         if (position !== "none" && typeof (text as Text).animate === "function") {
            (text as Text).animate(
               [{ transform: position }, { transform: "translateX(0)" }],
               { duration: MARQUEE_RETURN_MS, easing: "ease-out" }
            );
         }
      }

      // Mouse clicks also focus buttons, so only keyboard focus keeps it moving.
      function hasKeyboardFocus(element: Element | null): boolean {
         try {
            return element?.matches(":focus-visible") ?? false;
         } catch {
            return false;
         }
      }

      function isHovered(): boolean {
         try {
            return card?.matches(":hover") ?? false;
         } catch {
            return false;
         }
      }

      const hoverCapable = !matches("(hover: none)");
      const handleEnter = () => start(Infinity);
      const handleLeave = () => {
         if (!(
            card.contains(document.activeElement)
            && hasKeyboardFocus(document.activeElement)
         )) {
            stop();
         }
      };
      const handleFocusIn = (event: FocusEvent) => {
         if (animation === null && hasKeyboardFocus(event.target as Element)) {
            start(Infinity);
         }
      };
      const handleFocusOut = (event: FocusEvent) => {
         const next = event.relatedTarget;
         if (!(next instanceof Node && card.contains(next)) && !isHovered()) {
            stop();
         }
      };
      const handleTap = () => start(MARQUEE_TOUCH_PASSES);

      markOverflow();
      card.addEventListener("focusin", handleFocusIn);
      card.addEventListener("focusout", handleFocusOut);
      if (hoverCapable) {
         card.addEventListener("mouseenter", handleEnter);
         card.addEventListener("mouseleave", handleLeave);
      } else {
         container.addEventListener("click", handleTap);
      }

      let resizeObserver: ResizeObserver | null = null;
      if (typeof ResizeObserver !== "undefined") {
         resizeObserver = new ResizeObserver(markOverflow);
         resizeObserver.observe(container);
      } else {
         window.addEventListener("resize", markOverflow);
      }

      let intersectionObserver: IntersectionObserver | null = null;
      if (!hoverCapable && typeof IntersectionObserver !== "undefined") {
         intersectionObserver = new IntersectionObserver(
            (entries) => {
               if (entries.some((entry) => entry.isIntersecting)) {
                  intersectionObserver?.disconnect();
                  start(MARQUEE_TOUCH_PASSES);
               }
            },
            { threshold: 0.6 }
         );
         intersectionObserver.observe(card);
      }

      return () => {
         animation?.cancel();
         card.removeEventListener("focusin", handleFocusIn);
         card.removeEventListener("focusout", handleFocusOut);
         card.removeEventListener("mouseenter", handleEnter);
         card.removeEventListener("mouseleave", handleLeave);
         container.removeEventListener("click", handleTap);
         resizeObserver?.disconnect();
         window.removeEventListener("resize", markOverflow);
         intersectionObserver?.disconnect();
      };
   }, [title]);

   return { containerRef, textRef };
}
