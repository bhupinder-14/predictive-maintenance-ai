import { useMutation, useQueryClient } from "@tanstack/react-query";
import { predictAnomaly, predictFailure, type PredictionInput } from "@/api/predictions";

function invalidateEquipmentHistory(queryClient: ReturnType<typeof useQueryClient>, equipmentId: number) {
  void queryClient.invalidateQueries({ queryKey: ["equipment-list"] });
  void queryClient.invalidateQueries({ queryKey: ["equipment-history", equipmentId] });
}

export function useAnomalyPrediction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PredictionInput) => predictAnomaly(input),
    onSuccess: (result) => invalidateEquipmentHistory(queryClient, result.equipment_id),
  });
}

export function useFailurePrediction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PredictionInput) => predictFailure(input),
    onSuccess: (result) => invalidateEquipmentHistory(queryClient, result.equipment_id),
  });
}
