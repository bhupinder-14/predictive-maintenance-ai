import type { EquipmentHistoryEntry, PredictionSummaryRecord, SensorReadingRecord } from "@/api/equipment";

export interface EquipmentAnalytics {
  readings: SensorReadingRecord[];
  anomalyPredictions: PredictionSummaryRecord[];
  failurePredictions: PredictionSummaryRecord[];
  normalCount: number;
  anomalyCount: number;
  anomalyVersions: Record<string, number>;
  failureVersions: Record<string, number>;
}

/** Deduplicate persisted entity IDs before deriving loaded-history summaries. */
export function buildEquipmentAnalytics(entries: EquipmentHistoryEntry[]): EquipmentAnalytics {
  const readingsById = new Map<number, SensorReadingRecord>();
  const predictionsById = new Map<string, PredictionSummaryRecord>();
  for (const entry of entries) {
    readingsById.set(entry.reading.id, entry.reading);
    for (const prediction of entry.predictions) predictionsById.set(prediction.id, prediction);
  }

  const readings = [...readingsById.values()].sort((left, right) =>
    Date.parse(left.timestamp) - Date.parse(right.timestamp) || left.id - right.id,
  );
  const predictions = [...predictionsById.values()];
  const anomalyPredictions = predictions.filter((item) => item.anomaly_score !== null && item.is_anomaly !== null);
  const failurePredictions = predictions.filter((item) => item.failure_probability !== null);
  const countVersions = (items: PredictionSummaryRecord[]) => items.reduce<Record<string, number>>((counts, item) => {
    counts[item.model_version] = (counts[item.model_version] ?? 0) + 1;
    return counts;
  }, {});

  return {
    readings,
    anomalyPredictions,
    failurePredictions,
    normalCount: anomalyPredictions.filter((item) => item.is_anomaly === false).length,
    anomalyCount: anomalyPredictions.filter((item) => item.is_anomaly === true).length,
    anomalyVersions: countVersions(anomalyPredictions),
    failureVersions: countVersions(failurePredictions),
  };
}
