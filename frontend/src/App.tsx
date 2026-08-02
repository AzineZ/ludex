import "./App.css";
import { useEffect, useState, type FormEvent } from "react";
import {
   ApiError,
   createProfile,
   getHealth,
   listProfiles,
   type ProfileSummaryResponse,
} from "./api";

type ConnectionState = "checking" | "connected" | "unavailable";
type ProfileListState = "loading" | "ready" | "unavailable";

/** Inserts or replaces a profile while preserving display-name order. */
function upsertProfile(
   profiles: ProfileSummaryResponse[],
   updatedProfile: ProfileSummaryResponse
): ProfileSummaryResponse[] {
   return [
      ...profiles.filter((profile) => profile.id !== updatedProfile.id),
      updatedProfile,
   ].sort(
      (firstProfile, secondProfile) =>
         firstProfile.display_name.localeCompare(secondProfile.display_name) ||
         firstProfile.id - secondProfile.id
   );
}

/** Displays Ludex's connection state and local Steam profiles. */
function App() {
   const [connectionState, setConnectionState] =
      useState<ConnectionState>("checking");
   const [profileListState, setProfileListState] =
      useState<ProfileListState>("loading");
   const [profiles, setProfiles] = useState<ProfileSummaryResponse[]>([]);
   const [identifier, setIdentifier] = useState("");
   const [isAddingProfile, setIsAddingProfile] = useState(false);
   const [addProfileError, setAddProfileError] = useState<string | null>(null);

   useEffect(() => {
      getHealth()
         .then(() => setConnectionState("connected"))
         .catch(() => setConnectionState("unavailable"));
   }, []);

   useEffect(() => {
      listProfiles()
         .then((savedProfiles) => {
            setProfiles(savedProfiles);
            setProfileListState("ready");
         })
         .catch(() => {
            setProfileListState("unavailable");
         });
   }, []);

   /** Imports a Steam profile submitted through the form. */
   async function handleAddProfile(
      event: FormEvent<HTMLFormElement>
   ): Promise<void> {
      event.preventDefault();

      const normalizedIdentifier = identifier.trim();

      if (!normalizedIdentifier || isAddingProfile) {
         return;
      }

      setIsAddingProfile(true);
      setAddProfileError(null);

      try {
         const importedProfile = await createProfile(normalizedIdentifier);

         setProfiles((currentProfiles) =>
            upsertProfile(currentProfiles, importedProfile)
         );
         setProfileListState("ready");
         setIdentifier("");
      } catch (error) {
         setAddProfileError(
            error instanceof ApiError
               ? error.message
               : "The profile could not be added."
         );
      } finally {
         setIsAddingProfile(false);
      }
   }

   return (
      <main className="app">
         <section>
            <p className="app__name">Ludex</p>
            <h1>Find your next game.</h1>
            <p>
               Ludex helps you choose what to play from your existing Steam
               library.
            </p>

            <p className={`app__status app__status--${connectionState}`}>
               Backend: {connectionState}
            </p>

            <div className="app__profiles" aria-labelledby="profiles-heading">
               <h2 id="profiles-heading">Steam profiles</h2>

               <form onSubmit={handleAddProfile}>
                  <label htmlFor="steam-identifier">
                     Steam ID or profile URL
                  </label>
                  <input
                     id="steam-identifier"
                     name="identifier"
                     value={identifier}
                     onChange={(event) => setIdentifier(event.target.value)}
                     disabled={isAddingProfile}
                  />
                  <button
                     type="submit"
                     disabled={
                        isAddingProfile || identifier.trim().length === 0
                     }
                  >
                     {isAddingProfile ? "Adding profile..." : "Add profile"}
                  </button>
               </form>

               {addProfileError !== null && (
                  <p role="alert">{addProfileError}</p>
               )}

               {profileListState === "loading" && <p>Loading profiles...</p>}

               {profileListState === "unavailable" && (
                  <p role="alert">Saved profiles are currently unavailable.</p>
               )}

               {profileListState === "ready" && profiles.length === 0 && (
                  <p>No Steam profiles have been added yet.</p>
               )}

               {profileListState === "ready" && profiles.length > 0 && (
                  <ul>
                     {profiles.map((profile) => (
                        <li key={profile.id}>{profile.display_name}</li>
                     ))}
                  </ul>
               )}
            </div>
         </section>
      </main>
   );
}

export default App;
