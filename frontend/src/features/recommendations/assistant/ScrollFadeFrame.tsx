import {
   useCallback,
   useEffect,
   useRef,
   useState,
   type ReactNode,
} from "react";

type ScrollFadeFrameProps = {
   ariaLabel?: string;
   children: ReactNode;
   className: string;
   role?: "region";
   tabIndex?: number;
   updateKey: number | string;
};

export default function ScrollFadeFrame({
   ariaLabel,
   children,
   className,
   role,
   tabIndex,
   updateKey,
}: ScrollFadeFrameProps) {
   const viewportRef = useRef<HTMLDivElement>(null);
   const [scrollState, setScrollState] = useState({
      atEnd: true,
      atStart: true,
      hasOverflow: false,
   });

   const updateScrollState = useCallback(() => {
      const viewport = viewportRef.current;
      if (viewport === null) {
         return;
      }

      const maximumScroll = Math.max(
         0,
         viewport.scrollHeight - viewport.clientHeight
      );
      const nextState = {
         atEnd: viewport.scrollTop >= maximumScroll - 1,
         atStart: viewport.scrollTop <= 1,
         hasOverflow: maximumScroll > 1,
      };
      setScrollState((current) =>
         current.atEnd === nextState.atEnd &&
         current.atStart === nextState.atStart &&
         current.hasOverflow === nextState.hasOverflow
            ? current
            : nextState
      );
   }, []);

   useEffect(() => {
      if (viewportRef.current !== null) {
         viewportRef.current.scrollTop = 0;
      }
      updateScrollState();

      if (typeof ResizeObserver === "undefined") {
         window.addEventListener("resize", updateScrollState);
         return () => window.removeEventListener("resize", updateScrollState);
      }

      const observer = new ResizeObserver(updateScrollState);
      if (viewportRef.current !== null) {
         observer.observe(viewportRef.current);
      }
      return () => observer.disconnect();
   }, [updateKey, updateScrollState]);

   return (
      <div
         className="assistant-scroll-frame"
         data-at-end={scrollState.atEnd}
         data-at-start={scrollState.atStart}
         data-has-overflow={scrollState.hasOverflow}
      >
         <div
            ref={viewportRef}
            className={className}
            role={role}
            aria-label={ariaLabel}
            tabIndex={tabIndex}
            onScroll={updateScrollState}
         >
            {children}
         </div>
      </div>
   );
}
