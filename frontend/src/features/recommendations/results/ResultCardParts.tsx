import type { ReactNode } from "react";

import { useTitleMarquee } from "./useTitleMarquee";

import type { GameRatingsResponse } from "../../../api";
import {
   describeCardMeta,
   describeCompletion,
   describeCriticScore,
   describeIgdbRating,
   describePlaytime,
   getRecommendationCoverUrl,
} from "./resultCardFormat";

export type CardHeadingLevel = 3 | 4 | 5;

type ResultCardCoverProps = {
   title: string;
   coverUrl: string | null;
};

/** Shows the whole portrait cover, or a labelled placeholder of the same shape. */
export function ResultCardCover({ title, coverUrl }: ResultCardCoverProps) {
   return (
      <div className="recommendation-result-card__cover-frame">
         {coverUrl === null ? (
            <div
               className="recommendation-result-card__cover-fallback"
               role="img"
               aria-label={`${title} cover unavailable`}
            >
               Cover unavailable
            </div>
         ) : (
            <img
               className="recommendation-result-card__cover"
               src={getRecommendationCoverUrl(coverUrl)}
               alt={`${title} cover`}
            />
         )}
      </div>
   );
}

type CardHeadingProps = {
   level: CardHeadingLevel | 6;
   id?: string;
   className?: string;
   children: ReactNode;
};

/** Renders a heading at the level the surrounding page needs. */
export function CardHeading({ level, id, className, children }: CardHeadingProps) {
   const Tag = `h${level}` as "h3" | "h4" | "h5" | "h6";
   return (
      <Tag id={id} className={className}>
         {children}
      </Tag>
   );
}

type CardTitleProps = {
   level: CardHeadingLevel;
   id: string;
   title: string;
};

/**
 * Shows a game's name on one line; a name too long to fit scrolls back and
 * forth on hover or keyboard focus (see `useTitleMarquee`).
 */
export function CardTitle({ level, id, title }: CardTitleProps) {
   const { containerRef, textRef } = useTitleMarquee<
      HTMLHeadingElement,
      HTMLSpanElement
   >(title);
   const Tag = `h${level}` as "h3" | "h4" | "h5";
   return (
      <Tag
         ref={containerRef}
         id={id}
         className="recommendation-result-card__title"
      >
         <span ref={textRef} className="recommendation-result-card__title-text">
            {title}
         </span>
      </Tag>
   );
}

type ResultCardMetaProps = {
   ratings: GameRatingsResponse;
   normalCompletionSeconds: number | null;
   profilePlaytimeMinutes: number;
};

/** Shows the thresholded rating, rough length, and library playtime. */
export function ResultCardMeta({
   ratings,
   normalCompletionSeconds,
   profilePlaytimeMinutes,
}: ResultCardMetaProps) {
   return (
      <p className="recommendation-result-card__meta">
         {describeCardMeta(
            ratings,
            normalCompletionSeconds,
            profilePlaytimeMinutes
         )}
      </p>
   );
}

type ResultCardFactsProps = {
   profilePlaytimeMinutes: number;
   normalCompletionSeconds: number | null;
   ratings: GameRatingsResponse;
};

/** Lists playtime, length, and every available rating with its count. */
export function ResultCardFacts({
   profilePlaytimeMinutes,
   normalCompletionSeconds,
   ratings,
}: ResultCardFactsProps) {
   return (
      <dl className="recommendation-result-card__facts">
         <div>
            <dt>Your library</dt>
            <dd>{describePlaytime(profilePlaytimeMinutes)}</dd>
         </div>
         <div>
            <dt>Estimated completion</dt>
            <dd>{describeCompletion(normalCompletionSeconds)}</dd>
         </div>
         <div>
            <dt>Critic score</dt>
            <dd>{describeCriticScore(ratings)}</dd>
         </div>
         <div>
            <dt>IGDB rating</dt>
            <dd>{describeIgdbRating(ratings)}</dd>
         </div>
      </dl>
   );
}
