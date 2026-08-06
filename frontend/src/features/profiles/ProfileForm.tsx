import { useState, type FormEvent } from "react";

type ProfileFormProps = {
   error: string | null;
   isAdding: boolean;
   onAdd: (identifier: string) => Promise<boolean>;
};

/** Collects the Steam identifier used to import a local profile. */
function ProfileForm({ error, isAdding, onAdd }: ProfileFormProps) {
   const [identifier, setIdentifier] = useState("");

   async function handleSubmit(event: FormEvent<HTMLFormElement>) {
      event.preventDefault();

      if (await onAdd(identifier)) {
         setIdentifier("");
      }
   }

   return (
      <>
         <form className="app__profile-form" onSubmit={handleSubmit}>
            <label htmlFor="steam-identifier">Steam ID or profile URL</label>
            <input
               className="app__input"
               id="steam-identifier"
               name="identifier"
               value={identifier}
               onChange={(event) => setIdentifier(event.target.value)}
               disabled={isAdding}
            />
            <button
               className="app__primary-button"
               type="submit"
               disabled={isAdding || identifier.trim().length === 0}
            >
               {isAdding ? "Adding profile..." : "Add profile"}
            </button>
         </form>

         {error !== null && <p role="alert">{error}</p>}
      </>
   );
}

export default ProfileForm;
