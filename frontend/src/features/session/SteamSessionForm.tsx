import { useState, type FormEvent } from "react";

const SAMPLE_STEAM_ID = "76561198342733684";

type SteamSessionFormProps = {
   error: string | null;
   isStarting: boolean;
   onStart: (
      identifier: string,
      authorizedUseAcknowledged: boolean
   ) => Promise<boolean>;
};

/** Collects the Steam identifier used to authorize this browser session. */
function SteamSessionForm({ error, isStarting, onStart }: SteamSessionFormProps) {
   const [identifier, setIdentifier] = useState("");
   const [authorizedUseAcknowledged, setAuthorizedUseAcknowledged] =
      useState(false);
   const descriptionIds = [
      "steam-identifier-help",
      "steam-sample-help",
      ...(error === null ? [] : ["steam-identifier-error"]),
   ].join(" ");

   async function handleSubmit(event: FormEvent<HTMLFormElement>) {
      event.preventDefault();
      if (!authorizedUseAcknowledged) return;
      if (await onStart(identifier, authorizedUseAcknowledged)) {
         setIdentifier("");
         setAuthorizedUseAcknowledged(false);
      }
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
         <p className="app__session-form-sample" id="steam-sample-help">
            Prefer not to use your own Steam ID? Try the Ludex sample library by
            pasting this steam ID: <code>{SAMPLE_STEAM_ID}</code>
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
         <label className="app__session-acknowledgment">
            <input
               type="checkbox"
               name="authorized-use"
               checked={authorizedUseAcknowledged}
               onChange={(event) =>
                  setAuthorizedUseAcknowledged(event.target.checked)
               }
               disabled={isStarting}
               required
            />
            <span>
               I confirm I am authorized to request this profile&apos;s cached or
               public Steam data. Entering a Steam ID does not verify ownership.
               Read the <a href="/privacy">privacy and data notice</a>.
            </span>
         </label>
         <button
            className="app__primary-button"
            type="submit"
            disabled={
               isStarting ||
               identifier.trim().length === 0 ||
               !authorizedUseAcknowledged
            }
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
