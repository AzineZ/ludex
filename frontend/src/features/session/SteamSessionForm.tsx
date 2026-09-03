import { useState, type FormEvent } from "react";

type SteamSessionFormProps = {
   error: string | null;
   isStarting: boolean;
   onStart: (identifier: string) => Promise<boolean>;
};

/** Collects the Steam identifier used to authorize this browser session. */
function SteamSessionForm({ error, isStarting, onStart }: SteamSessionFormProps) {
   const [identifier, setIdentifier] = useState("");

   async function handleSubmit(event: FormEvent<HTMLFormElement>) {
      event.preventDefault();
      if (await onStart(identifier)) setIdentifier("");
   }

   return (
      <>
         <form className="app__session-form" onSubmit={handleSubmit}>
            <label htmlFor="steam-identifier">Steam ID or profile URL</label>
            <input
               className="app__input"
               id="steam-identifier"
               name="identifier"
               value={identifier}
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
         </form>
         {error !== null && <p role="alert">{error}</p>}
      </>
   );
}

export default SteamSessionForm;
