import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { formatDuration, getOperationalMetrics, isOperationalMetrics } from "./metrics";

afterEach(() => vi.restoreAllMocks());

const duration = { total: 0, average: 0, max: 0 };
const requests = { total: 0, successful: 0, failed: 0, status_codes: {}, by_endpoint: {}, duration_ms: duration };
const predictions = {
  anomaly: { total: 0, normal: 0, anomaly: 0, by_model_version: {} },
  failure: { total: 0, predicted_class_0: 0, predicted_class_1: 0, by_model_version: {} },
  errors: { total: 0, by_model: {} },
};
const validMetrics = {
  requests,
  predictions,
  runtime: { uptime_seconds: 0, metrics_storage: "in_memory_process_local" },
  availability: { models: {
    anomaly: { available: true, status: "available", model_version: "anomaly_v1" },
    failure: { available: true, status: "available", model_version: "failure_v1" },
  }, database_available: true },
  rolling_window: { window_seconds: 300, requests, predictions },
};

function requestMetrics(total: number, successful: number, failed: number) {
  const statusCodes = total === 0 ? {} : { "200": successful, "503": failed };
  const endpoint = total === 0 ? {} : { "/health": {
    requests: total, successful, failed, status_codes: statusCodes,
    duration_ms: { total, average: 1, max: 1 },
  } };
  return {
    total, successful, failed, status_codes: statusCodes, by_endpoint: endpoint,
    duration_ms: { total, average: total === 0 ? 0 : 1, max: total === 0 ? 0 : 1 },
  };
}

function failedPredictionRequests(anomaly: number, failure: number) {
  const byEndpoint: Record<string, { requests: number; successful: number; failed: number; status_codes: Record<string, number>; duration_ms: { total: number; average: number; max: number } }> = {};
  if (anomaly > 0) byEndpoint["/predict/anomaly"] = {
    requests: anomaly, successful: 0, failed: anomaly, status_codes: { "503": anomaly },
    duration_ms: { total: anomaly, average: 1, max: 1 },
  };
  if (failure > 0) byEndpoint["/predict/failure"] = {
    requests: failure, successful: 0, failed: failure, status_codes: { "503": failure },
    duration_ms: { total: failure, average: 1, max: 1 },
  };
  const total = anomaly + failure;
  return {
    total, successful: 0, failed: total,
    status_codes: total === 0 ? {} : { "503": total },
    by_endpoint: byEndpoint,
    duration_ms: { total, average: total === 0 ? 0 : 1, max: total === 0 ? 0 : 1 },
  };
}

function metricsWithPredictionErrors(anomalyErrors: number, failureErrors: number) {
  const byModel = {
    ...(anomalyErrors > 0 ? { anomaly: anomalyErrors } : {}),
    ...(failureErrors > 0 ? { failure: failureErrors } : {}),
  };
  const withErrors = {
    ...predictions,
    errors: { total: anomalyErrors + failureErrors, by_model: byModel },
  };
  const requestsWithErrors = failedPredictionRequests(anomalyErrors, failureErrors);
  return {
    ...validMetrics,
    requests: requestsWithErrors,
    predictions: withErrors,
    rolling_window: {
      window_seconds: 300,
      requests: requestsWithErrors,
      predictions: withErrors,
    },
  };
}

describe("operational metrics service", () => {
  it("accepts the cumulative and rolling backend contract including zero counts", () => {
    expect(isOperationalMetrics(validMetrics)).toBe(true);
    expect(isOperationalMetrics({ ...validMetrics, requests: requestMetrics(8, 6, 2) })).toBe(true);
  });

  it("rejects missing availability, invalid counters, and malformed durations", () => {
    expect(isOperationalMetrics({ ...validMetrics, availability: { models: {}, database_available: true } })).toBe(false);
    expect(isOperationalMetrics({ ...validMetrics, requests: { ...requests, failed: -1 } })).toBe(false);
    expect(isOperationalMetrics({ ...validMetrics, requests: { ...requests, total: 1.5 } })).toBe(false);
    expect(isOperationalMetrics({ ...validMetrics, rolling_window: { ...validMetrics.rolling_window, requests: { ...requests, duration_ms: { total: 0, average: "unknown", max: 0 } } } })).toBe(false);
  });

  it("rejects request totals and outcomes that contradict status and endpoint counts", () => {
    const valid = { ...validMetrics, requests: requestMetrics(4, 3, 1) };
    expect(isOperationalMetrics(valid)).toBe(true);
    expect(isOperationalMetrics({ ...validMetrics, requests: { ...requestMetrics(4, 3, 1), total: 2 } })).toBe(false);
    expect(isOperationalMetrics({ ...validMetrics, requests: { ...requestMetrics(4, 3, 1), failed: 5 } })).toBe(false);
  });

  it("rejects prediction totals inconsistent with outcomes or model-version aggregates", () => {
    expect(isOperationalMetrics({
      ...validMetrics,
      predictions: { ...predictions, anomaly: { total: 0, normal: 0, anomaly: 1, by_model_version: {} } },
    })).toBe(false);
    expect(isOperationalMetrics({
      ...validMetrics,
      predictions: { ...predictions, failure: { total: 0, predicted_class_0: 0, predicted_class_1: 1, by_model_version: {} } },
    })).toBe(false);
    expect(isOperationalMetrics({
      ...validMetrics,
      predictions: { ...predictions, anomaly: { total: 2, normal: 1, anomaly: 1, by_model_version: { v1: { total: 1, normal: 1, anomaly: 0 } } } },
    })).toBe(false);
  });

  it("accepts cumulative anomaly prediction errors reconciled to failed anomaly requests", () => {
    expect(isOperationalMetrics(metricsWithPredictionErrors(2, 0))).toBe(true);
  });

  it("accepts cumulative failure prediction errors reconciled to failed failure requests", () => {
    expect(isOperationalMetrics(metricsWithPredictionErrors(0, 3))).toBe(true);
  });

  it("rejects cumulative prediction-error counts that differ from their matching endpoint failures", () => {
    const anomalyMismatch = metricsWithPredictionErrors(0, 0);
    anomalyMismatch.requests = failedPredictionRequests(1, 0);
    expect(isOperationalMetrics(anomalyMismatch)).toBe(false);

    const failureMismatch = metricsWithPredictionErrors(0, 0);
    failureMismatch.requests = failedPredictionRequests(0, 1);
    expect(isOperationalMetrics(failureMismatch)).toBe(false);
  });

  it("accepts rolling prediction-error counts reconciled to rolling failed endpoint requests", () => {
    expect(isOperationalMetrics(metricsWithPredictionErrors(2, 1))).toBe(true);
  });

  it("rejects rolling anomaly or failure prediction-error mismatches", () => {
    const anomalyMismatch = metricsWithPredictionErrors(1, 0);
    anomalyMismatch.rolling_window.predictions = predictions;
    expect(isOperationalMetrics(anomalyMismatch)).toBe(false);

    const failureMismatch = metricsWithPredictionErrors(0, 1);
    failureMismatch.rolling_window.predictions = predictions;
    expect(isOperationalMetrics(failureMismatch)).toBe(false);
  });

  it("accepts empty endpoint and error maps at the zero-count boundary", () => {
    expect(isOperationalMetrics(validMetrics)).toBe(true);
    expect(validMetrics.requests.by_endpoint).toEqual({});
    expect(validMetrics.predictions.errors.by_model).toEqual({});
  });

  it("rejects rolling values larger than cumulative totals but accepts unavailable models and zeros", () => {
    expect(isOperationalMetrics({
      ...validMetrics,
      availability: { models: {
        anomaly: { available: false, status: "missing_artifacts", model_version: null },
        failure: { available: true, status: "available", model_version: "failure_v1" },
      }, database_available: true },
    })).toBe(true);
    expect(isOperationalMetrics({
      ...validMetrics,
      rolling_window: { ...validMetrics.rolling_window, predictions: {
        ...predictions, anomaly: { total: 1, normal: 1, anomaly: 0, by_model_version: { v1: { total: 1, normal: 1, anomaly: 0 } } },
      } },
    })).toBe(false);
  });

  it("calls the actual metrics endpoint and reports an invalid response safely", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: validMetrics } as never);
    await expect(getOperationalMetrics()).resolves.toEqual(validMetrics);
    expect(get).toHaveBeenCalledWith("/monitoring/metrics");

    vi.restoreAllMocks();
    vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: { requests: {} } } as never);
    await expect(getOperationalMetrics()).rejects.toThrow("Operational metrics could not be loaded.");
  });

  it("formats process uptime without inventing a value", () => {
    expect(formatDuration(0)).toBe("0m 0s");
    expect(formatDuration(3661)).toBe("1h 1m");
    expect(formatDuration(90_061)).toBe("1d 1h");
  });
});
