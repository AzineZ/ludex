import {
   describeCompletion,
   describePlaytime,
   getRecommendationCoverUrl,
} from "./resultCardFormat";

type ResultCardCoverProps = {
   title: string;
   coverUrl: string | null;
};

/** Shows the large cover, or a labelled placeholder when none is cached. */
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

type ResultCardFactsProps = {
   profilePlaytimeMinutes: number;
   normalCompletionSeconds: number | null;
};

/** Lists the library playtime and completion estimate for one result. */
export function ResultCardFacts({
   profilePlaytimeMinutes,
   normalCompletionSeconds,
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
      </dl>
   );
}
