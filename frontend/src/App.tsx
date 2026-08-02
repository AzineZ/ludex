import "./App.css";
import { useEffect, useState } from "react";
import { getHealth, listProfiles, type ProfileSummaryResponse } from "./api";

type ConnectionState = "checking" | "connected" | "unavailable";
type ProfileListState = "loading" | "ready" | "unavailable";

function App() {
   const [connectionState, setConnectionState] =
      useState<ConnectionState>("checking");
   const [profileListState, setProfileListState] =
      useState<ProfileListState>("loading");
   const [profiles, setProfiles] = useState<ProfileSummaryResponse[]>([]);

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
