import axios from "axios";
import { apiClient } from "./client";
import type { MachineType } from "./equipment";

export interface PredictionInput {
  Type: MachineType;
  "Air temperature [K]": number;
  "Process temperature [K]": number;
  "Rotational speed [rpm]": number;
  "Torque [Nm]": number;
  "Tool wear [min]": number;
  equipment_id?: number;
  equipment_name?: string;
  equipment_location?: string;
}

export interface SuspiciousFeature {
  feature: string;
  standardised_value: number;
  abs_deviation: number;
}

export interface AnomalyPredictionResponse {
  prediction_id: string;
  equipment_id: number;
  reading_id: number;
  anomaly_score: number;
  classification: "normal" | "anomaly";
  model_version: string;
  prediction_timestamp: string;
  inference_latency_ms: number;
  explanation: {
    method: string;
    anomaly_score: number;
    top_suspicious_features: SuspiciousFeature[];
  };
}

export interface FailurePredictionResponse {
  prediction_id: string;
  equipment_id: number;
  reading_id: number;
  predicted_class: 0 | 1;
  failure_probability: number;
  model_version: string;
  prediction_timestamp: string;
  inference_latency_ms: number;
}

export interface SavedPredictionRecord {
  id: string;
  equipment_id: number;
  reading_id: number;
  model_version: string;
  anomaly_score: number | null;
  is_anomaly: boolean | null;
  failure_probability: number | null;
  latency_ms: number;
  created_at: string;
}

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && typeof value === "number" && value > 0;
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

export function parseAnomalyPrediction(value: unknown): AnomalyPredictionResponse {
  if (!isObject(value) || typeof value.prediction_id !== "string" || !value.prediction_id ||
      !isPositiveInteger(value.equipment_id) || !isPositiveInteger(value.reading_id) ||
      !isFiniteNumber(value.anomaly_score) || (value.classification !== "normal" && value.classification !== "anomaly") ||
      typeof value.model_version !== "string" || !value.model_version || !isTimestamp(value.prediction_timestamp) ||
      !isFiniteNumber(value.inference_latency_ms) || value.inference_latency_ms < 0 || !isObject(value.explanation) ||
      typeof value.explanation.method !== "string" || !isFiniteNumber(value.explanation.anomaly_score) ||
      !Array.isArray(value.explanation.top_suspicious_features) ||
      !value.explanation.top_suspicious_features.every(isSuspiciousFeature)) {
    throw new Error("Anomaly prediction response is invalid.");
  }
  return {
    prediction_id: value.prediction_id,
    equipment_id: value.equipment_id,
    reading_id: value.reading_id,
    anomaly_score: value.anomaly_score,
    classification: value.classification,
    model_version: value.model_version,
    prediction_timestamp: value.prediction_timestamp,
    inference_latency_ms: value.inference_latency_ms,
    explanation: {
      method: value.explanation.method,
      anomaly_score: value.explanation.anomaly_score,
      top_suspicious_features: value.explanation.top_suspicious_features,
    },
  };
}

function isSuspiciousFeature(value: unknown): value is SuspiciousFeature {
  return isObject(value) && typeof value.feature === "string" &&
    isFiniteNumber(value.standardised_value) && isFiniteNumber(value.abs_deviation) && value.abs_deviation >= 0;
}

export function parseFailurePrediction(value: unknown): FailurePredictionResponse {
  if (!isObject(value) || typeof value.prediction_id !== "string" || !value.prediction_id ||
      !isPositiveInteger(value.equipment_id) || !isPositiveInteger(value.reading_id) ||
      (value.predicted_class !== 0 && value.predicted_class !== 1) || !isFiniteNumber(value.failure_probability) ||
      value.failure_probability < 0 || value.failure_probability > 1 ||
      typeof value.model_version !== "string" || !value.model_version || !isTimestamp(value.prediction_timestamp) ||
      !isFiniteNumber(value.inference_latency_ms) || value.inference_latency_ms < 0) {
    throw new Error("Failure prediction response is invalid.");
  }
  return {
    prediction_id: value.prediction_id,
    equipment_id: value.equipment_id,
    reading_id: value.reading_id,
    predicted_class: value.predicted_class,
    failure_probability: value.failure_probability,
    model_version: value.model_version,
    prediction_timestamp: value.prediction_timestamp,
    inference_latency_ms: value.inference_latency_ms,
  };
}

export function parseSavedPrediction(value: unknown): SavedPredictionRecord {
  if (!isObject(value) || typeof value.id !== "string" || !value.id ||
      !isPositiveInteger(value.equipment_id) || !isPositiveInteger(value.reading_id) ||
      typeof value.model_version !== "string" || !value.model_version ||
      !(value.anomaly_score === null || isFiniteNumber(value.anomaly_score)) ||
      !(value.is_anomaly === null || typeof value.is_anomaly === "boolean") ||
      !(value.failure_probability === null || (isFiniteNumber(value.failure_probability) && value.failure_probability >= 0 && value.failure_probability <= 1)) ||
      !isFiniteNumber(value.latency_ms) || value.latency_ms < 0 || !isTimestamp(value.created_at)) {
    throw new Error("Saved prediction response is invalid.");
  }
  const anomaly = value.anomaly_score !== null && typeof value.is_anomaly === "boolean" && value.failure_probability === null;
  const failure = value.anomaly_score === null && value.is_anomaly === null && value.failure_probability !== null;
  if (!anomaly && !failure) throw new Error("Saved prediction model fields are inconsistent.");
  return {
    id: value.id,
    equipment_id: value.equipment_id,
    reading_id: value.reading_id,
    model_version: value.model_version,
    anomaly_score: value.anomaly_score,
    is_anomaly: value.is_anomaly,
    failure_probability: value.failure_probability,
    latency_ms: value.latency_ms,
    created_at: value.created_at,
  };
}

export async function predictAnomaly(input: PredictionInput): Promise<AnomalyPredictionResponse> {
  const response = await apiClient.post<unknown>("/predict/anomaly", input);
  return parseAnomalyPrediction(response.data);
}

export async function predictFailure(input: PredictionInput): Promise<FailurePredictionResponse> {
  const response = await apiClient.post<unknown>("/predict/failure", input);
  return parseFailurePrediction(response.data);
}

export async function getSavedPrediction(predictionId: string): Promise<SavedPredictionRecord> {
  const response = await apiClient.get<unknown>(`/predictions/${encodeURIComponent(predictionId)}`);
  const record = parseSavedPrediction(response.data);
  if (record.id !== predictionId) throw new Error("Saved prediction ID does not match the requested record.");
  return record;
}

export function predictionErrorMessage(error: unknown): string {
  if (axios.isAxiosError<{ detail?: unknown }>(error)) {
    const detail = error.response?.data?.detail;
    if (error.response?.status === 422) return validationErrorMessage(detail);
    if (typeof detail === "string") {
      const safeDetail = safePredictionDetails[detail];
      if (safeDetail) return safeDetail;
    }
    if (isPredictionOutcomeUnknown(error)) {
      return "No response was received. The API may have saved this prediction. Check the selected equipment's Prediction History before retrying; exactly-once execution is not guaranteed.";
    }
  }
  if (error instanceof Error && /response is invalid|fields are inconsistent/.test(error.message)) {
    return "The API returned a response that did not match the prediction schema.";
  }
  return "The prediction request could not be completed. Please try again.";
}

const safePredictionDetails: Record<string, string> = {
  "Anomaly model is unavailable": "Anomaly model is unavailable",
  "Failure model is unavailable": "Failure model is unavailable",
  "Prediction could not be persisted": "The prediction could not be saved.",
  "Prediction could not be completed": "The prediction could not be completed.",
  "Equipment was not found": "The selected equipment record was not found.",
  "Database is unavailable": "The prediction service database is unavailable.",
};

/** A dispatched prediction may have committed even when its response was lost. */
export function isPredictionOutcomeUnknown(error: unknown): boolean {
  if (!axios.isAxiosError(error) || error.response) return false;
  return error.code === "ECONNABORTED" || error.code === "ETIMEDOUT" ||
    error.code === "ERR_NETWORK" || error.request !== undefined;
}

const validationFieldLabels: Record<string, string> = {
  Type: "Machine type",
  "Air temperature [K]": "Air temperature",
  "Process temperature [K]": "Process temperature",
  "Rotational speed [rpm]": "Rotational speed",
  "Torque [Nm]": "Torque",
  "Tool wear [min]": "Tool wear",
  equipment_id: "Equipment record",
  equipment_name: "Equipment name",
  equipment_location: "Equipment location",
};

function validationErrorMessage(detail: unknown): string {
  const fallback = "The API rejected the observation. Review the sensor values and equipment association.";
  if (!Array.isArray(detail)) return fallback;

  const issues = detail.slice(0, 5).flatMap((item): string[] => {
    if (!isObject(item) || !Array.isArray(item.loc) || typeof item.msg !== "string") return [];
    const field = item.loc.find((part): part is string =>
      typeof part === "string" && Object.hasOwn(validationFieldLabels, part),
    );
    const label = field ? validationFieldLabels[field] : "Request";
    const message = item.msg
      .replace(/[\u0000-\u001F\u007F-\u009F]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 180);
    return message ? [`${label}: ${message}`] : [];
  });

  return issues.length > 0 ? `Input validation failed — ${issues.join("; ")}` : fallback;
}
