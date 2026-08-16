import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProfilesSection from "../features/profiles/ProfilesSection";
import { useProfiles } from "../features/profiles/useProfiles";

vi.mock("../features/profiles/useProfiles", () => ({
   useProfiles: vi.fn(),
}));
vi.mock("../features/profiles/ProfileForm", () => ({ default: () => null }));
vi.mock("../features/profiles/ProfileSelector", () => ({ default: () => null }));
vi.mock("../features/profiles/GameLibrary", () => ({ default: () => null }));
vi.mock("../features/recommendations/ReferenceSelectionSection", () => ({
   default: ({ profileId }: { profileId: number | null }) => (
      <p>Recommendation profile: {profileId ?? "none"}</p>
   ),
}));

const mockedUseProfiles = vi.mocked(useProfiles);

function profilesResult(selectedProfileId: number | null) {
   return {
      addProfile: vi.fn(),
      addProfileError: null,
      isAddingProfile: false,
      profileDetailError: null,
      profileDetailState: "idle" as const,
      profileListState: "ready" as const,
      profiles: [],
      refreshError: null,
      refreshSelectedProfile: vi.fn(),
      refreshState: "idle" as const,
      selectedProfileDetail: null,
      selectedProfileId,
      selectedProfileSummary: null,
      selectProfile: vi.fn(),
   };
}

describe("ProfilesSection recommendation composition", () => {
   beforeEach(() => mockedUseProfiles.mockReset());

   it("passes no profile to the recommendation workflow initially", () => {
      mockedUseProfiles.mockReturnValue(profilesResult(null));
      render(<ProfilesSection />);
      expect(screen.getByText("Recommendation profile: none")).toBeInTheDocument();
   });

   it("passes the selected local profile ID to the recommendation workflow", () => {
      mockedUseProfiles.mockReturnValue(profilesResult(7));
      render(<ProfilesSection />);
      expect(screen.getByText("Recommendation profile: 7")).toBeInTheDocument();
   });
});
