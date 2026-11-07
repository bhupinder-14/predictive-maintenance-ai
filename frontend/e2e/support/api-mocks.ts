import type { Page, Route } from "@playwright/test";

const equipment = [
  { id: 7, name: "Press A", equipment_type: "M", location: "Line 2", created_at: "2026-10-31T10:00:00Z" },
  { id: 8, name: "Lathe B", equipment_type: "L", location: null, created_at: "2026-10-30T10:00:00Z" },
];

const predictionId = "8c4e84b9-27c1-4f3e-bcc7-226cb39cf8de";
const failurePredictionId = "c8c38ad5-d291-4d8c-a707-b89a37bfecf8";

export const anomalyResponse = {
  prediction_id: predictionId,
  equipment_id: 7,
  reading_id: 41,
  anomaly_score: -0.42,
  classification: "anomaly",
  model_version: "anomaly_v1",
  prediction_timestamp: "2026-10-31T10:05:01Z",
  inference_latency_ms: 2.1,
  explanation: { method: "isolation_forest_feature_deviation", anomaly_score: -0.42, top_suspicious_features: [] },
};

export const failureResponse = {
  prediction_id: failurePredictionId,
  equipment_id: 7,
  reading_id: 42,
  predicted_class: 1,
  failure_probability: 0.73,
  model_version: "failure_v1",
  prediction_timestamp: "2026-10-31T10:06:01Z",
  inference_latency_ms: 3.2,
};

const duration = { total: 0, average: 0, max: 0 };
const requestMetrics = { total: 0, successful: 0, failed: 0, status_codes: {}, by_endpoint: {}, duration_ms: duration };
const predictionMetrics = {
  anomaly: { total: 0, normal: 0, anomaly: 0, by_model_version: {} },
  failure: { total: 0, predicted_class_0: 0, predicted_class_1: 0, by_model_version: {} },
  errors: { total: 0, by_model: {} },
};

export const metricsResponse = {
  requests: requestMetrics,
  predictions: predictionMetrics,
  runtime: { uptime_seconds: 25, metrics_storage: "in_memory_process_local" },
  availability: {
    models: {
      anomaly: { available: true, status: "available", model_version: "anomaly_v1" },
      failure: { available: true, status: "available", model_version: "failure_v1" },
    },
    database_available: true,
  },
  rolling_window: { window_seconds: 300, requests: requestMetrics, predictions: predictionMetrics },
};

const featureNames = ["Air temperature [K]", "Process temperature [K]", "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]"];
export const driftResponse = {
  reference_version: "drift_reference_v1",
  generated_at: "2026-10-31T10:10:00Z",
  reference_sample_size: 7000,
  current_sample_size: 20,
  minimum_sample_size: 20,
  overall_status: "drift_detected",
  features: [
    ...featureNames.map((feature_name) => ({
      feature_name, method: "kolmogorov_smirnov_two_sample", statistic: 0.2, p_value: 0.03,
      threshold: 0.05, threshold_kind: "p_value_significance_level", drift_detected: true,
      reference_sample_size: 7000, current_sample_size: 20,
    })),
    { feature_name: "Type", method: "total_variation_distance", statistic: 0.2, p_value: null,
      threshold: 0.1, threshold_kind: "distance_threshold", drift_detected: true,
      reference_sample_size: 7000, current_sample_size: 20 },
  ],
  interpretation: "Drift indicates an input distribution change.",
  report_id: 3,
  created_at: "2026-10-31T10:10:00Z",
  window_start: "2026-10-31T10:10:00Z",
  window_end: "2026-10-31T10:10:00Z",
  batch_description: "Validated batch; no chronological sequence.",
  methodology: { methods: ["kolmogorov_smirnov_two_sample"] },
  report_metadata: { model_versions: { anomaly: "anomaly_v1" } },
  model_version: "anomaly=anomaly_v1;failure=failure_v1",
};

export function sensorReading(id: number, equipmentId: number, timestamp: string) {
  return {
    id, equipment_id: equipmentId, timestamp, Type: "M",
    "Air temperature [K]": 300.234,
    "Process temperature [K]": 310.125,
    "Rotational speed [rpm]": 1450,
    "Torque [Nm]": 38.625,
    "Tool wear [min]": 80,
    source: "api",
  };
}

export function predictionSummary(id: string, modelVersion: string, kind: "anomaly" | "failure", createdAt: string) {
  return kind === "anomaly"
    ? { id, model_version: modelVersion, anomaly_score: -0.42, is_anomaly: true, failure_probability: null, latency_ms: 2.1, created_at: createdAt }
    : { id, model_version: modelVersion, anomaly_score: null, is_anomaly: null, failure_probability: 0.73, latency_ms: 3.2, created_at: createdAt };
}

export function historyEntry(readingId: number, equipmentId: number, withPredictions = false) {
  return {
    reading: sensorReading(readingId, equipmentId, `2026-10-31T10:${String(readingId % 60).padStart(2, "0")}:00Z`),
    predictions: withPredictions
      ? [predictionSummary(predictionId, "anomaly_v1", "anomaly", "2026-10-31T10:05:01Z"), predictionSummary(failurePredictionId, "failure_v1", "failure", "2026-10-31T10:06:01Z")]
      : [],
  };
}

export type MockReply = { status: number; body: unknown };
export interface ApiMockOptions {
  equipmentPage?: (offset: number, call: number) => MockReply | unknown[];
  historyPage?: (equipmentId: number, offset: number, call: number) => MockReply | unknown;
  drift?: (call: number) => MockReply;
  metrics?: MockReply | ((call: number) => MockReply);
  readiness?: MockReply;
  anomaly?: (call: number, body: unknown) => MockReply | "abort" | "timeout";
  failure?: (call: number, body: unknown) => MockReply;
  savedPrediction?: MockReply;
}

export interface ApiMockCounters {
  equipment: number;
  history: number;
  drift: number;
  metrics: number;
  anomaly: number;
  failure: number;
  predictionRequests: Array<{ path: string; method: string; body: unknown }>;
}

function isMockReply(value: unknown): value is MockReply {
  return typeof value === "object" && value !== null && "status" in value && "body" in value;
}

async function fulfill(route: Route, status: number, body: unknown) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export async function installApiMocks(page: Page, options: ApiMockOptions = {}): Promise<ApiMockCounters> {
  const counts: ApiMockCounters = { equipment: 0, history: 0, drift: 0, metrics: 0, anomaly: 0, failure: 0, predictionRequests: [] };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/")) return route.continue();
    const path = url.pathname.replace(/^\/api/, "");
    const method = request.method();

    if (path.startsWith("/predict/")) {
      counts.predictionRequests.push({
        path,
        method,
        body: method === "POST" ? request.postDataJSON() : null,
      });
    }

    if (path === "/health" && method === "GET") return fulfill(route, 200, { status: "ok" });
    if (path === "/ready" && method === "GET") return fulfill(route, options.readiness?.status ?? 200, options.readiness?.body ?? { status: "ready", models: { anomaly: true, failure: true }, database: true });
    if ((path === "/monitoring/metrics" || path === "/metrics/summary") && method === "GET") {
      counts.metrics += 1;
      const configured = typeof options.metrics === "function" ? options.metrics(counts.metrics) : options.metrics;
      const response = configured ?? { status: 200, body: metricsResponse };
      return fulfill(route, response.status, response.body);
    }
    if (path === "/monitoring/drift" && method === "GET") {
      counts.drift += 1;
      const response = options.drift?.(counts.drift) ?? { status: 404, body: { detail: "No drift report is available" } };
      return fulfill(route, response.status, response.body);
    }
    if (path === "/equipment" && method === "GET") {
      counts.equipment += 1;
      const offset = Number(url.searchParams.get("offset") ?? "0");
      const response = options.equipmentPage?.(offset, counts.equipment) ?? equipment;
      return Array.isArray(response) ? fulfill(route, 200, response) : fulfill(route, response.status, response.body);
    }
    const historyMatch = path.match(/^\/equipment\/(\d+)\/history$/);
    if (historyMatch && method === "GET") {
      counts.history += 1;
      const equipmentId = Number(historyMatch[1]);
      const offset = Number(url.searchParams.get("offset") ?? "0");
      const response = options.historyPage?.(equipmentId, offset, counts.history) ?? {
        equipment: equipment.find((item) => item.id === equipmentId),
        items: equipmentId === 7
          ? [
              { ...historyEntry(41, 7), predictions: [predictionSummary(predictionId, "anomaly_v1", "anomaly", "2026-10-31T10:05:01Z")] },
              { ...historyEntry(42, 7), predictions: [predictionSummary(failurePredictionId, "failure_v1", "failure", "2026-10-31T10:06:01Z")] },
            ]
          : [historyEntry(81, equipmentId)],
      };
      return isMockReply(response) ? fulfill(route, response.status, response.body) : fulfill(route, 200, response);
    }
    const predictionMatch = path.match(/^\/predictions\/(.+)$/);
    if (predictionMatch && method === "GET") {
      const isFailure = decodeURIComponent(predictionMatch[1]) === failurePredictionId;
      const base = isFailure ? failureResponse : anomalyResponse;
      const body = {
        id: base.prediction_id, equipment_id: base.equipment_id, reading_id: base.reading_id,
        model_version: base.model_version,
        anomaly_score: "anomaly_score" in base ? base.anomaly_score : null,
        is_anomaly: "classification" in base ? base.classification === "anomaly" : null,
        failure_probability: "failure_probability" in base ? base.failure_probability : null,
        latency_ms: base.inference_latency_ms,
        created_at: base.prediction_timestamp,
      };
      const reply = options.savedPrediction ?? { status: 200, body };
      return fulfill(route, reply.status, reply.body);
    }
    if (path === "/predict/anomaly" && method === "POST") {
      counts.anomaly += 1;
      const reply = options.anomaly?.(counts.anomaly, request.postDataJSON()) ?? { status: 200, body: anomalyResponse };
      if (reply === "abort") return route.abort("failed");
      if (reply === "timeout") return route.abort("timedout");
      return fulfill(route, reply.status, reply.body);
    }
    if (path === "/predict/failure" && method === "POST") {
      counts.failure += 1;
      const reply = options.failure?.(counts.failure, request.postDataJSON()) ?? { status: 200, body: failureResponse };
      return fulfill(route, reply.status, reply.body);
    }
    return fulfill(route, 404, { detail: "Not found" });
  });
  return counts;
}
