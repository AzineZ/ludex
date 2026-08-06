import type { ProfileSummaryResponse } from "../../api";
import type { ProfileListState } from "./types";

type ProfileSelectorProps = {
   listState: ProfileListState;
   profiles: ProfileSummaryResponse[];
   selectedProfileId: number | null;
   selectedProfile: ProfileSummaryResponse | null;
   onSelect: (profileId: number) => void;
};

/** Displays profile-list states and lets the user choose one profile. */
function ProfileSelector({
   listState,
   profiles,
   selectedProfileId,
   selectedProfile,
   onSelect,
}: ProfileSelectorProps) {
   return (
      <>
         {listState === "loading" && <p>Loading profiles...</p>}

         {listState === "unavailable" && (
            <p role="alert">Saved profiles are currently unavailable.</p>
         )}

         {listState === "ready" && profiles.length === 0 && (
            <p>No Steam profiles have been added yet.</p>
         )}

         {listState === "ready" && profiles.length > 0 && (
            <ul className="app__profile-list">
               {profiles.map((profile) => (
                  <li key={profile.id}>
                     <button
                        className="app__profile-button"
                        type="button"
                        aria-pressed={selectedProfileId === profile.id}
                        onClick={() => onSelect(profile.id)}
                     >
                        {profile.display_name}
                     </button>
                  </li>
               ))}
            </ul>
         )}

         {selectedProfile !== null && (
            <p className="app__selection">
               Selected profile: <strong>{selectedProfile.display_name}</strong>
            </p>
         )}
      </>
   );
}

export default ProfileSelector;
