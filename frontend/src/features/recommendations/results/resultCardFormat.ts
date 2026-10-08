export function formatMinutes(minutes: number): string {
   const hours = Math.floor(minutes / 60);
   const remainingMinutes = minutes % 60;

   if (hours === 0) {
      return `${remainingMinutes} min`;
   }
   if (remainingMinutes === 0) {
      return `${hours} hr`;
   }
   return `${hours} hr ${remainingMinutes} min`;
}

export function getRecommendationCoverUrl(coverUrl: string): string {
   return coverUrl.replace(
      /^(https:\/\/images\.igdb\.com\/igdb\/image\/upload\/)t_cover_big(?=\/)/,
      "$1t_cover_big_2x"
   );
}

export function describePlaytime(profilePlaytimeMinutes: number): string {
   return profilePlaytimeMinutes === 0
      ? "Not played yet"
      : `${formatMinutes(profilePlaytimeMinutes)} played`;
}

export function describeCompletion(
   normalCompletionSeconds: number | null
): string {
   return normalCompletionSeconds === null
      ? "Unavailable"
      : formatMinutes(Math.round(normalCompletionSeconds / 60));
}

export function showAnotherLabel(
   remainingAlternatives: number | undefined
): string {
   if (remainingAlternatives === 0) {
      return "No alternatives left";
   }
   return remainingAlternatives === undefined
      ? "Show another"
      : `Show another · ${remainingAlternatives} left`;
}
