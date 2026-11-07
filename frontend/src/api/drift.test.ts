import { AxiosError } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { getLatestDriftReport, isLatestDriftReport } from "./drift";

afterEach(() => vi.restoreAllMocks());

const featureNames = [
  "Air temperature [K]", "Process temperature [K]", "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]",
];
const numericFeatures = featureNames.map((feature_name) => ({
  feature_name,
  method: "kolmogorov_smirnov_two_sample",
  statistic: 0.2,
  p_value: 0.03,
  threshold: 0.05,
  threshold_kind: "p_value_significance_level",
  drift_detected: true,
  reference_sample_size: 7000,
  current_sample_size: 20,
}));
const categoricalFeature = {
  feature_name: "Type",
  method: "total_variation_distance",
  statistic: 0.2,
  p_value: null,
  threshold: 0.1,
  threshold_kind: "distance_threshold",
  drift_detected: true,
  reference_sample_size: 7000,
  current_sample_size: 20,
};
const validReport = {
  reference_version: "drift_reference_v1",
  generated_at: "2026-10-30T01:57:37.601829Z",
  reference_sample_size: 7000,
  current_sample_size: 20,
  minimum_sample_size: 20,
  overall_status: "drift_detected",
  features: [...numericFeatures, categoricalFeature],
  interpretation: "Drift indicates an input distribution change.",
  report_id: 3,
  created_at: "2026-10-30T01:57:37.601829Z",
  window_start: "2026-10-30T01:57:37.601829Z",
  window_end: "2026-10-30T01:57:37.601829Z",
  batch_description: "Validated batch; no chronological sequence.",
  methodology: { methods: ["kolmogorov_smirnov_two_sample"] },
  report_metadata: { model_versions: { anomaly: "anomaly_v1" } },
  model_version: "anomaly=anomaly_v1;failure=failure_v1",
};

describe("latest drift report service", () => {
  it("validates actual persisted report and per-feature fields", () => {
    expect(isLatestDriftReport(validReport)).toBe(true);
    expect(isLatestDriftReport({ ...validReport, features: [{ ...numericFeatures[0], statistic: "unknown" }] })).toBe(false);
  });

  it.each([
    ["KS statistic above one", { ...numericFeatures[0], statistic: 1.01 }],
    ["negative KS statistic", { ...numericFeatures[0], statistic: -0.01 }],
    ["p-value above one", { ...numericFeatures[0], p_value: 1.01, drift_detected: false }],
    ["negative p-value", { ...numericFeatures[0], p_value: -0.01 }],
    ["invalid KS threshold", { ...numericFeatures[0], threshold: 0 }],
    ["invalid categorical threshold", { ...categoricalFeature, threshold: 1.1 }],
    ["negative sample size", { ...numericFeatures[0], current_sample_size: -1 }],
    ["fractional sample size", { ...numericFeatures[0], reference_sample_size: 7000.5 }],
    ["unknown feature name", { ...numericFeatures[0], feature_name: "Product ID" }],
  ])("rejects %s", (_label, badFeature) => {
    const features = [...numericFeatures, categoricalFeature];
    features[0] = badFeature;
    expect(isLatestDriftReport({ ...validReport, features })).toBe(false);
  });

  it("rejects empty and duplicate feature result lists", () => {
    expect(isLatestDriftReport({ ...validReport, features: [] })).toBe(false);
    const duplicate = [...numericFeatures.slice(0, 4), numericFeatures[4], { ...numericFeatures[4] }];
    expect(isLatestDriftReport({ ...validReport, features: duplicate })).toBe(false);
  });

  it("rejects contradictory overall status and report metadata", () => {
    expect(isLatestDriftReport({ ...validReport, overall_status: "no_drift_detected" })).toBe(false);
    expect(isLatestDriftReport({ ...validReport, report_metadata: { overall_status: "no_drift_detected" } })).toBe(false);
  });

  it("accepts a valid insufficient-data report with null per-feature statistics and labels", () => {
    const insufficientFeatures = [
      ...featureNames.map((feature_name) => ({
        feature_name, method: "kolmogorov_smirnov_two_sample", statistic: null, p_value: null,
        threshold: 0.05, threshold_kind: "p_value_significance_level", drift_detected: null,
        reference_sample_size: 7000, current_sample_size: 5,
      })),
      { feature_name: "Type", method: "total_variation_distance", statistic: null, p_value: null,
        threshold: 0.1, threshold_kind: "distance_threshold", drift_detected: null,
        reference_sample_size: 7000, current_sample_size: 5 },
    ];
    expect(isLatestDriftReport({
      ...validReport,
      current_sample_size: 5,
      overall_status: "insufficient_data",
      features: insufficientFeatures,
      report_metadata: { overall_status: "insufficient_data", reference_sample_size: 7000, current_sample_size: 5, minimum_sample_size: 20 },
    })).toBe(true);
  });

  it("requests the latest report endpoint and returns parsed data", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: validReport } as never);
    await expect(getLatestDriftReport()).resolves.toEqual(validReport);
    expect(get).toHaveBeenCalledWith("/monitoring/drift");
  });

  it("treats HTTP 404 as the expected no-report state", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValueOnce(new AxiosError("Not found", "ERR_BAD_REQUEST", undefined, undefined, {
      status: 404, statusText: "Not Found", headers: {}, config: {} as never, data: { detail: "No drift report is available" },
    }));
    await expect(getLatestDriftReport()).resolves.toBeNull();
  });

  it("keeps other service errors separate from the empty state", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValueOnce(new AxiosError("Request failed", "ERR_BAD_RESPONSE", undefined, undefined, {
      status: 503, statusText: "Unavailable", headers: {}, config: {} as never, data: {},
    }));
    await expect(getLatestDriftReport()).rejects.toThrow("Latest drift report could not be loaded.");
  });
});
