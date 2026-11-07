import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SystemHealthPage } from "./SystemHealthPage";

const { mockBackendStatus, mockOperationalMetrics } = vi.hoisted(() => ({
  mockBackendStatus: vi.fn(),
  mockOperationalMetrics: vi.fn(),
}));
vi.mock("@/hooks/useBackendStatus", () => ({ useBackendStatus: () => mockBackendStatus() }));
vi.mock("@/hooks/useOperationalMetrics", () => ({ useOperationalMetrics: () => mockOperationalMetrics() }));

const emptyRequest = { total: 0, successful: 0, failed: 0, status_codes: {}, by_endpoint: {}, duration_ms: { total: 0, average: 0, max: 0 } };
const emptyPredictions = {
  anomaly: { total: 0, normal: 0, anomaly: 0, by_model_version: {} },
  failure: { total: 0, predicted_class_0: 0, predicted_class_1: 0, by_model_version: {} },
  errors: { total: 0, by_model: {} },
};
const zeroMetrics = {
  requests: emptyRequest,
  predictions: emptyPredictions,
  runtime: { uptime_seconds: 0, metrics_storage: "in_memory_process_local" as const },
  availability: { models: {
    anomaly: { available: true, status: "available", model_version: "anomaly_v1" },
    failure: { available: true, status: "available", model_version: "failure_v1" },
  }, database_available: true },
  rolling_window: { window_seconds: 300, requests: emptyRequest, predictions: emptyPredictions },
};

function query(data: typeof zeroMetrics | undefined, overrides: Record<string, unknown> = {}) {
  return {
    data,
    isPending: false,
    isError: false,
    isFetching: false,
    dataUpdatedAt: 1_798_000_000_000,
    refetch: vi.fn(),
    ...overrides,
  };
}

function renderPage() {
  return render(<SystemHealthPage />);
}

beforeEach(() => {
  mockBackendStatus.mockReset().mockReturnValue({ kind: "ready", health: { status: "ok" }, readiness: { status: "ready", models: { anomaly: true, failure: true }, database: true } });
  mockOperationalMetrics.mockReset().mockReturnValue(query(zeroMetrics));
});
afterEach(() => cleanup());

describe("SystemHealthPage", () => {
  it("shows healthy liveness/readiness and actual cumulative and rolling metrics", () => {
    const healthyMetrics = {
      ...zeroMetrics,
      requests: { ...emptyRequest, total: 8, successful: 8, status_codes: { "200": 8 }, by_endpoint: { "/health": { requests: 8, successful: 8, failed: 0, status_codes: { "200": 8 }, duration_ms: { total: 8, average: 1, max: 1 } } }, duration_ms: { total: 8, average: 1, max: 1 } },
      predictions: { ...emptyPredictions, anomaly: { total: 2, normal: 1, anomaly: 1, by_model_version: { anomaly_v1: { total: 2, normal: 1, anomaly: 1 } } } },
      runtime: { uptime_seconds: 3661, metrics_storage: "in_memory_process_local" as const },
      rolling_window: { ...zeroMetrics.rolling_window, predictions: { ...emptyPredictions, anomaly: { total: 1, normal: 0, anomaly: 1, by_model_version: { anomaly_v1: { total: 1, normal: 0, anomaly: 1 } } } } },
    };
    mockOperationalMetrics.mockReturnValue(query(healthyMetrics));
    renderPage();
    expect(screen.getAllByText("Reachable")).toHaveLength(2);
    expect(screen.getAllByText("Ready")).toHaveLength(2);
    expect(screen.getByText("8", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("1h 1m")).toBeInTheDocument();
    expect(screen.getByText("Rolling window · 5 min")).toBeInTheDocument();
    expect(screen.getByText(/reset when it restarts/)).toBeInTheDocument();
  });

  it("distinguishes degraded readiness from a failed readiness probe", () => {
    mockBackendStatus.mockReturnValue({ kind: "not-ready", health: { status: "ok" }, readiness: { status: "not_ready", models: { anomaly: false, failure: true }, database: true } });
    const { rerender } = renderPage();
    expect(screen.getAllByText("Reachable, not ready")).toHaveLength(2);
    expect(screen.getByText("ANOMALY MODEL").parentElement).toHaveTextContent("Unavailable");
    expect(screen.getByText("FAILURE MODEL").parentElement).toHaveTextContent("Available");

    mockBackendStatus.mockReturnValue({ kind: "readiness-error", health: { status: "ok" }, error: { kind: "error", reason: "http", statusCode: 500, message: "Readiness check returned unexpected HTTP 500." } });
    rerender(<SystemHealthPage />);
    expect(screen.getAllByText("Probe failed")).toHaveLength(2);
    expect(screen.getByText("Readiness could not be confirmed")).toBeInTheDocument();
    expect(screen.queryByText("Unknown")).not.toBeInTheDocument();
  });

  it("shows database unavailability from the readiness response", () => {
    mockBackendStatus.mockReturnValue({ kind: "not-ready", health: { status: "ok" }, readiness: { status: "not_ready", models: { anomaly: true, failure: true }, database: false } });
    renderPage();
    expect(screen.getAllByText("Reachable, not ready")).toHaveLength(2);
    expect(screen.getByText("DATABASE").parentElement).toHaveTextContent("Unavailable");
  });

  it("keeps metrics available independently when backend liveness is unreachable", () => {
    mockBackendStatus.mockReturnValue({ kind: "unreachable", error: { kind: "error", reason: "network", message: "Health check timed out." } });
    renderPage();
    expect(screen.getAllByText("Unreachable")).toHaveLength(2);
    expect(screen.getByText("Health check timed out.")).toBeInTheDocument();
    expect(screen.getByText("Requests recorded")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown")).toHaveLength(2);
  });

  it("keeps health visible when metrics fail and offers retry", () => {
    const refetch = vi.fn();
    mockOperationalMetrics.mockReturnValue(query(undefined, { isError: true, refetch }));
    renderPage();
    expect(screen.getAllByText("Reachable")).toHaveLength(2);
    expect(screen.getByText("Operational metrics unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("labels cached metrics stale after a refresh failure", () => {
    mockOperationalMetrics.mockReturnValue(query(zeroMetrics, { isError: true }));
    renderPage();
    expect(screen.getByText(/Metrics refresh failed\. Showing the last successful snapshot/)).toBeInTheDocument();
    expect(screen.getByText("Requests recorded")).toBeInTheDocument();
  });

  it("renders valid zero counts as zero rather than as missing data", () => {
    renderPage();
    expect(screen.getByLabelText("Requests recorded: 0")).toHaveTextContent("0");
    expect(screen.getByLabelText("Anomaly predictions: 0")).toHaveTextContent("0");
    expect(screen.getByText("Rolling window · 5 min")).toBeInTheDocument();
  });

  it("shows a loading state while the metrics query is pending", () => {
    mockOperationalMetrics.mockReturnValue(query(undefined, { isPending: true }));
    renderPage();
    expect(screen.getByRole("region", { name: "Operational metrics loading" })).toBeInTheDocument();
  });
});
