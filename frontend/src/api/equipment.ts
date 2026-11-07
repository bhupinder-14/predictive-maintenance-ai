import { apiClient } from "./client";

export type MachineType = "L" | "M" | "H";

export interface EquipmentRecord {
  id: number;
  name: string;
  equipment_type: string;
  location: string | null;
  created_at: string;
}

export interface SensorReadingRecord {
  id: number;
  equipment_id: number;
  timestamp: string;
  Type: MachineType;
  "Air temperature [K]": number;
  "Process temperature [K]": number;
  "Rotational speed [rpm]": number;
  "Torque [Nm]": number;
  "Tool wear [min]": number;
  source: string;
}

export interface PredictionSummaryRecord {
  id: string;
  model_version: string;
  anomaly_score: number | null;
  is_anomaly: boolean | null;
  failure_probability: number | null;
  latency_ms: number;
  created_at: string;
}

export interface EquipmentHistoryEntry {
  reading: SensorReadingRecord;
  predictions: PredictionSummaryRecord[];
}

export interface EquipmentHistoryResponse {
  equipment: EquipmentRecord;
  items: EquipmentHistoryEntry[];
}

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function isEquipment(value: unknown): value is EquipmentRecord {
  return isObject(value) && Number.isSafeInteger(value.id) && Number(value.id) > 0 &&
    typeof value.name === "string" && value.name.length > 0 && typeof value.equipment_type === "string" &&
    (typeof value.location === "string" || value.location === null) && isTimestamp(value.created_at);
}

function isSensorReading(value: unknown): value is SensorReadingRecord {
  return isObject(value) && Number.isSafeInteger(value.id) && Number(value.id) > 0 &&
    Number.isSafeInteger(value.equipment_id) && Number(value.equipment_id) > 0 && isTimestamp(value.timestamp) &&
    (value.Type === "L" || value.Type === "M" || value.Type === "H") &&
    isFiniteNumber(value["Air temperature [K]"]) && isFiniteNumber(value["Process temperature [K]"]) &&
    isFiniteNumber(value["Rotational speed [rpm]"]) && isFiniteNumber(value["Torque [Nm]"]) &&
    isFiniteNumber(value["Tool wear [min]"]) && typeof value.source === "string";
}

function isPredictionSummary(value: unknown): value is PredictionSummaryRecord {
  if (!isObject(value) || typeof value.id !== "string" || value.id.length === 0 ||
      typeof value.model_version !== "string" || !isTimestamp(value.created_at) ||
      !isFiniteNumber(value.latency_ms) || value.latency_ms < 0) return false;
  const anomaly = value.anomaly_score !== null && isFiniteNumber(value.anomaly_score) &&
    typeof value.is_anomaly === "boolean" && value.failure_probability === null;
  const failure = value.anomaly_score === null && value.is_anomaly === null &&
    isFiniteNumber(value.failure_probability) && value.failure_probability >= 0 && value.failure_probability <= 1;
  return anomaly || failure;
}

export function isEquipmentRecord(value: unknown): value is EquipmentRecord {
  return isEquipment(value);
}

export function parseEquipmentList(value: unknown): EquipmentRecord[] {
  if (!Array.isArray(value) || !value.every(isEquipment)) throw new Error("Equipment response is invalid.");
  return value;
}

export function parseEquipmentHistory(value: unknown, expectedEquipmentId: number): EquipmentHistoryResponse {
  if (!isObject(value) || !isEquipment(value.equipment) || value.equipment.id !== expectedEquipmentId ||
      !Array.isArray(value.items) || !value.items.every((entry) => isHistoryEntry(entry, expectedEquipmentId))) {
    throw new Error("Equipment history response is invalid.");
  }
  return { equipment: value.equipment, items: value.items };
}

function isHistoryEntry(value: unknown, equipmentId: number): value is EquipmentHistoryEntry {
  return isObject(value) && isSensorReading(value.reading) && value.reading.equipment_id === equipmentId &&
    Array.isArray(value.predictions) && value.predictions.every(isPredictionSummary);
}

export async function getEquipment(limit = 100, offset = 0): Promise<EquipmentRecord[]> {
  const response = await apiClient.get<unknown>("/equipment", { params: { limit, offset } });
  return parseEquipmentList(response.data);
}

export async function getEquipmentHistory(
  equipmentId: number,
  limit = 50,
  offset = 0,
): Promise<EquipmentHistoryResponse> {
  const response = await apiClient.get<unknown>(`/equipment/${equipmentId}/history`, { params: { limit, offset } });
  return parseEquipmentHistory(response.data, equipmentId);
}
