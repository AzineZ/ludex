import type { PlayStatus, PreferenceConstraints } from "../../../api";

type QuickTogglesProps = {
   value: PreferenceConstraints;
   disabled: boolean;
   onChange: (value: PreferenceConstraints) => void;
};

const PLAY_STATUS_OPTIONS: { value: PlayStatus; label: string }[] = [
   { value: "unplayed", label: "Not started" },
   { value: "previously_played", label: "Played before" },
   { value: "either", label: "Either" },
];

const LENGTH_OPTIONS: { minutes: number | null; label: string }[] = [
   { minutes: null, label: "Any" },
   { minutes: 300, label: "≤5 h" },
   { minutes: 600, label: "≤10 h" },
   { minutes: 1200, label: "≤20 h" },
   { minutes: 2400, label: "≤40 h" },
];

/** Re-filters automatic rows with the two existing hard constraints. */
function QuickToggles({ value, disabled, onChange }: QuickTogglesProps) {
   return (
      <div className="automatic-toggles">
         <fieldset className="automatic-toggles__group">
            <legend>Played?</legend>
            <div className="automatic-toggles__choices">
               {PLAY_STATUS_OPTIONS.map((option) => (
                  <button
                     key={option.value}
                     className="recommendation-choice-pill"
                     type="button"
                     aria-pressed={value.play_status === option.value}
                     disabled={disabled}
                     onClick={() => {
                        if (value.play_status !== option.value) {
                           onChange({ ...value, play_status: option.value });
                        }
                     }}
                  >
                     {option.label}
                  </button>
               ))}
            </div>
         </fieldset>

         <fieldset className="automatic-toggles__group">
            <legend>Length</legend>
            <div className="automatic-toggles__choices">
               {LENGTH_OPTIONS.map((option) => (
                  <button
                     key={option.label}
                     className="recommendation-choice-pill"
                     type="button"
                     aria-pressed={
                        value.maximum_completion_minutes === option.minutes
                     }
                     aria-label={
                        option.minutes === null
                           ? "Any length"
                           : `Up to ${option.minutes / 60} hours`
                     }
                     disabled={disabled}
                     onClick={() => {
                        if (value.maximum_completion_minutes !== option.minutes) {
                           onChange({
                              ...value,
                              maximum_completion_minutes: option.minutes,
                           });
                        }
                     }}
                  >
                     {option.label}
                  </button>
               ))}
            </div>
         </fieldset>

         {value.maximum_completion_minutes !== null && (
            <p className="automatic-toggles__note">
               Games without a known completion time won’t be included when a
               limit is set.
            </p>
         )}
      </div>
   );
}

export default QuickToggles;
