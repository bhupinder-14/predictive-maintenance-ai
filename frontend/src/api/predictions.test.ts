import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import {
  getSavedPrediction,
  parseAnomalyPrediction,
  parseFailurePrediction,
  parseSavedPrediction,
  predictAnomaly,
  predictFailure,
  predictionErrorMessage,
  type PredictionInput,
} from "./predictions";

afterEach(() => vi.restoreAllMocks());

const anomalyResponse = {
  prediction_id: "anomaly-id", equipment_id: 7, reading_id: 41, anomaly_score: -0.42,
  classification: "anomaly", model_version: "anomaly_v1", prediction_timestamp: "2026-10-31T10:05:01Z",
  inference_latency_ms: 2.1,
  explanation: { method: "isolation_forest_feature_deviation", anomaly_score: -0.42, top_suspicious_features: [{ feature: "num__Torque [Nm]", standardised_value: 2.1, abs_deviation: 2.1 }] },
};
const failureResponse = {
  prediction_id: "failure-id", equipment_id: 7, reading_id: 42, predicted_class: 1,
  failure_probability: 0.72, model_version: "failure_v1", prediction_timestamp: "2026-10-31T10:06:01Z", inference_latency_ms: 3.5,
};
const input: PredictionInput = {
  Type: "M", "Air temperature [K]": 300.2, "Process temperature [K]": 310.1,
  "Rotational speed [rpm]": 1450, "Torque [Nm]": 38.6, "Tool wear [min]": 80, equipment_id: 7,
};

function axiosError(status: number, data: unknown) {
  return Object.assign(new Error("Request failed"), {
    isAxiosError: true,
    response: { status, data },
  });
}

describe("prediction API", () => {
  it("parses the anomaly response and rejects an invalid classification", () => {
    expect(parseAnomalyPrediction(anomalyResponse)).toMatchObject({ classification: "anomaly", anomaly_score: -0.42, explanation: { top_suspicious_features: [{ feature: "num__Torque [Nm]" }] } });
    expect(() => parseAnomalyPrediction({ ...anomalyResponse, classification: "failure" })).toThrow("Anomaly prediction response is invalid.");
  });

  it("posts anomaly input to its independent endpoint", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValueOnce({ data: anomalyResponse } as never);
    await expect(predictAnomaly(input)).resolves.toMatchObject({ prediction_id: "anomaly-id", equipment_id: 7 });
    expect(post).toHaveBeenCalledWith("/predict/anomaly", input);
  });

  it("parses failure class separately from the estimator probability and validates its range", () => {
    expect(parseFailurePrediction(failureResponse)).toMatchObject({ predicted_class: 1, failure_probability: 0.72 });
    expect(() => parseFailurePrediction({ ...failureResponse, failure_probability: 1.2 })).toThrow("Failure prediction response is invalid.");
  });

  it("posts failure input only to the failure endpoint", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValueOnce({ data: failureResponse } as never);
    await expect(predictFailure(input)).resolves.toMatchObject({ prediction_id: "failure-id", predicted_class: 1 });
    expect(post).toHaveBeenCalledWith("/predict/failure", input);
  });

  it("parses persisted prediction fields and rejects contradictory model columns", () => {
    const record = { id: "anomaly-id", equipment_id: 7, reading_id: 41, model_version: "anomaly_v1", anomaly_score: -0.42, is_anomaly: true, failure_probability: null, latency_ms: 2.1, created_at: "2026-10-31T10:05:01Z" };
    expect(parseSavedPrediction(record)).toEqual(record);
    expect(() => parseSavedPrediction({ ...record, failure_probability: 0.4 })).toThrow("Saved prediction model fields are inconsistent.");
  });

  it("retrieves the exact prediction identifier", async () => {
    const record = { id: "failure-id", equipment_id: 7, reading_id: 42, model_version: "failure_v1", anomaly_score: null, is_anomaly: null, failure_probability: 0.72, latency_ms: 3.5, created_at: "2026-10-31T10:06:01Z" };
    const get = vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: record } as never);
    await expect(getSavedPrediction("failure-id")).resolves.toEqual(record);
    expect(get).toHaveBeenCalledWith("/predictions/failure-id");
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: { ...record, id: "other-id" } } as never);
    await expect(getSavedPrediction("failure-id")).rejects.toThrow("Saved prediction ID does not match the requested record.");
  });

  it("maps a backend 422 sensor field error without exposing its input value", () => {
    const error = axiosError(422, { detail: [{
      loc: ["body", "Air temperature [K]"],
      msg: "Input should be less than or equal to 310",
      type: "less_than_equal",
      input: 999,
    }] });

    const message = predictionErrorMessage(error);
    expect(message).toBe("Input validation failed — Air temperature: Input should be less than or equal to 310");
    expect(message).not.toContain("999");
  });

  it("maps multiple backend validation locations to their form labels", () => {
    const message = predictionErrorMessage(axiosError(422, { detail: [
      { loc: ["body", "Type"], msg: "Input should be 'L', 'M' or 'H'", type: "literal_error", input: "X" },
      { loc: ["body", "Torque [Nm]"], msg: "Input should be greater than or equal to 0", type: "greater_than_equal", input: -3 },
      { loc: ["body", "equipment_id"], msg: "Field required", type: "missing" },
    ] }));

    expect(message).toContain("Machine type: Input should be 'L', 'M' or 'H'");
    expect(message).toContain("Torque: Input should be greater than or equal to 0");
    expect(message).toContain("Equipment record: Field required");
    expect(message).not.toContain('"input"');
    expect(message).not.toContain("X");
    expect(message).not.toContain("-3");
  });

  it.each([
    ["missing detail", {}],
    ["null detail", { detail: null }],
    ["string detail", { detail: "invalid input" }],
    ["object detail", { detail: { loc: ["body", "Torque [Nm]"], msg: "private value" } }],
    ["malformed issue", { detail: [{ loc: "body.Torque", msg: "private value", input: "private value" }] }],
    ["empty detail", { detail: [] }],
  ])("uses a safe validation fallback for %s", (_name, data) => {
    const message = predictionErrorMessage(axiosError(422, data));
    expect(message).toBe("The API rejected the observation. Review the sensor values and equipment association.");
    expect(message).not.toContain("private value");
  });

  it("identifies an unmapped field as a request-level validation issue", () => {
    expect(predictionErrorMessage(axiosError(422, { detail: [
      { loc: ["body", "unknown_internal_field"], msg: "Unsupported request field" },
    ] }))).toBe("Input validation failed — Request: Unsupported request field");
  });

  it("uses the validation fallback when no issue contains a safe message", () => {
    expect(predictionErrorMessage(axiosError(422, { detail: [
      { loc: ["body", "Air temperature [K]"], msg: "   ", input: 999 },
    ] }))).toBe("The API rejected the observation. Review the sensor values and equipment association.");
  });

  it("preserves safe string backend details such as model-unavailable 503 responses", () => {
    expect(predictionErrorMessage(axiosError(503, { detail: "Failure model is unavailable" }))).toBe("Failure model is unavailable");
  });

  it("does not surface unrecognized server strings or raw stack details", () => {
    const stack = "Traceback (most recent call last): C:\\private\\secret.py SQL password=secret";
    const message = predictionErrorMessage(axiosError(500, { detail: stack, debug: stack }));
    expect(message).toBe("The prediction request could not be completed. Please try again.");
    expect(message).not.toContain("secret");
    expect(message).not.toContain("private");
  });

  it("explains timeout ambiguity and directs the user to equipment history before retrying", () => {
    const error = Object.assign(new Error("timeout"), { isAxiosError: true, code: "ECONNABORTED", request: {} });
    expect(predictionErrorMessage(error)).toContain("The API may have saved this prediction.");
    expect(predictionErrorMessage(error)).toContain("selected equipment's Prediction History before retrying");
    expect(predictionErrorMessage(error)).toContain("exactly-once execution is not guaranteed");
  });

  it("treats a dispatched network failure as an unknown outcome, not a definite failure", () => {
    const error = Object.assign(new Error("network down"), { isAxiosError: true, code: "ERR_NETWORK", request: {} });
    expect(predictionErrorMessage(error)).toContain("The API may have saved this prediction.");
    expect(predictionErrorMessage(error)).toContain("Prediction History before retrying");
  });

  it("keeps explicit 422 validation and 503 unavailability responses distinct from ambiguous outcomes", () => {
    expect(predictionErrorMessage(axiosError(422, { detail: [{ loc: ["body", "Torque [Nm]"], msg: "Out of range" }] }))).toContain("Torque: Out of range");
    expect(predictionErrorMessage(axiosError(503, { detail: "Failure model is unavailable" }))).toBe("Failure model is unavailable");
  });

  it("keeps network and other unstructured failures generic", () => {
    expect(predictionErrorMessage(new Error("network down"))).toBe("The prediction request could not be completed. Please try again.");
  });
});
