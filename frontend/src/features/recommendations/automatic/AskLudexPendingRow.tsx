import { useEffect, useState } from "react";

const PLACEHOLDER_CARDS = 3;
export const SLOW_ASK_HINT_DELAY_MS = 6_000;

type AskLudexPendingRowProps = {
   heading: string;
};

/**
 * Stands in for the Ask Ludex row while Gemini answers. Each placeholder
 * copies the real card's structure, so the page does not jump when the
 * picks replace it; the bar's status line is what screen readers hear.
 */
export function AskLudexPendingRow({ heading }: AskLudexPendingRowProps) {
   return (
      <section
         className="automatic-recommendations__row automatic-recommendations__row--ask-ludex ask-ludex-pending"
         data-row-kind="ask-ludex-pending"
         aria-hidden="true"
      >
         <h4>{heading}</h4>
         <div className="automatic-recommendations__cards" inert>
            {Array.from({ length: PLACEHOLDER_CARDS }, (_, index) => (
               <PlaceholderCard key={index} />
            ))}
         </div>
      </section>
   );
}

function PlaceholderCard() {
   return (
      <div className="recommendation-result-card ask-ludex-placeholder">
         <div className="recommendation-result-card__cover-frame ask-ludex-placeholder__cover" />
         <div className="recommendation-result-card__body">
            <h5 className="recommendation-result-card__title">
               <span className="ask-ludex-placeholder__bar">Finding a game</span>
            </h5>
            <p className="recommendation-result-card__meta">
               <span className="recommendation-result-card__rating ask-ludex-placeholder__bar">
                  Critics 00
               </span>
               <span className="recommendation-result-card__meta-text">
                  <span className="ask-ludex-placeholder__bar">About 00 hours</span>
               </span>
            </p>
            <section className="recommendation-result-card__reason assistant-result-card__explanation">
               <h6>
                  <span className="ask-ludex-placeholder__bar">Reasoning</span>
               </h6>
               <div className="assistant-scroll-frame">
                  <div className="assistant-result-card__scroll-region ask-ludex-placeholder__lines" />
               </div>
            </section>
            <div className="recommendation-result-card__actions">
               <button className="app__secondary-button" type="button" disabled>
                  Show another
               </button>
               <button className="app__secondary-button" type="button" disabled>
                  More like this
               </button>
            </div>
         </div>
         <div className="recommendation-result-card__details">
            <p className="ask-ludex-placeholder__summary">Game details</p>
         </div>
      </div>
   );
}

/** Mounted only while asking, so its timer starts fresh with every ask. */
export function SlowAskHint() {
   const [isSlow, setIsSlow] = useState(false);
   useEffect(() => {
      const timer = window.setTimeout(() => setIsSlow(true), SLOW_ASK_HINT_DELAY_MS);
      return () => window.clearTimeout(timer);
   }, []);
   return isSlow ? (
      <p className="ask-ludex__note">Large libraries take a little longer.</p>
   ) : null;
}
