import type {
   PreferenceConstraints,
   RecommendationPreference,
} from "../../api";
import type { SelectedReference } from "./useReferenceSelection";

export function serializeRecommendationPreference(
   references: SelectedReference[],
   constraints: PreferenceConstraints
): RecommendationPreference {
   return {
      references: references.map((reference) => ({
         steam_app_id: reference.details.steam_app_id,
         facets: {
            genre_ids: reference.selectedFacets.genres.map((option) => option.id),
            theme_ids: reference.selectedFacets.themes.map((option) => option.id),
            keyword_ids: reference.selectedFacets.keywords.map((option) => option.id),
            game_mode_ids: reference.selectedFacets.gameModes.map(
               (option) => option.id
            ),
         },
      })),
      constraints: { ...constraints },
   };
}
