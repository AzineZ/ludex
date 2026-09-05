import type { PlayStatus, PreferenceConstraints } from "../../api";

type RecommendationConstraintsProps = {
   value: PreferenceConstraints;
   onChange: (value: PreferenceConstraints) => void;
};

const PLAY_STATUS_OPTIONS: { value: PlayStatus; label: string }[] = [
   { value: "unplayed", label: "Unplayed" },
   { value: "previously_played", label: "Previously played" },
   { value: "either", label: "Either" },
];

function maximumCompletionSummary(minutes: number | null): string {
   if (minutes === null) {
      return "Any length";
   }

   const hours = Math.floor(minutes / 60);
   const remainingMinutes = minutes % 60;
   if (hours === 0) {
      return `${remainingMinutes} min max`;
   }
   if (remainingMinutes === 0) {
      return `${hours} hr max`;
   }
   return `${hours} hr ${remainingMinutes} min max`;
}

function playStatusSummary(playStatus: PlayStatus): string {
   if (playStatus === "either") {
      return "Any play status";
   }
   return PLAY_STATUS_OPTIONS.find((option) => option.value === playStatus)?.label
      ?? "Any play status";
}

function RecommendationConstraints({
   value,
   onChange,
}: RecommendationConstraintsProps) {
   return (
      <details className="recommendation-constraints">
         <summary>
            <span>Optional constraints</span>
            <span className="recommendation-constraints__summary-value">
               {maximumCompletionSummary(value.maximum_completion_minutes)} ·{" "}
               {playStatusSummary(value.play_status)}
            </span>
         </summary>

         <div className="recommendation-constraints__content">
            <label htmlFor="maximum-completion-minutes">
               Maximum completion time in minutes
            </label>
            <input
               id="maximum-completion-minutes"
               type="number"
               min={30}
               max={60000}
               step={1}
               value={value.maximum_completion_minutes ?? ""}
               aria-describedby="maximum-completion-help"
               onChange={(event) => {
                  const nextValue = event.target.value;
                  onChange({
                     ...value,
                     maximum_completion_minutes:
                        nextValue === "" ? null : Math.trunc(Number(nextValue)),
                  });
               }}
            />
            <p id="maximum-completion-help">
               Optional. Enter 30 to 60,000 minutes.
            </p>

            <fieldset className="recommendation-constraints__play-status">
               <legend>Play status</legend>
               {PLAY_STATUS_OPTIONS.map((option) => (
                  <label key={option.value}>
                     <input
                        type="radio"
                        name="recommendation-play-status"
                        value={option.value}
                        checked={value.play_status === option.value}
                        onChange={() => {
                           onChange({ ...value, play_status: option.value });
                        }}
                     />
                     {option.label}
                  </label>
               ))}
            </fieldset>
         </div>
      </details>
   );
}

export default RecommendationConstraints;
