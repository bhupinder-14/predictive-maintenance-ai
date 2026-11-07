import axios from "axios";
import { apiClient } from "./client";

export interface FeatureDriftResult {
  feature_name: string;
  method: "kolmogorov_smirnov_two_sample" | "total_variation_distance";
  statistic: number | null;
  p_value: number | null;
  threshold: number;
  threshold_kind: "p_value_significance_level" | "distance_threshold";
  drift_detected: boolean | null;
  reference_sample_size: number;
  current_sample_size: number;
}

export interface LatestDriftReport {
  reference_version: string;
  generated_at: string;
  reference_sample_size: number;
  current_sample_size: number;
  minimum_sample_size: number;
  overall_status: "drift_detected" | "no_drift_detected" | "insufficient_data";
  features: FeatureDriftResult[];
  interpretation: string;
  report_id: number;
  created_at: string;
  window_start: string;
  window_end: string;
  batch_description: string;
  methodology: Record<string, unknown>;
  report_metadata: Record<string, unknown>;
  model_version: string;
}

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isUnitInterval(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

const monitoredFeatures = new Map<string, FeatureDriftResult["method"]>([
  ["Air temperature [K]", "kolmogorov_smirnov_two_sample"],
  ["Process temperature [K]", "kolmogorov_smirnov_two_sample"],
  ["Rotational speed [rpm]", "kolmogorov_smirnov_two_sample"],
  ["Torque [Nm]", "kolmogorov_smirnov_two_sample"],
  ["Tool wear [min]", "kolmogorov_smirnov_two_sample"],
  ["Type", "total_variation_distance"],
]);

function isSampleSize(value: unknown): value is number {
  return Number.isSafeInteger(value) && typeof value === "number" && value >= 0;
}

function isFeature(value: unknown, report: JsonObject): value is FeatureDriftResult {
  if (!isObject(value)) return false;
  if (typeof value.feature_name !== "string" || monitoredFeatures.get(value.feature_name) !== value.method ||
      !isSampleSize(value.reference_sample_size) || !isSampleSize(value.current_sample_size) ||
      value.reference_sample_size !== report.reference_sample_size || value.current_sample_size !== report.current_sample_size ||
      typeof value.threshold !== "number" || !Number.isFinite(value.threshold) ||
      typeof value.drift_detected !== "boolean" && value.drift_detected !== null) return false;

  const insufficient = report.overall_status === "insufficient_data";
  if (insufficient) {
    if (value.drift_detected !== null || value.statistic !== null || value.p_value !== null) return false;
  } else if (typeof value.drift_detected !== "boolean") {
    return false;
  }

  if (value.method === "kolmogorov_smirnov_two_sample") {
    if (value.threshold_kind !== "p_value_significance_level" || value.threshold <= 0 || value.threshold >= 1) return false;
    if (!insufficient && (!isUnitInterval(value.statistic) || !isUnitInterval(value.p_value))) return false;
    if (!insufficient && value.drift_detected !== (Number(value.p_value) < value.threshold)) return false;
  } else {
    if (value.threshold_kind !== "distance_threshold" || !isUnitInterval(value.threshold) || value.p_value !== null) return false;
    if (!insufficient && !isUnitInterval(value.statistic)) return false;
    if (!insufficient && value.drift_detected !== (Number(value.statistic) >= value.threshold)) return false;
  }
  return true;
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

export function isLatestDriftReport(value: unknown): value is LatestDriftReport {
  if (!isObject(value)) return false;
  if (typeof value.reference_version !== "string" || value.reference_version.length === 0 || !isTimestamp(value.generated_at) ||
      !isSampleSize(value.reference_sample_size) || value.reference_sample_size < 1 ||
      !isSampleSize(value.current_sample_size) || value.current_sample_size < 1 ||
      !isSampleSize(value.minimum_sample_size) || value.minimum_sample_size < 2 ||
      (value.overall_status !== "drift_detected" && value.overall_status !== "no_drift_detected" && value.overall_status !== "insufficient_data") ||
      !Array.isArray(value.features) || value.features.length !== monitoredFeatures.size || typeof value.interpretation !== "string" ||
      !Number.isSafeInteger(value.report_id) || Number(value.report_id) < 1 || !isTimestamp(value.created_at) ||
      !isTimestamp(value.window_start) || !isTimestamp(value.window_end) || Date.parse(value.window_start) > Date.parse(value.window_end) ||
      typeof value.batch_description !== "string" || value.batch_description.length === 0 ||
      !isObject(value.methodology) || !isObject(value.report_metadata) ||
      typeof value.model_version !== "string" || value.model_version.length === 0) return false;

  const insufficient = value.current_sample_size < value.minimum_sample_size;
  if ((value.overall_status === "insufficient_data") !== insufficient) return false;
  const names = new Set<string>();
  const featureResults: FeatureDriftResult[] = [];
  for (const feature of value.features) {
    if (!isFeature(feature, value) || names.has(feature.feature_name)) return false;
    names.add(feature.feature_name);
    featureResults.push(feature);
  }
  if (names.size !== monitoredFeatures.size || [...monitoredFeatures.keys()].some((name) => !names.has(name))) return false;

  if (!insufficient) {
    const anyDetected = featureResults.some((feature) => feature.drift_detected === true);
    if ((value.overall_status === "drift_detected") !== anyDetected) return false;
  }
  const metadata = value.report_metadata;
  if (metadata.overall_status !== undefined && metadata.overall_status !== value.overall_status) return false;
  if (metadata.reference_sample_size !== undefined && metadata.reference_sample_size !== value.reference_sample_size) return false;
  if (metadata.current_sample_size !== undefined && metadata.current_sample_size !== value.current_sample_size) return false;
  if (metadata.minimum_sample_size !== undefined && metadata.minimum_sample_size !== value.minimum_sample_size) return false;
  return true;
}

export async function getLatestDriftReport(): Promise<LatestDriftReport | null> {
  try {
    const response = await apiClient.get<unknown>("/monitoring/drift");
    if (!isLatestDriftReport(response.data)) throw new Error("schema");
    return response.data;
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return null;
    throw new Error("Latest drift report could not be loaded.");
  }
}
