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

function RecommendationConstraints({
   value,
   onChange,
}: RecommendationConstraintsProps) {
   return (
      <fieldset className="recommendation-constraints">
         <legend>Optional constraints</legend>

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
      </fieldset>
   );
}

export default RecommendationConstraints;
