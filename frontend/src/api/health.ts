import axios from "axios";
import { apiClient } from "./client";
import type { HealthResponse, ProbeFailure, ReadinessResponse } from "./types";

export type ProbeResult<T> = { kind: "success"; statusCode: number; data: T } | ProbeFailure;

export interface BackendStatus {
  health: ProbeResult<HealthResponse>;
  readiness: ProbeResult<ReadinessResponse>;
}

function isHealthResponse(value: unknown): value is HealthResponse {
  return typeof value === "object" && value !== null && "status" in value && value.status === "ok";
}

function isReadinessResponse(value: unknown): value is ReadinessResponse {
  if (typeof value !== "object" || value === null || !("status" in value) || !("models" in value) || !("database" in value)) {
    return false;
  }
  const candidate = value as Partial<ReadinessResponse>;
  return (
    (candidate.status === "ready" || candidate.status === "not_ready") &&
    typeof candidate.database === "boolean" &&
    typeof candidate.models === "object" && candidate.models !== null &&
    typeof candidate.models.anomaly === "boolean" &&
    typeof candidate.models.failure === "boolean"
  );
}

function failureFrom(error: unknown, endpoint: "health" | "readiness"): ProbeFailure {
  if (axios.isAxiosError(error)) {
    if (error.response) {
      return {
        kind: "error",
        reason: "http",
        statusCode: error.response.status,
        message: `${endpoint === "health" ? "Health" : "Readiness"} check returned HTTP ${error.response.status}.`,
      };
    }
    const timedOut = error.code === "ECONNABORTED" || error.code === "ETIMEDOUT";
    return {
      kind: "error",
      reason: "network",
      message: timedOut
        ? `${endpoint === "health" ? "Health" : "Readiness"} check timed out.`
        : `${endpoint === "health" ? "Health" : "Readiness"} check could not reach the API.`,
    };
  }
  return {
    kind: "error",
    reason: "network",
    message: `${endpoint === "health" ? "Health" : "Readiness"} check could not reach the API.`,
  };
}

async function probeHealth(): Promise<ProbeResult<HealthResponse>> {
  try {
    const response = await apiClient.get<unknown>("/health", { validateStatus: () => true });
    if (response.status !== 200) {
      return {
        kind: "error",
        reason: "http",
        statusCode: response.status,
        message: `Health check returned HTTP ${response.status}.`,
      };
    }
    if (!isHealthResponse(response.data)) {
      return { kind: "error", reason: "malformed", statusCode: response.status, message: "Health check returned an invalid response." };
    }
    return { kind: "success", statusCode: response.status, data: response.data };
  } catch (error: unknown) {
    return failureFrom(error, "health");
  }
}

async function probeReadiness(): Promise<ProbeResult<ReadinessResponse>> {
  try {
    const response = await apiClient.get<unknown>("/ready", { validateStatus: () => true });
    if (response.status !== 200 && response.status !== 503) {
      return {
        kind: "error",
        reason: "http",
        statusCode: response.status,
        message: `Readiness check returned unexpected HTTP ${response.status}.`,
      };
    }
    if (!isReadinessResponse(response.data)) {
      return { kind: "error", reason: "malformed", statusCode: response.status, message: "Readiness check returned an invalid response." };
    }
    const isConsistentReady = response.status === 200 && response.data.status === "ready" &&
      response.data.database && response.data.models.anomaly && response.data.models.failure;
    const hasUnavailableDependency = !response.data.database ||
      !response.data.models.anomaly || !response.data.models.failure;
    const isConsistentNotReady = response.status === 503 &&
      response.data.status === "not_ready" && hasUnavailableDependency;
    if (!isConsistentReady && !isConsistentNotReady) {
      return { kind: "error", reason: "malformed", statusCode: response.status, message: "Readiness response did not match its HTTP status." };
    }
    return { kind: "success", statusCode: response.status, data: response.data };
  } catch (error: unknown) {
    return failureFrom(error, "readiness");
  }
}

export async function getBackendStatus(): Promise<BackendStatus> {
  const [health, readiness] = await Promise.all([probeHealth(), probeReadiness()]);
  return { health, readiness };
}
