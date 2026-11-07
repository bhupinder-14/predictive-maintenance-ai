import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DriftMonitoringPage } from "./DriftMonitoringPage";

const { mockLatestDrift } = vi.hoisted(() => ({ mockLatestDrift: vi.fn() }));
vi.mock("@/hooks/useLatestDriftReport", () => ({ useLatestDriftReport: () => mockLatestDrift() }));

const features = [
  ["Air temperature [K]", "kolmogorov_smirnov_two_sample", 0.25, 0.02, 0.05, "p_value_significance_level", true],
  ["Process temperature [K]", "kolmogorov_smirnov_two_sample", 0.01, 0.99, 0.05, "p_value_significance_level", false],
  ["Rotational speed [rpm]", "kolmogorov_smirnov_two_sample", 0.04, 0.7, 0.05, "p_value_significance_level", false],
  ["Torque [Nm]", "kolmogorov_smirnov_two_sample", 0.03, 0.8, 0.05, "p_value_significance_level", false],
  ["Tool wear [min]", "kolmogorov_smirnov_two_sample", 0.06, 0.4, 0.05, "p_value_significance_level", false],
  ["Type", "total_variation_distance", 0.12, null, 0.1, "distance_threshold", true],
].map(([feature_name, method, statistic, p_value, threshold, threshold_kind, drift_detected]) => ({
  feature_name: String(feature_name),
  method: method as "kolmogorov_smirnov_two_sample" | "total_variation_distance",
  statistic: statistic as number | null,
  p_value: p_value as number | null,
  threshold: Number(threshold),
  threshold_kind: threshold_kind as "p_value_significance_level" | "distance_threshold",
  drift_detected: drift_detected as boolean | null,
  reference_sample_size: 7000,
  current_sample_size: 40,
}));

const report = {
  reference_version: "drift_reference_v1",
  generated_at: "2026-11-01T12:00:00Z",
  reference_sample_size: 7000,
  current_sample_size: 40,
  minimum_sample_size: 20,
  overall_status: "drift_detected" as const,
  features,
  interpretation: "Distributional change does not prove model performance degradation.",
  report_id: 18,
  created_at: "2026-11-01T12:00:00Z",
  window_start: "2026-11-01T12:00:00Z",
  window_end: "2026-11-01T12:00:00Z",
  batch_description: "40 validated observations",
  methodology: {},
  report_metadata: {},
  model_version: "anomaly=anomaly_v1;failure=failure_v1",
};

function query(data: typeof report | null | undefined, overrides: Record<string, unknown> = {}) {
  return { data, isPending: false, isError: false, isFetching: false, dataUpdatedAt: 1_798_000_000_000, refetch: vi.fn(), ...overrides };
}

beforeEach(() => mockLatestDrift.mockReset().mockReturnValue(query(report)));
afterEach(() => cleanup());

describe("DriftMonitoringPage", () => {
  it("shows the latest actual report and its feature statistics", () => {
    render(<DriftMonitoringPage />);
    expect(screen.getByText("LATEST REPORT ONLY")).toBeInTheDocument();
    expect(screen.getAllByText("Drift detected")).toHaveLength(2);
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("Air temperature [K]")).toBeInTheDocument();
    expect(screen.getAllByText("Total variation distance")).toHaveLength(2);
    expect(screen.getByText("Distributional change does not prove model performance degradation.")).toBeInTheDocument();
    expect(screen.getByText("This page shows the latest persisted report only. It does not provide report history or generate a new report.")).toBeInTheDocument();
  });

  it("treats the backend no-report response as a valid empty state", () => {
    mockLatestDrift.mockReturnValue(query(null));
    render(<DriftMonitoringPage />);
    expect(screen.getByText("No drift report has been generated yet.")).toBeInTheDocument();
    expect(screen.getByText(/returns the latest saved report only/)).toBeInTheDocument();
  });

  it("shows a loading state while the latest report is pending", () => {
    mockLatestDrift.mockReturnValue(query(undefined, { isPending: true }));
    render(<DriftMonitoringPage />);
    expect(screen.getByRole("heading", { name: "Drift monitoring", level: 1 })).toBeInTheDocument();
    expect(document.querySelectorAll(".overview-drift-skeletons .skeleton")).toHaveLength(3);
  });

  it("shows an error and retries the shared latest-report query", () => {
    const refetch = vi.fn();
    mockLatestDrift.mockReturnValue(query(undefined, { isError: true, refetch }));
    render(<DriftMonitoringPage />);
    expect(screen.getByText("Latest drift report unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledOnce();
  });
});
