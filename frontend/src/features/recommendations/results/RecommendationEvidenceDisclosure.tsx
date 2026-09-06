import { useId } from "react";

import type {
   FacetKind,
   FacetLabelResponse,
   FacetMatchState,
   FactualScoreEvidenceResponse,
} from "../../../api";


type RecommendationEvidenceDisclosureProps = {
   evidence: FactualScoreEvidenceResponse;
   facetLabels: readonly FacetLabelResponse[];
};

const FACET_KIND_LABELS: Record<FacetKind, string> = {
   genre: "Genre",
   theme: "Theme",
   keyword: "Keyword",
   game_mode: "Game mode",
};

const MATCH_STATE_LABELS: Record<FacetMatchState, string> = {
   matched: "Matched",
   not_matched: "Did not match",
   unknown: "Metadata unavailable",
};

function RecommendationEvidenceDisclosure({
   evidence,
   facetLabels,
}: RecommendationEvidenceDisclosureProps) {
   const headingId = useId();
   const labelsByIdentity = new Map(
      facetLabels.map((label) => [
         `${label.facet_kind}:${label.facet_igdb_id}`,
         label.name,
      ])
   );

   return (
      <section
         className="recommendation-evidence"
         aria-labelledby={headingId}
      >
         <h4 id={headingId}>Preference comparison</h4>
         <div className="recommendation-evidence__content">
            <p>
               This comparison uses the factual preferences you selected.
            </p>
            {evidence.contributions.length === 0 ? (
               <p>
                  No factual contribution details are available for this
                  comparison.
               </p>
            ) : (
               <ul className="recommendation-evidence__list">
                  {evidence.contributions.map((contribution, index) => {
                     const identity =
                        `${contribution.facet_kind}:${contribution.facet_igdb_id}`;
                     return (
                        <li
                           key={`${identity}:${index}`}
                           data-match-state={contribution.match_state}
                        >
                           <strong>
                              {labelsByIdentity.get(identity)
                                 ?? "Label unavailable"}
                           </strong>
                           <span>
                              {FACET_KIND_LABELS[contribution.facet_kind]}
                           </span>
                           <span>
                              {MATCH_STATE_LABELS[contribution.match_state]}
                           </span>
                        </li>
                     );
                  })}
               </ul>
            )}
         </div>
      </section>
   );
}

export default RecommendationEvidenceDisclosure;
