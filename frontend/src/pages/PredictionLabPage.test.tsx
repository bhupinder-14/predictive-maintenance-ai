import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PredictionLabPage } from "./PredictionLabPage";

const { mockGetEquipment, mockPredictAnomaly, mockPredictFailure } = vi.hoisted(() => ({
  mockGetEquipment: vi.fn(), mockPredictAnomaly: vi.fn(), mockPredictFailure: vi.fn(),
}));

vi.mock("@/api/equipment", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/equipment")>();
  return { ...actual, getEquipment: (...args: unknown[]) => mockGetEquipment(...args) };
});
vi.mock("@/api/predictions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/predictions")>();
  return { ...actual, predictAnomaly: (...args: unknown[]) => mockPredictAnomaly(...args), predictFailure: (...args: unknown[]) => mockPredictFailure(...args) };
});

const equipment = { id: 12, name: "Mill 12", equipment_type: "M", location: "Bay 3", created_at: "2026-10-30T00:00:00Z" };
const anomalyResult = {
  prediction_id: "anomaly-12", equipment_id: 12, reading_id: 90, anomaly_score: -0.61, classification: "anomaly" as const,
  model_version: "anomaly_v1", prediction_timestamp: "2026-10-31T10:00:00Z", inference_latency_ms: 2.3,
  explanation: { method: "isolation_forest_feature_deviation", anomaly_score: -0.61, top_suspicious_features: [{ feature: "num__Torque [Nm]", standardised_value: 2.3, abs_deviation: 2.3 }] },
};
const failureResult = {
  prediction_id: "failure-12", equipment_id: 12, reading_id: 91, predicted_class: 1 as const,
  failure_probability: 0.73, model_version: "failure_v1", prediction_timestamp: "2026-10-31T10:01:00Z", inference_latency_ms: 3.2,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><PredictionLabPage /></QueryClientProvider>);
}

async function selectExistingEquipment() {
  await screen.findByRole("option", { name: /Mill 12/ }, { timeout: 5000 });
  fireEvent.change(screen.getByLabelText(/^Equipment record/), { target: { value: "12" } });
}

function fillValidSensors() {
  fireEvent.change(screen.getByLabelText(/^Type/), { target: { value: "M" } });
  fireEvent.change(screen.getByLabelText(/Air temperature/), { target: { value: "300.2" } });
  fireEvent.change(screen.getByLabelText(/Process temperature/), { target: { value: "310.1" } });
  fireEvent.change(screen.getByLabelText(/Rotational speed/), { target: { value: "1450" } });
  fireEvent.change(screen.getByLabelText(/Torque/), { target: { value: "38.6" } });
  fireEvent.change(screen.getByLabelText(/Tool wear/), { target: { value: "80" } });
}

beforeEach(() => {
  mockGetEquipment.mockReset().mockResolvedValue([equipment]);
  mockPredictAnomaly.mockReset().mockResolvedValue(anomalyResult);
  mockPredictFailure.mockReset().mockResolvedValue(failureResult);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Prediction Lab", () => {
  it("submits the exact validated sensor fields and existing equipment ID to anomaly only", async () => {
    renderPage();
    await selectExistingEquipment();
    fillValidSensors();
    fireEvent.click(screen.getByRole("button", { name: "Run anomaly detection" }));
    expect(await screen.findByText("Anomalous sensor pattern")).toBeInTheDocument();
    expect(mockPredictAnomaly).toHaveBeenCalledWith({
      Type: "M", "Air temperature [K]": 300.2, "Process temperature [K]": 310.1,
      "Rotational speed [rpm]": 1450, "Torque [Nm]": 38.6, "Tool wear [min]": 80, equipment_id: 12,
    });
    expect(mockPredictFailure).not.toHaveBeenCalled();
    const result = within(screen.getByLabelText("Anomaly detection result"));
    expect(result.getAllByText(/not a failure probability/)).toHaveLength(2);
    const announcement = result.getByRole("status");
    expect(announcement).toHaveAttribute("aria-live", "polite");
    expect(announcement).toHaveAttribute("aria-atomic", "true");
    expect(announcement).toHaveTextContent(/Anomaly detection result: anomalous sensor pattern/);
    expect(announcement).toHaveTextContent(/score_samples output: -0.61/);
    expect(announcement).toHaveTextContent(/not a failure probability/);
    expect(announcement).toHaveTextContent(/Saved prediction anomaly-12; equipment 12, reading 90/);
  });

  it("shows required-field validation and does not submit incomplete observations", async () => {
    renderPage();
    await selectExistingEquipment();
    fireEvent.click(screen.getByRole("button", { name: "Predict machine failure" }));
    expect(await screen.findByText("Choose a machine type.")).toBeInTheDocument();
    expect(screen.getAllByText("Enter a finite numeric value.")).toHaveLength(5);
    expect(mockPredictFailure).not.toHaveBeenCalled();
  });

  it.each([
    ["Air temperature", "289", "290"],
    ["Process temperature", "321", "300"],
    ["Rotational speed", "3001", "1000"],
    ["Torque", "101", "0"],
    ["Tool wear", "301", "0"],
  ])("rejects an out-of-range %s value", async (label, invalid, min) => {
    renderPage();
    await selectExistingEquipment();
    fillValidSensors();
    fireEvent.change(screen.getByLabelText(new RegExp(label)), { target: { value: invalid } });
    fireEvent.click(screen.getByRole("button", { name: "Run anomaly detection" }));
    expect(await screen.findByText(new RegExp(`from ${label === "Air temperature" ? "290" : label === "Process temperature" ? "300" : label === "Rotational speed" ? "1000" : "0"}`))).toBeInTheDocument();
    expect(mockPredictAnomaly).not.toHaveBeenCalled();
    expect(min).toBeTruthy();
  });

  it("registers explicitly named equipment through the supported prediction request", async () => {
    mockGetEquipment.mockResolvedValue([]);
    renderPage();
    await screen.findByLabelText("Equipment name");
    fireEvent.change(screen.getByLabelText("Equipment name"), { target: { value: "User-entered lathe" } });
    fireEvent.change(screen.getByLabelText(/^Type/), { target: { value: "L" } });
    fireEvent.change(screen.getByLabelText(/Air temperature/), { target: { value: "295" } });
    fireEvent.change(screen.getByLabelText(/Process temperature/), { target: { value: "305" } });
    fireEvent.change(screen.getByLabelText(/Rotational speed/), { target: { value: "1200" } });
    fireEvent.change(screen.getByLabelText(/Torque/), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText(/Tool wear/), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Predict machine failure" }));
    await screen.findByText("Machine failure class 1");
    expect(mockPredictFailure).toHaveBeenCalledWith(expect.objectContaining({ equipment_name: "User-entered lathe" }));
    expect(mockPredictFailure.mock.calls[0]?.[0]).not.toHaveProperty("equipment_id");
    const announcement = within(screen.getByLabelText("Failure classification result")).getByRole("status");
    expect(announcement).toHaveTextContent(/Failure classification result: class 1/);
    expect(announcement).toHaveTextContent(/Class-1 predict_proba estimator output: 73%/);
    expect(announcement).toHaveTextContent(/uncalibrated, not a calibrated probability or future-failure forecast/);
    expect(announcement).toHaveTextContent(/Saved prediction failure-12; equipment 12, reading 91/);
  });

  it("keeps anomaly errors and failure success independent", async () => {
    mockPredictAnomaly.mockRejectedValue(new Error("Anomaly model is unavailable"));
    renderPage();
    await selectExistingEquipment();
    fillValidSensors();
    fireEvent.click(screen.getByRole("button", { name: "Run anomaly detection" }));
    expect(await screen.findByText("Anomaly detection failed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Predict machine failure" }));
    expect(await screen.findByText("Machine failure class 1")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Failure classification result")).getByText(/not calibrated/)).toBeInTheDocument();
  });

  it("does not expose raw server stack details in the model result error", async () => {
    const privateDetail = "Traceback C:\\private\\model.py token=secret";
    mockPredictAnomaly.mockRejectedValue(Object.assign(new Error(privateDetail), {
      isAxiosError: true,
      response: { status: 500, data: { detail: privateDetail } },
    }));
    renderPage();
    await selectExistingEquipment();
    fillValidSensors();
    fireEvent.click(screen.getByRole("button", { name: "Run anomaly detection" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The prediction request could not be completed. Please try again.");
    expect(alert).not.toHaveTextContent(/private|model\.py|secret|Traceback/);
  });

  it("shows the unknown-save warning only in the timed-out model's result panel", async () => {
    mockPredictAnomaly.mockRejectedValue(Object.assign(new Error("timeout"), {
      isAxiosError: true, code: "ECONNABORTED", request: {},
    }));
    renderPage();
    await selectExistingEquipment();
    fillValidSensors();
    fireEvent.click(screen.getByRole("button", { name: "Run anomaly detection" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/API may have saved this prediction/)).toBeInTheDocument();
    expect(within(alert).getByText(/selected equipment's Prediction History before retrying/)).toBeInTheDocument();
    expect(within(alert).getByText(/Do not resubmit until you have checked equipment history/)).toBeInTheDocument();
    expect(mockPredictFailure).not.toHaveBeenCalled();
    expect(screen.queryByText(/Saved prediction anomaly-12/)).not.toBeInTheDocument();
    expect(within(screen.getByLabelText("Prediction results")).queryByRole("status")).not.toBeInTheDocument();
  });

  it("prevents duplicate submissions for the same model while it is pending", async () => {
    let resolvePrediction: ((value: typeof anomalyResult) => void) | undefined;
    mockPredictAnomaly.mockReturnValue(new Promise<typeof anomalyResult>((resolve) => { resolvePrediction = resolve; }));
    renderPage();
    await selectExistingEquipment();
    fillValidSensors();
    const runButton = screen.getByRole("button", { name: "Run anomaly detection" });
    fireEvent.click(runButton);
    await waitFor(() => expect(runButton).toBeDisabled());
    expect(runButton).toHaveAttribute("aria-busy", "true");
    fireEvent.click(runButton);
    expect(mockPredictAnomaly).toHaveBeenCalledTimes(1);
    resolvePrediction?.(anomalyResult);
    expect(await screen.findByText("Anomalous sensor pattern")).toBeInTheDocument();
  });
});
