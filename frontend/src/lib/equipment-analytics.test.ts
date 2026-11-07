import { describe, expect, it } from "vitest";
import { buildEquipmentAnalytics } from "./equipment-analytics";
import type { EquipmentHistoryEntry } from "@/api/equipment";

const reading = (id: number, timestamp: string): EquipmentHistoryEntry["reading"] => ({
  id, equipment_id: 4, timestamp, Type: "M", "Air temperature [K]": 300,
  "Process temperature [K]": 310, "Rotational speed [rpm]": 1400,
  "Torque [Nm]": 40, "Tool wear [min]": 60, source: "api",
});
const anomaly = { id: "a1", model_version: "anomaly_v1", anomaly_score: -0.4, is_anomaly: true, failure_probability: null, latency_ms: 2, created_at: "2026-10-31T10:00:00Z" };
const failure = { id: "f1", model_version: "failure_v1", anomaly_score: null, is_anomaly: null, failure_probability: 0.4, latency_ms: 3, created_at: "2026-10-31T10:01:00Z" };

describe("equipment analytics", () => {
  it("orders actual readings chronologically and deduplicates readings and predictions by persisted IDs", () => {
    const entries: EquipmentHistoryEntry[] = [
      { reading: reading(2, "2026-10-31T10:02:00Z"), predictions: [anomaly, failure] },
      { reading: reading(1, "2026-10-31T10:01:00Z"), predictions: [anomaly] },
    ];
    const result = buildEquipmentAnalytics(entries);
    expect(result.readings.map((item) => item.id)).toEqual([1, 2]);
    expect(result.anomalyPredictions).toHaveLength(1);
    expect(result.failurePredictions).toHaveLength(1);
    expect(result.anomalyCount).toBe(1);
    expect(result.normalCount).toBe(0);
    expect(result.anomalyVersions).toEqual({ anomaly_v1: 1 });
    expect(result.failureVersions).toEqual({ failure_v1: 1 });
  });

  it("does not turn failure estimator output into a predicted class", () => {
    const result = buildEquipmentAnalytics([{ reading: reading(1, "2026-10-31T10:00:00Z"), predictions: [failure] }]);
    expect(result.failurePredictions[0]).toHaveProperty("failure_probability", 0.4);
    expect(result.failurePredictions[0]).not.toHaveProperty("predicted_class");
  });
});
