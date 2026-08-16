import "./profiles.css";
import ReferenceSelectionSection from "../recommendations/ReferenceSelectionSection";
import GameLibrary from "./GameLibrary";
import ProfileForm from "./ProfileForm";
import ProfileSelector from "./ProfileSelector";
import { useProfiles } from "./useProfiles";

/** Composes profile import, selection, library, and refresh controls. */
function ProfilesSection() {
   const profiles = useProfiles();

   return (
      <section className="app__profiles" aria-labelledby="profiles-heading">
         <h2 id="profiles-heading">Steam profiles</h2>

         <ProfileForm
            error={profiles.addProfileError}
            isAdding={profiles.isAddingProfile}
            onAdd={profiles.addProfile}
         />

         <ProfileSelector
            listState={profiles.profileListState}
            profiles={profiles.profiles}
            selectedProfileId={profiles.selectedProfileId}
            selectedProfile={profiles.selectedProfileSummary}
            onSelect={profiles.selectProfile}
         />

         <GameLibrary
            detailState={profiles.profileDetailState}
            error={profiles.profileDetailError}
            profile={profiles.selectedProfileDetail}
            refreshError={profiles.refreshError}
            refreshState={profiles.refreshState}
            onRefresh={profiles.refreshSelectedProfile}
         />

         <ReferenceSelectionSection
            profileId={profiles.selectedProfileId}
         />
      </section>
   );
}

export default ProfilesSection;
