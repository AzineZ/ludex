import "./App.css";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
   ApiError,
   createProfile,
   getHealth,
   getProfile,
   listProfiles,
   refreshProfile,
   type ProfileSummaryResponse,
   type ProfileDetailResponse,
} from "./api";
import ludexLogo from "./assets/ludex_logo.png";

type ConnectionState = "checking" | "connected" | "unavailable";
type ProfileListState = "loading" | "ready" | "unavailable";
type ProfileDetailState = "idle" | "loading" | "ready" | "unavailable";
type RefreshState = "idle" | "refreshing" | "succeeded" | "failed";

const SELECTED_PROFILE_STORAGE_KEY = "ludex.selectedProfileId";

/** Reads and validates the previously selected local profile ID. */
function getStoredProfileId(): number | null {
   const storedProfileId = window.localStorage.getItem(
      SELECTED_PROFILE_STORAGE_KEY
   );

   if (storedProfileId === null) {
      return null;
   }

   const profileId = Number(storedProfileId);

   return Number.isSafeInteger(profileId) && profileId > 0 ? profileId : null;
}

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
   const [selectedProfileId, setSelectedProfileId] = useState<number | null>(
      getStoredProfileId
   );
   const selectedProfileIdRef = useRef(selectedProfileId);
   selectedProfileIdRef.current = selectedProfileId;
   const [profileDetailState, setProfileDetailState] =
      useState<ProfileDetailState>("idle");
   const [selectedProfileDetail, setSelectedProfileDetail] =
      useState<ProfileDetailResponse | null>(null);
   const [profileDetailError, setProfileDetailError] = useState<string | null>(
      null
   );
   const [identifier, setIdentifier] = useState("");
   const [isAddingProfile, setIsAddingProfile] = useState(false);
   const [addProfileError, setAddProfileError] = useState<string | null>(null);
   const [refreshState, setRefreshState] = useState<RefreshState>("idle");
   const [refreshError, setRefreshError] = useState<string | null>(null);

   useEffect(() => {
      getHealth()
         .then(() => setConnectionState("connected"))
         .catch(() => setConnectionState("unavailable"));
   }, []);

   useEffect(() => {
      listProfiles()
         .then((savedProfiles) => {
            setProfiles(savedProfiles);
            setSelectedProfileId((currentProfileId) => {
               if (currentProfileId === null) {
                  return null;
               }

               const profileStillExists = savedProfiles.some(
                  (profile) => profile.id === currentProfileId
               );

               return profileStillExists ? currentProfileId : null;
            });
            setProfileListState("ready");
         })
         .catch(() => {
            setProfileListState("unavailable");
         });
   }, []);

   useEffect(() => {
      if (selectedProfileId === null) {
         window.localStorage.removeItem(SELECTED_PROFILE_STORAGE_KEY);
         return;
      }

      window.localStorage.setItem(
         SELECTED_PROFILE_STORAGE_KEY,
         String(selectedProfileId)
      );
   }, [selectedProfileId]);

   useEffect(() => {
      if (profileListState !== "ready" || selectedProfileId === null) {
         setSelectedProfileDetail(null);
         setProfileDetailError(null);
         setProfileDetailState("idle");
         return;
      }

      let requestIsCurrent = true;

      setRefreshState("idle");
      setRefreshError(null);
      setSelectedProfileDetail(null);
      setProfileDetailError(null);
      setProfileDetailState("loading");

      getProfile(selectedProfileId)
         .then((profile) => {
            if (!requestIsCurrent) {
               return;
            }

            setSelectedProfileDetail(profile);
            setProfileDetailState("ready");
         })
         .catch((error) => {
            if (!requestIsCurrent) {
               return;
            }

            setProfileDetailError(
               error instanceof ApiError
                  ? error.message
                  : "The game library could not be loaded."
            );
            setProfileDetailState("unavailable");
         });

      return () => {
         requestIsCurrent = false;
      };
   }, [profileListState, selectedProfileId]);

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

   /** Refreshes the selected profile and its Steam library. */
   async function handleRefreshProfile(): Promise<void> {
      if (selectedProfileId === null || refreshState === "refreshing") {
         return;
      }

      const refreshingProfileId = selectedProfileId;

      setRefreshState("refreshing");
      setRefreshError(null);

      try {
         const refreshedProfile = await refreshProfile(refreshingProfileId);

         setProfiles((currentProfiles) =>
            upsertProfile(currentProfiles, refreshedProfile)
         );

         if (selectedProfileIdRef.current !== refreshingProfileId) {
            return;
         }

         setSelectedProfileDetail(refreshedProfile);
         setProfileDetailState("ready");
         setProfileDetailError(null);
         setRefreshState("succeeded");
      } catch (error) {
         if (selectedProfileIdRef.current !== refreshingProfileId) {
            return;
         }

         setRefreshError(
            error instanceof ApiError
               ? error.message
               : "The Steam library could not be refreshed."
         );
         setRefreshState("failed");
      }
   }

   const selectedProfileSummary =
      profiles.find((profile) => profile.id === selectedProfileId) ?? null;

   return (
      <main className="app">
         <div className="app__signal-field" aria-hidden="true">
            <span className="app__signal-ring app__signal-ring--one" />
            <span className="app__signal-ring app__signal-ring--two" />
            <span className="app__signal-ring app__signal-ring--three" />
            <span className="app__signal-ring app__signal-ring--four" />
            <span className="app__hazard app__hazard--one">!</span>
            <span className="app__hazard app__hazard--two">+</span>
            <span className="app__hazard app__hazard--three">×</span>
            <span className="app__hazard app__hazard--four">◆</span>
         </div>
         <section className="app__content">
            <header className="app__hero">
               <h1 className="app__logo-heading">
                  <img
                     className="app__logo"
                     src={ludexLogo}
                     alt="Ludex — Your next game awaits"
                  />
               </h1>
               <p className="app__intro">
                  Ludex helps you choose what to play from your existing Steam
                  library.
               </p>

               <p className={`app__status app__status--${connectionState}`}>
                  Backend: {connectionState}
               </p>
            </header>

            <section
               className="app__profiles"
               aria-labelledby="profiles-heading"
            >
               <h2 id="profiles-heading">Steam profiles</h2>

               <form className="app__profile-form" onSubmit={handleAddProfile}>
                  <label htmlFor="steam-identifier">
                     Steam ID or profile URL
                  </label>
                  <input
                     className="app__input"
                     id="steam-identifier"
                     name="identifier"
                     value={identifier}
                     onChange={(event) => setIdentifier(event.target.value)}
                     disabled={isAddingProfile}
                  />
                  <button
                     className="app__primary-button"
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
                  <ul className="app__profile-list">
                     {profiles.map((profile) => (
                        <li key={profile.id}>
                           <button
                              className="app__profile-button"
                              type="button"
                              aria-pressed={selectedProfileId === profile.id}
                              onClick={() => setSelectedProfileId(profile.id)}
                           >
                              {profile.display_name}
                           </button>
                        </li>
                     ))}
                  </ul>
               )}
               {selectedProfileSummary !== null && (
                  <p className="app__selection">
                     Selected profile:{" "}
                     <strong>{selectedProfileSummary.display_name}</strong>
                  </p>
               )}
               {profileDetailState === "loading" && (
                  <p>Loading game library...</p>
               )}

               {profileDetailState === "unavailable" && (
                  <p role="alert">
                     {profileDetailError ??
                        "The game library could not be loaded."}
                  </p>
               )}

               {profileDetailState === "ready" &&
                  selectedProfileDetail !== null && (
                     <section
                        className="app__library"
                        aria-labelledby="library-heading"
                     >
                        <h3 id="library-heading">Game library</h3>
                        <button
                           className="app__secondary-button"
                           type="button"
                           onClick={handleRefreshProfile}
                           disabled={refreshState === "refreshing"}
                        >
                           {refreshState === "refreshing"
                              ? "Refreshing library..."
                              : "Refresh library"}
                        </button>

                        {refreshState === "succeeded" && (
                           <p role="status">Steam library refreshed.</p>
                        )}

                        {refreshState === "failed" && (
                           <p role="alert">
                              {refreshError ??
                                 "The Steam library could not be refreshed."}
                           </p>
                        )}

                        <p className="app__game-count">
                           {selectedProfileDetail.games.length}{" "}
                           {selectedProfileDetail.games.length === 1
                              ? "game"
                              : "games"}
                        </p>

                        {selectedProfileDetail.games.length === 0 && (
                           <p>This Steam library is empty.</p>
                        )}

                        {selectedProfileDetail.games.length > 0 && (
                           <ul className="app__game-list">
                              {selectedProfileDetail.games.map((game) => (
                                 <li
                                    className="app__game"
                                    key={game.steam_app_id}
                                 >
                                    <span className="app__game-name">
                                       {game.name}
                                    </span>
                                    <span className="app__playtime">
                                       {game.playtime_minutes} minutes played
                                    </span>
                                 </li>
                              ))}
                           </ul>
                        )}
                     </section>
                  )}
            </section>
         </section>
      </main>
   );
}

export default App;
