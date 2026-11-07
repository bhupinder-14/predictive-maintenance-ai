import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { getEquipment, getEquipmentHistory, parseEquipmentHistory, parseEquipmentList } from "./equipment";

afterEach(() => vi.restoreAllMocks());

const equipment = { id: 7, name: "Press A", equipment_type: "M", location: "Line 2", created_at: "2026-10-31T10:00:00Z" };
const reading = {
  id: 41, equipment_id: 7, timestamp: "2026-10-31T10:05:00Z", Type: "M",
  "Air temperature [K]": 300.2, "Process temperature [K]": 310.1,
  "Rotational speed [rpm]": 1450, "Torque [Nm]": 38.6, "Tool wear [min]": 80, source: "api",
};
const anomaly = { id: "anomaly-id", model_version: "anomaly_v1", anomaly_score: -0.42, is_anomaly: true, failure_probability: null, latency_ms: 2.1, created_at: "2026-10-31T10:05:01Z" };
const failure = { id: "failure-id", model_version: "failure_v1", anomaly_score: null, is_anomaly: null, failure_probability: 0.37, latency_ms: 3.4, created_at: "2026-10-31T10:05:02Z" };

describe("equipment API", () => {
  it("parses actual equipment records and rejects malformed entries", () => {
    expect(parseEquipmentList([equipment])).toEqual([equipment]);
    expect(() => parseEquipmentList([{ ...equipment, id: 0 }])).toThrow("Equipment response is invalid.");
  });

  it("loads equipment with the supported limit and offset parameters", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: [equipment] } as never);
    await expect(getEquipment(100, 0)).resolves.toEqual([equipment]);
    expect(get).toHaveBeenCalledWith("/equipment", { params: { limit: 100, offset: 0 } });
  });

  it("parses equipment-scoped readings and separate persisted model outputs", () => {
    const response = parseEquipmentHistory({ equipment, items: [{ reading, predictions: [anomaly, failure] }] }, 7);
    expect(response.items[0]?.reading["Torque [Nm]"]).toBe(38.6);
    expect(response.items[0]?.predictions.map((item) => item.id)).toEqual(["anomaly-id", "failure-id"]);
  });

  it("rejects cross-equipment readings or a mismatched equipment response", () => {
    expect(() => parseEquipmentHistory({ equipment, items: [{ reading: { ...reading, equipment_id: 8 }, predictions: [] }] }, 7)).toThrow("Equipment history response is invalid.");
    expect(() => parseEquipmentHistory({ equipment: { ...equipment, id: 8 }, items: [] }, 7)).toThrow("Equipment history response is invalid.");
  });

  it("uses the equipment-scoped history path and pagination parameters", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: { equipment, items: [{ reading, predictions: [anomaly, failure] }] } } as never);
    await expect(getEquipmentHistory(7, 50, 100)).resolves.toMatchObject({ equipment: { id: 7 } });
    expect(get).toHaveBeenCalledWith("/equipment/7/history", { params: { limit: 50, offset: 100 } });
  });
});
