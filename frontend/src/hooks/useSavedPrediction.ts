import { useQuery } from "@tanstack/react-query";
import { getSavedPrediction } from "@/api/predictions";

export function useSavedPrediction(predictionId: string | null) {
  return useQuery({
    queryKey: ["saved-prediction", predictionId],
    enabled: predictionId !== null,
    queryFn: () => {
      if (predictionId === null) throw new Error("Select a saved prediction.");
      return getSavedPrediction(predictionId);
    },
    staleTime: 60_000,
    retry: false,
  });
}
