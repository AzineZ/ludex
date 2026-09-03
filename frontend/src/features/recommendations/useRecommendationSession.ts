import { useCallback, useEffect, useRef, useState } from "react";

import type {
   FinalRecommendationItemResponse,
   RecommendationPreference,
} from "../../api";
import {
   acceptRecommendation,
   beginRecommendationRefinement,
   completeRecommendationRefinement,
   createIdleRecommendationSession,
   createRecommendationSession,
   failRecommendationRefinement,
   showAnotherRecommendation,
   startOverRecommendationSession,
   type RecommendationSessionState,
   updateRecommendationSessionDraft,
} from "./recommendationSession";


export type RecommendationSessionOwner = {
   state: RecommendationSessionState;
   initialize: (
      preference: RecommendationPreference,
      items: readonly FinalRecommendationItemResponse[]
   ) => void;
   showAnother: (rejectedSteamAppId: number) => void;
   playThis: (acceptedSteamAppId: number) => void;
   updateDraft: (draftPreference: RecommendationPreference) => void;
   beginRefinement: (validatedPreference: RecommendationPreference) => void;
   completeRefinement: (
      items: readonly FinalRecommendationItemResponse[]
   ) => void;
   failRefinement: () => void;
   startOver: () => void;
};

export function useRecommendationSession(
   sessionEpoch: number | null
): RecommendationSessionOwner {
   const [state, setState] = useState<RecommendationSessionState>(
      createIdleRecommendationSession
   );
   const previousSessionEpochRef = useRef(sessionEpoch);

   useEffect(() => {
      if (previousSessionEpochRef.current !== sessionEpoch) {
         previousSessionEpochRef.current = sessionEpoch;
         setState(createIdleRecommendationSession());
      }
   }, [sessionEpoch]);

   const initialize = useCallback((
      preference: RecommendationPreference,
      items: readonly FinalRecommendationItemResponse[]
   ) => {
      setState(createRecommendationSession(preference, items));
   }, []);

   const showAnother = useCallback((rejectedSteamAppId: number) => {
      setState((current) => current.phase === "active"
         ? showAnotherRecommendation(current, rejectedSteamAppId)
         : current);
   }, []);

   const playThis = useCallback((acceptedSteamAppId: number) => {
      setState((current) => current.phase === "active"
         ? acceptRecommendation(current, acceptedSteamAppId)
         : current);
   }, []);

   const updateDraft = useCallback((draftPreference: RecommendationPreference) => {
      setState((current) => (
         current.phase === "active" || current.phase === "editing"
      )
         ? updateRecommendationSessionDraft(current, draftPreference)
         : current);
   }, []);

   const beginRefinement = useCallback((
      validatedPreference: RecommendationPreference
   ) => {
      setState((current) => current.phase === "editing"
         ? beginRecommendationRefinement(current, validatedPreference)
         : current);
   }, []);

   const completeRefinement = useCallback((
      items: readonly FinalRecommendationItemResponse[]
   ) => {
      setState((current) => current.phase === "refining"
         ? completeRecommendationRefinement(current, items)
         : current);
   }, []);

   const failRefinement = useCallback(() => {
      setState((current) => current.phase === "refining"
         ? failRecommendationRefinement(current)
         : current);
   }, []);

   const startOver = useCallback(() => {
      setState((current) => startOverRecommendationSession(current));
   }, []);

   return {
      state,
      initialize,
      showAnother,
      playThis,
      updateDraft,
      beginRefinement,
      completeRefinement,
      failRefinement,
      startOver,
   };
}
