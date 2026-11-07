import { apiClient } from "./client";

export interface DurationSummary {
  total: number;
  average: number;
  max: number;
}

export interface EndpointRequestMetrics {
  requests: number;
  successful: number;
  failed: number;
  status_codes: Record<string, number>;
  duration_ms: DurationSummary;
}

export interface RequestMetrics {
  total: number;
  successful: number;
  failed: number;
  status_codes: Record<string, number>;
  by_endpoint: Record<string, EndpointRequestMetrics>;
  duration_ms: DurationSummary;
}

export interface AnomalyVersionCounts {
  total: number;
  normal: number;
  anomaly: number;
}

export interface FailureVersionCounts {
  total: number;
  predicted_class_0: number;
  predicted_class_1: number;
}

export interface AnomalyMetrics {
  total: number;
  normal: number;
  anomaly: number;
  by_model_version: Record<string, AnomalyVersionCounts>;
}

export interface FailureMetrics {
  total: number;
  predicted_class_0: number;
  predicted_class_1: number;
  by_model_version: Record<string, FailureVersionCounts>;
}

export interface PredictionMetrics {
  anomaly: AnomalyMetrics;
  failure: FailureMetrics;
  errors: { total: number; by_model: Record<string, number> };
}

export interface ModelAvailability {
  available: boolean;
  status: string;
  model_version: string | null;
}

export interface OperationalMetrics {
  requests: RequestMetrics;
  predictions: PredictionMetrics;
  runtime: { uptime_seconds: number; metrics_storage: "in_memory_process_local" };
  availability: {
    models: Record<string, ModelAvailability>;
    database_available: boolean | null;
  };
  rolling_window: {
    window_seconds: number;
    requests: RequestMetrics;
    predictions: PredictionMetrics;
  };
}

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isMeasure(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isCountMap(value: unknown): value is Record<string, number> {
  return isObject(value) && Object.values(value).every(isCount);
}

function sumCounts(values: Record<string, number>): number {
  return Object.values(values).reduce((sum, value) => sum + value, 0);
}

function isDuration(value: unknown, count: number): value is DurationSummary {
  if (!isObject(value) || !isMeasure(value.total) || !isMeasure(value.average) || !isMeasure(value.max)) return false;
  if (count === 0) return value.total === 0 && value.average === 0 && value.max === 0;
  // Backend fields are rounded independently to three decimal places.
  return value.average <= value.max + 0.002 && value.max <= value.total + 0.002;
}

function isStatusCounts(value: unknown, total: number, successful: number, failed: number): value is Record<string, number> {
  if (!isCountMap(value)) return false;
  let successfulByStatus = 0;
  let failedByStatus = 0;
  for (const [status, count] of Object.entries(value)) {
    if (!/^\d{3}$/.test(status)) return false;
    const code = Number(status);
    if (code < 100 || code > 599) return false;
    if (code < 400) successfulByStatus += count;
    else failedByStatus += count;
  }
  return sumCounts(value) === total && successfulByStatus === successful && failedByStatus === failed;
}

function isEndpointMetrics(value: unknown): value is EndpointRequestMetrics {
  if (!isObject(value) || !isCount(value.requests) || !isCount(value.successful) || !isCount(value.failed)) return false;
  return value.successful + value.failed === value.requests &&
    isStatusCounts(value.status_codes, value.requests, value.successful, value.failed) &&
    isDuration(value.duration_ms, value.requests);
}

function isRequestMetrics(value: unknown): value is RequestMetrics {
  if (!isObject(value) || !isCount(value.total) || !isCount(value.successful) || !isCount(value.failed) ||
      value.successful + value.failed !== value.total ||
      !isDuration(value.duration_ms, value.total) || !isObject(value.by_endpoint)) return false;
  const statusCodes = value.status_codes;
  if (!isStatusCounts(statusCodes, value.total, value.successful, value.failed)) return false;

  const endpoints: EndpointRequestMetrics[] = [];
  for (const endpoint of Object.values(value.by_endpoint)) {
    if (!isEndpointMetrics(endpoint)) return false;
    endpoints.push(endpoint);
  }
  if (endpoints.reduce((sum, endpoint) => sum + endpoint.requests, 0) !== value.total ||
      endpoints.reduce((sum, endpoint) => sum + endpoint.successful, 0) !== value.successful ||
      endpoints.reduce((sum, endpoint) => sum + endpoint.failed, 0) !== value.failed) return false;

  const endpointStatuses = new Map<string, number>();
  for (const endpoint of endpoints) {
    for (const [status, count] of Object.entries(endpoint.status_codes)) {
      endpointStatuses.set(status, (endpointStatuses.get(status) ?? 0) + count);
    }
  }
  return [...new Set([...Object.keys(statusCodes), ...endpointStatuses.keys()])]
    .every((status) => statusCodes[status] === (endpointStatuses.get(status) ?? 0));
}

function isVersionCounts(value: unknown, fields: readonly string[]): boolean {
  if (!isObject(value) || !isCount(value.total) || !fields.every((field) => isCount(value[field]))) return false;
  return fields.reduce((sum, field) => sum + Number(value[field]), 0) === value.total;
}

function isVersionMap(value: unknown, fields: readonly string[], total: number, outcomes: Record<string, number>): boolean {
  if (!isObject(value)) return false;
  const versions: JsonObject[] = [];
  for (const entry of Object.values(value)) {
    if (!isVersionCounts(entry, fields) || !isObject(entry)) return false;
    versions.push(entry);
  }
  return versions.reduce((sum, version) => sum + Number(version.total), 0) === total &&
    fields.every((field) => versions.reduce((sum, version) => sum + Number(version[field]), 0) === outcomes[field]);
}

function isAnomalyMetrics(value: unknown): value is AnomalyMetrics {
  if (!isObject(value) || !isCount(value.total) || !isCount(value.normal) || !isCount(value.anomaly) ||
      value.normal + value.anomaly !== value.total) return false;
  return isVersionMap(value.by_model_version, ["normal", "anomaly"], value.total, {
    normal: value.normal, anomaly: value.anomaly,
  });
}

function isFailureMetrics(value: unknown): value is FailureMetrics {
  if (!isObject(value) || !isCount(value.total) || !isCount(value.predicted_class_0) || !isCount(value.predicted_class_1) ||
      value.predicted_class_0 + value.predicted_class_1 !== value.total) return false;
  return isVersionMap(value.by_model_version, ["predicted_class_0", "predicted_class_1"], value.total, {
    predicted_class_0: value.predicted_class_0, predicted_class_1: value.predicted_class_1,
  });
}

function isPredictionMetrics(value: unknown): value is PredictionMetrics {
  return isObject(value) && isAnomalyMetrics(value.anomaly) && isFailureMetrics(value.failure) &&
    isObject(value.errors) && isCount(value.errors.total) && isCountMap(value.errors.by_model) &&
    sumCounts(value.errors.by_model) === value.errors.total;
}

function predictionErrorsMatchFailedEndpoints(predictions: PredictionMetrics, requests: RequestMetrics): boolean {
  const anomalyFailures = requests.by_endpoint["/predict/anomaly"]?.failed ?? 0;
  const failureFailures = requests.by_endpoint["/predict/failure"]?.failed ?? 0;
  return (predictions.errors.by_model.anomaly ?? 0) === anomalyFailures &&
    (predictions.errors.by_model.failure ?? 0) === failureFailures;
}

function isModelAvailability(value: unknown): value is ModelAvailability {
  return isObject(value) && typeof value.available === "boolean" && typeof value.status === "string" &&
    (typeof value.model_version === "string" || value.model_version === null);
}

export function isOperationalMetrics(value: unknown): value is OperationalMetrics {
  if (!isObject(value) || !isRequestMetrics(value.requests) || !isPredictionMetrics(value.predictions) ||
    !isObject(value.runtime) || !isMeasure(value.runtime.uptime_seconds) ||
    value.runtime.metrics_storage !== "in_memory_process_local" || !isObject(value.availability) ||
    !isObject(value.availability.models) || !isModelAvailability(value.availability.models.anomaly) ||
    !isModelAvailability(value.availability.models.failure) ||
    !(typeof value.availability.database_available === "boolean" || value.availability.database_available === null) ||
    !isObject(value.rolling_window) || !isCount(value.rolling_window.window_seconds) ||
    value.rolling_window.window_seconds < 1 || !isRequestMetrics(value.rolling_window.requests) ||
    !isPredictionMetrics(value.rolling_window.predictions)) {
    return false;
  }
  return predictionErrorsMatchFailedEndpoints(value.predictions, value.requests) &&
    predictionErrorsMatchFailedEndpoints(value.rolling_window.predictions, value.rolling_window.requests) &&
    isRollingRequestSubset(value.rolling_window.requests, value.requests) &&
    isRollingPredictionSubset(value.rolling_window.predictions, value.predictions);
}

function isRollingRequestSubset(rolling: RequestMetrics, cumulative: RequestMetrics): boolean {
  if (rolling.total > cumulative.total || rolling.successful > cumulative.successful || rolling.failed > cumulative.failed) return false;
  if (Object.entries(rolling.status_codes).some(([status, count]) => count > (cumulative.status_codes[status] ?? 0))) return false;
  return Object.entries(rolling.by_endpoint).every(([endpoint, values]) => {
    const total = cumulative.by_endpoint[endpoint];
    return total !== undefined && values.requests <= total.requests && values.successful <= total.successful &&
      values.failed <= total.failed && Object.entries(values.status_codes).every(([status, count]) => count <= (total.status_codes[status] ?? 0));
  });
}

function isRollingPredictionSubset(rolling: PredictionMetrics, cumulative: PredictionMetrics): boolean {
  const rollingAnomaly = rolling.anomaly;
  const totalAnomaly = cumulative.anomaly;
  const rollingFailure = rolling.failure;
  const totalFailure = cumulative.failure;
  if (rollingAnomaly.total > totalAnomaly.total || rollingAnomaly.normal > totalAnomaly.normal || rollingAnomaly.anomaly > totalAnomaly.anomaly ||
      rollingFailure.total > totalFailure.total || rollingFailure.predicted_class_0 > totalFailure.predicted_class_0 ||
      rollingFailure.predicted_class_1 > totalFailure.predicted_class_1 || rolling.errors.total > cumulative.errors.total) return false;
  if (Object.entries(rolling.errors.by_model).some(([model, count]) => count > (cumulative.errors.by_model[model] ?? 0))) return false;
  return isVersionSubset(rollingAnomaly.by_model_version, totalAnomaly.by_model_version, ["normal", "anomaly"]) &&
    isVersionSubset(rollingFailure.by_model_version, totalFailure.by_model_version, ["predicted_class_0", "predicted_class_1"]);
}

function isVersionSubset(
  rolling: Record<string, AnomalyVersionCounts | FailureVersionCounts>,
  cumulative: Record<string, AnomalyVersionCounts | FailureVersionCounts>,
  fields: readonly string[],
): boolean {
  return Object.entries(rolling).every(([version, counts]) => {
    const total = cumulative[version];
    return total !== undefined && counts.total <= total.total && fields.every((field) => {
      const rollingCount = outcomeCount(counts, field);
      const cumulativeCount = outcomeCount(total, field);
      return typeof rollingCount === "number" && typeof cumulativeCount === "number" && rollingCount <= cumulativeCount;
    });
  });
}

function outcomeCount(counts: AnomalyVersionCounts | FailureVersionCounts, field: string): number | undefined {
  if (field === "normal") return "normal" in counts ? counts.normal : undefined;
  if (field === "anomaly") return "anomaly" in counts ? counts.anomaly : undefined;
  if (field === "predicted_class_0") return "predicted_class_0" in counts ? counts.predicted_class_0 : undefined;
  if (field === "predicted_class_1") return "predicted_class_1" in counts ? counts.predicted_class_1 : undefined;
  return undefined;
}

export async function getOperationalMetrics(): Promise<OperationalMetrics> {
  try {
    const response = await apiClient.get<unknown>("/monitoring/metrics");
    if (!isOperationalMetrics(response.data)) throw new Error("schema");
    return response.data;
  } catch {
    throw new Error("Operational metrics could not be loaded.");
  }
}

export function formatDuration(seconds: number): string {
  const totalSeconds = Math.floor(seconds);
  const days = Math.floor(totalSeconds / 86_400);
  const hours = Math.floor((totalSeconds % 86_400) / 3_600);
  const minutes = Math.floor((totalSeconds % 3_600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m ${totalSeconds % 60}s`;
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat().format(value);
}
