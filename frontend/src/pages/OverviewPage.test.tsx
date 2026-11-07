import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OverviewPage } from "./OverviewPage";

const { mockGetMetrics, mockGetDrift, mockBackendState } = vi.hoisted(() => ({
  mockGetMetrics: vi.fn(),
  mockGetDrift: vi.fn(),
  mockBackendState: vi.fn(),
}));
vi.mock("@/api/metrics", () => ({
  getOperationalMetrics: () => mockGetMetrics(),
  formatCount: (value: number) => new Intl.NumberFormat().format(value),
  formatDuration: (value: number) => `${Math.floor(value / 60)}m ${Math.floor(value % 60)}s`,
}));
vi.mock("@/api/drift", () => ({
  getLatestDriftReport: () => mockGetDrift(),
}));
vi.mock("@/hooks/useBackendStatus", () => ({ useBackendStatus: () => mockBackendState() }));

const emptyRequests = { total: 0, successful: 0, failed: 0, status_codes: {}, by_endpoint: {}, duration_ms: { total: 0, average: 0, max: 0 } };
const emptyPredictions = {
  anomaly: { total: 0, normal: 0, anomaly: 0, by_model_version: {} },
  failure: { total: 0, predicted_class_0: 0, predicted_class_1: 0, by_model_version: {} },
  errors: { total: 0, by_model: {} },
};

function metricsFixture() {
  return {
    requests: {
      total: 24, successful: 22, failed: 2,
      status_codes: { "200": 22, "500": 2 },
      by_endpoint: { "/health": {
        requests: 24, successful: 22, failed: 2, status_codes: { "200": 22, "500": 2 },
        duration_ms: { total: 24, average: 1, max: 1 },
      } },
      duration_ms: { total: 24, average: 1, max: 1 },
    },
    predictions: {
      anomaly: { total: 8, normal: 6, anomaly: 2, by_model_version: { anomaly_v1: { total: 8, normal: 6, anomaly: 2 } } },
      failure: { total: 4, predicted_class_0: 3, predicted_class_1: 1, by_model_version: { failure_v1: { total: 4, predicted_class_0: 3, predicted_class_1: 1 } } },
      errors: { total: 1, by_model: { anomaly: 1 } },
    },
    runtime: { uptime_seconds: 3661, metrics_storage: "in_memory_process_local" as const },
    availability: { models: {
      anomaly: { available: true, status: "available", model_version: "anomaly_v1" },
      failure: { available: true, status: "available", model_version: "failure_v1" },
    }, database_available: true },
    rolling_window: {
      window_seconds: 300,
      requests: emptyRequests,
      predictions: {
        anomaly: { total: 4, normal: 3, anomaly: 1, by_model_version: { anomaly_v1: { total: 4, normal: 3, anomaly: 1 } } },
        failure: { total: 3, predicted_class_0: 2, predicted_class_1: 1, by_model_version: { failure_v1: { total: 3, predicted_class_0: 2, predicted_class_1: 1 } } },
        errors: { total: 0, by_model: {} },
      },
    },
  };
}

const reportFixture = {
  reference_version: "drift_reference_v1",
  generated_at: "2026-10-30T01:57:37.601829Z",
  reference_sample_size: 7000,
  current_sample_size: 40,
  minimum_sample_size: 20,
  overall_status: "drift_detected" as const,
  features: [{
    feature_name: "Air temperature [K]",
    method: "kolmogorov_smirnov_two_sample" as const,
    statistic: 0.2,
    p_value: 0.03,
    threshold: 0.05,
    threshold_kind: "p_value_significance_level" as const,
    drift_detected: true,
    reference_sample_size: 7000,
    current_sample_size: 40,
  }],
  interpretation: "Input distribution changed; this does not establish reduced accuracy.",
  report_id: 3,
  created_at: "2026-10-30T01:57:37.601829Z",
  window_start: "2026-10-30T01:57:37.601829Z",
  window_end: "2026-10-30T01:57:37.601829Z",
  batch_description: "Batch of 40 validated observations.",
  methodology: {},
  report_metadata: {},
  model_version: "anomaly=anomaly_v1;failure=failure_v1",
};

function renderOverview() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={queryClient}><OverviewPage /></QueryClientProvider>);
  return { queryClient, ...view };
}

beforeEach(() => {
  mockBackendState.mockReturnValue({ kind: "ready", health: { status: "ok" }, readiness: { status: "ready", models: { anomaly: true, failure: true }, database: true } });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("OverviewPage backend integration", () => {
  it("renders real metrics and latest per-feature drift data without combining model outcomes", async () => {
    mockGetMetrics.mockResolvedValue(metricsFixture());
    mockGetDrift.mockResolvedValue(reportFixture);
    renderOverview();

    expect(await screen.findByLabelText("Requests recorded: 24")).toBeInTheDocument();
    expect(screen.getByLabelText("Anomaly predictions: 8")).toBeInTheDocument();
    expect(screen.getByLabelText("Failure classifications: 4")).toBeInTheDocument();
    expect(screen.getByText("Cumulative since process start")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getAllByText("in 5 min")).toHaveLength(2);
    expect(await screen.findByRole("img", { name: /Anomaly detection outcomes in the last 5 min: Normal 3, Anomaly 1/ }, { timeout: 10000 })).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /Failure classification outcomes in the last 5 min: Class 0 2, Class 1 1/ }, { timeout: 10000 })).toBeInTheDocument();
    expect(screen.getByText("Input drift detected")).toBeInTheDocument();
    expect(screen.getByText("Air temperature [K]")).toBeInTheDocument();
    expect(screen.getByText("No global activity feed is available")).toBeInTheDocument();
  }, 15000);

  it("shows independent loading states while requests are pending", () => {
    mockGetMetrics.mockReturnValue(new Promise(() => undefined));
    mockGetDrift.mockReturnValue(new Promise(() => undefined));
    renderOverview();
    expect(screen.getByLabelText("Operational metrics loading")).toBeInTheDocument();
    expect(screen.getByLabelText("Prediction activity loading")).toBeInTheDocument();
    expect(screen.getByText("LOADING")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Drift monitoring" })).toHaveLength(1);
  });

  it("stays loading when metrics succeed while the initial drift request is pending", async () => {
    mockGetMetrics.mockResolvedValue(metricsFixture());
    mockGetDrift.mockReturnValue(new Promise(() => undefined));
    renderOverview();
    expect(await screen.findByLabelText("Requests recorded: 24")).toBeInTheDocument();
    expect(screen.getByText("LOADING")).toBeInTheDocument();
  });

  it("stays loading when drift succeeds while the initial metrics request is pending", async () => {
    mockGetMetrics.mockReturnValue(new Promise(() => undefined));
    mockGetDrift.mockResolvedValue(null);
    renderOverview();
    expect(await screen.findByText("No drift report has been generated yet.")).toBeInTheDocument();
    expect(screen.getByText("LOADING")).toBeInTheDocument();
  });

  it("treats latest-report 404 as a legitimate empty state", async () => {
    mockGetMetrics.mockResolvedValue(metricsFixture());
    mockGetDrift.mockResolvedValue(null);
    renderOverview();
    expect(await screen.findByLabelText("Requests recorded: 24")).toBeInTheDocument();
    expect(await screen.findByText("No drift report has been generated yet.")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("keeps metrics visible when the drift endpoint fails", async () => {
    mockGetMetrics.mockResolvedValue(metricsFixture());
    mockGetDrift.mockRejectedValue(new Error("service unavailable"));
    renderOverview();
    expect(await screen.findByLabelText("Requests recorded: 24")).toBeInTheDocument();
    expect(await screen.findByText("Latest drift report unavailable")).toBeInTheDocument();
    expect(screen.getByText("PARTIAL DATA")).toBeInTheDocument();
  });

  it("keeps the shell and drift report visible when metrics fail", async () => {
    mockGetMetrics.mockRejectedValue(new Error("service unavailable"));
    mockGetDrift.mockResolvedValue(reportFixture);
    renderOverview();
    expect(await screen.findByText("Operational metrics unavailable")).toBeInTheDocument();
    expect(screen.getByText("Input drift detected")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Operations overview" })).toBeInTheDocument();
    expect(screen.getByText("PARTIAL DATA")).toBeInTheDocument();
  });

  it("renders partial system readiness with unknowns rather than assuming availability", async () => {
    mockBackendState.mockReturnValue({ kind: "not-ready", health: { status: "ok" }, readiness: { status: "not_ready", models: { anomaly: false, failure: true }, database: false } });
    mockGetMetrics.mockResolvedValue(metricsFixture());
    mockGetDrift.mockResolvedValue(null);
    renderOverview();
    expect(await screen.findByText("Not ready")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.getByText("Available")).toBeInTheDocument();
  });

  it("renders zero counts as zero and uses empty activity states", async () => {
    mockGetMetrics.mockResolvedValue({
      ...metricsFixture(),
      requests: emptyRequests,
      predictions: emptyPredictions,
      rolling_window: { window_seconds: 300, requests: emptyRequests, predictions: emptyPredictions },
    });
    mockGetDrift.mockResolvedValue(null);
    renderOverview();
    expect(await screen.findByLabelText("Requests recorded: 0")).toBeInTheDocument();
    expect(screen.getByLabelText("Anomaly predictions: 0")).toBeInTheDocument();
    expect(screen.getByText("No anomaly predictions in this window")).toBeInTheDocument();
    expect(screen.getByText("No failure classifications in this window")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("labels cached metrics as stale after a failed refresh", async () => {
    mockGetMetrics.mockResolvedValueOnce(metricsFixture()).mockRejectedValueOnce(new Error("network down"));
    mockGetDrift.mockResolvedValue(null);
    const { queryClient } = renderOverview();
    expect(await screen.findByLabelText("Requests recorded: 24")).toBeInTheDocument();
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ["overview", "operational-metrics"], type: "active" });
    });
    expect(mockGetMetrics).toHaveBeenCalledTimes(2);
    expect(queryClient.getQueryState(["overview", "operational-metrics"])?.status).toBe("error");
    await waitFor(() => expect(screen.getByText(/Refresh failed\. Showing the last successful metrics snapshot/)).toBeInTheDocument());
    expect(screen.getByLabelText("Requests recorded: 24")).toBeInTheDocument();
    expect(screen.getByText("PARTIAL DATA")).toBeInTheDocument();
  });

  it("labels cached drift data as stale after a failed refresh", async () => {
    mockGetMetrics.mockResolvedValue(metricsFixture());
    mockGetDrift.mockResolvedValueOnce(reportFixture).mockRejectedValueOnce(new Error("network down"));
    const { queryClient } = renderOverview();
    expect(await screen.findByText("Input drift detected")).toBeInTheDocument();
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ["overview", "latest-drift-report"], type: "active" });
    });
    expect(mockGetDrift).toHaveBeenCalledTimes(2);
    expect(queryClient.getQueryState(["overview", "latest-drift-report"])?.status).toBe("error");
    expect(await screen.findByText(/Refresh failed\. Showing the last successful drift report/)).toBeInTheDocument();
    expect(screen.getByText("PARTIAL DATA")).toBeInTheDocument();
    expect(screen.getByText("Input drift detected")).toBeInTheDocument();
  });

  it("shows data unavailable after both sources fail without cached data", async () => {
    mockGetMetrics.mockRejectedValue(new Error("network down"));
    mockGetDrift.mockRejectedValue(new Error("network down"));
    renderOverview();
    expect(await screen.findByText("Operational metrics unavailable")).toBeInTheDocument();
    expect(await screen.findByText("Latest drift report unavailable")).toBeInTheDocument();
    expect(screen.getByText("DATA UNAVAILABLE")).toBeInTheDocument();
  });
});
