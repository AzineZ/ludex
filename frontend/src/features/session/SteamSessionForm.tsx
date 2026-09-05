import { useState, type FormEvent } from "react";

type SteamSessionFormProps = {
   error: string | null;
   isStarting: boolean;
   onStart: (identifier: string) => Promise<boolean>;
};

/** Collects the Steam identifier used to authorize this browser session. */
function SteamSessionForm({ error, isStarting, onStart }: SteamSessionFormProps) {
   const [identifier, setIdentifier] = useState("");
   const descriptionIds = [
      "steam-identifier-help",
      ...(error === null ? [] : ["steam-identifier-error"]),
   ].join(" ");

   async function handleSubmit(event: FormEvent<HTMLFormElement>) {
      event.preventDefault();
      if (await onStart(identifier)) setIdentifier("");
   }

   return (
      <form
         className="app__session-form"
         aria-label="Steam library access"
         aria-busy={isStarting}
         onSubmit={handleSubmit}
      >
         <label htmlFor="steam-identifier">Steam ID or profile URL</label>
         <p className="app__session-form-help" id="steam-identifier-help">
            Paste a 17-digit Steam ID or Steam Community profile URL.
         </p>
         <input
            className="app__input"
            id="steam-identifier"
            name="identifier"
            value={identifier}
            aria-describedby={descriptionIds}
            onChange={(event) => setIdentifier(event.target.value)}
            disabled={isStarting}
            autoComplete="off"
         />
         <button
            className="app__primary-button"
            type="submit"
            disabled={isStarting || identifier.trim().length === 0}
         >
            {isStarting ? "Loading Steam profile…" : "Continue with Steam"}
         </button>
         {error !== null && (
            <p
               className="app__session-form-error"
               id="steam-identifier-error"
               role="alert"
            >
               {error}
            </p>
         )}
      </form>
   );
}

export default SteamSessionForm;
