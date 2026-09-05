import { useState } from "react";

import type { PlayStatus, PreferenceConstraints } from "../../api";

type RecommendationConstraintsProps = {
   value: PreferenceConstraints;
   onChange: (value: PreferenceConstraints) => void;
};

const PLAY_STATUS_OPTIONS: { value: PlayStatus; label: string }[] = [
   { value: "unplayed", label: "Not started" },
   { value: "previously_played", label: "Played before" },
   { value: "either", label: "Either" },
];

const LENGTH_PRESETS: { minutes: number | null; label: string }[] = [
   { minutes: null, label: "Any length" },
   { minutes: 300, label: "Up to 5 hours" },
   { minutes: 600, label: "Up to 10 hours" },
   { minutes: 1200, label: "Up to 20 hours" },
   { minutes: 2400, label: "Up to 40 hours" },
];

const EMPTY_CONSTRAINTS: PreferenceConstraints = {
   maximum_completion_minutes: null,
   play_status: "either",
};

function isPresetLength(minutes: number | null): boolean {
   return LENGTH_PRESETS.some((preset) => preset.minutes === minutes);
}

function maximumCompletionSummary(minutes: number | null): string {
   if (minutes === null) {
      return "Any length";
   }

   const hours = Math.floor(minutes / 60);
   const remainingMinutes = minutes % 60;
   if (hours === 0) {
      return `Up to ${remainingMinutes} minutes`;
   }
   if (remainingMinutes === 0) {
      return `Up to ${hours} ${hours === 1 ? "hour" : "hours"}`;
   }
   return `Up to ${hours} hr ${remainingMinutes} min`;
}

function playStatusSummary(playStatus: PlayStatus): string {
   if (playStatus === "either") {
      return "Any game";
   }
   return PLAY_STATUS_OPTIONS.find((option) => option.value === playStatus)?.label
      ?? "Any game";
}

function RecommendationConstraints({
   value,
   onChange,
}: RecommendationConstraintsProps) {
   const [isCustomLength, setIsCustomLength] = useState(
      () => !isPresetLength(value.maximum_completion_minutes)
   );
   const hasActiveConstraints = value.maximum_completion_minutes !== null
      || value.play_status !== "either";

   return (
      <details className="recommendation-constraints">
         <summary>
            <span>Narrow your results</span>
            <span className="recommendation-constraints__summary-value">
               {maximumCompletionSummary(value.maximum_completion_minutes)} ·{" "}
               {playStatusSummary(value.play_status)}
            </span>
         </summary>

         <div className="recommendation-constraints__content">
            <fieldset className="recommendation-constraints__group">
               <legend>How long should the game be?</legend>
               <div className="recommendation-constraints__choices">
                  {LENGTH_PRESETS.map((preset) => (
                     <button
                        key={preset.label}
                        type="button"
                        aria-pressed={
                           !isCustomLength
                           && value.maximum_completion_minutes === preset.minutes
                        }
                        onClick={() => {
                           setIsCustomLength(false);
                           onChange({
                              ...value,
                              maximum_completion_minutes: preset.minutes,
                           });
                        }}
                     >
                        {preset.label}
                     </button>
                  ))}
                  <button
                     type="button"
                     aria-pressed={isCustomLength}
                     onClick={() => setIsCustomLength(true)}
                  >
                     Custom
                  </button>
               </div>

               {isCustomLength && (
                  <div className="recommendation-constraints__custom-length">
                     <label htmlFor="maximum-completion-hours">
                        Custom maximum in hours
                     </label>
                     <input
                        id="maximum-completion-hours"
                        type="number"
                        min={0.5}
                        max={1000}
                        step={0.5}
                        value={
                           value.maximum_completion_minutes === null
                              ? ""
                              : value.maximum_completion_minutes / 60
                        }
                        aria-describedby="maximum-completion-help"
                        onChange={(event) => {
                           const nextValue = event.target.value;
                           onChange({
                              ...value,
                              maximum_completion_minutes: nextValue === ""
                                 ? null
                                 : Math.round(Number(nextValue) * 60),
                           });
                        }}
                     />
                     <p id="maximum-completion-help">
                        Enter 0.5 to 1,000 hours.
                     </p>
                  </div>
               )}

               {value.maximum_completion_minutes !== null && (
                  <p className="recommendation-constraints__unknown-note">
                     Games without a known completion time won’t be included
                     when a limit is set.
                  </p>
               )}
            </fieldset>

            <fieldset className="recommendation-constraints__group">
               <legend>Have you played it before?</legend>
               <div className="recommendation-constraints__choices">
                  {PLAY_STATUS_OPTIONS.map((option) => (
                     <button
                        key={option.value}
                        type="button"
                        aria-pressed={value.play_status === option.value}
                        onClick={() => {
                           onChange({ ...value, play_status: option.value });
                        }}
                     >
                        {option.label}
                     </button>
                  ))}
               </div>
            </fieldset>

            {hasActiveConstraints && (
               <button
                  type="button"
                  className="recommendation-constraints__clear"
                  onClick={() => {
                     setIsCustomLength(false);
                     onChange(EMPTY_CONSTRAINTS);
                  }}
               >
                  Clear constraints
               </button>
            )}
         </div>
      </details>
   );
}

export default RecommendationConstraints;
