import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PredictionHistoryPage } from "./PredictionHistoryPage";

const { mockGetEquipment, mockGetEquipmentHistory, mockGetSavedPrediction } = vi.hoisted(() => ({
  mockGetEquipment: vi.fn(), mockGetEquipmentHistory: vi.fn(), mockGetSavedPrediction: vi.fn(),
}));

vi.mock("@/api/equipment", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/equipment")>();
  return { ...actual, getEquipment: (...args: unknown[]) => mockGetEquipment(...args), getEquipmentHistory: (...args: unknown[]) => mockGetEquipmentHistory(...args) };
});
vi.mock("@/api/predictions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/predictions")>();
  return { ...actual, getSavedPrediction: (...args: unknown[]) => mockGetSavedPrediction(...args) };
});

const equipment = { id: 12, name: "Mill 12", equipment_type: "M", location: "Bay 3", created_at: "2026-10-30T00:00:00Z" };
const otherEquipment = { id: 13, name: "Press 13", equipment_type: "L", location: null, created_at: "2026-10-30T00:00:00Z" };
const reading = {
  id: 90, equipment_id: 12, timestamp: "2026-10-31T10:00:00Z", Type: "M",
  "Air temperature [K]": 300.2, "Process temperature [K]": 310.1, "Rotational speed [rpm]": 1450,
  "Torque [Nm]": 38.6, "Tool wear [min]": 80, source: "api",
};
const anomalySummary = { id: "saved-anomaly", model_version: "anomaly_v1", anomaly_score: -0.42, is_anomaly: true, failure_probability: null, latency_ms: 2.1, created_at: "2026-10-31T10:00:01Z" };
const failureSummary = { id: "saved-failure", model_version: "failure_v1", anomaly_score: null, is_anomaly: null, failure_probability: 0.37, latency_ms: 3.4, created_at: "2026-10-31T10:00:02Z" };
const history = { equipment, items: [{ reading, predictions: [anomalySummary, failureSummary] }] };
const savedPrediction = { id: "saved-anomaly", equipment_id: 12, reading_id: 90, model_version: "anomaly_v1", anomaly_score: -0.42, is_anomaly: true, failure_probability: null, latency_ms: 2.1, created_at: "2026-10-31T10:00:01Z" };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><PredictionHistoryPage /></QueryClientProvider>);
}

async function selectEquipment() {
  await screen.findByRole("option", { name: /Mill 12/ });
  fireEvent.change(screen.getByLabelText("Equipment record"), { target: { value: "12" } });
}

beforeEach(() => {
  mockGetEquipment.mockReset().mockResolvedValue([equipment, otherEquipment]);
  mockGetEquipmentHistory.mockReset().mockResolvedValue(history);
  mockGetSavedPrediction.mockReset().mockResolvedValue(savedPrediction);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Prediction History", () => {
  it("loads only the selected equipment history and separates anomaly and failure records", async () => {
    renderPage();
    await selectEquipment();
    expect(await screen.findByText("Anomaly detection · Anomaly")).toBeInTheDocument();
    expect(screen.getByText("Failure classification · estimator output")).toBeInTheDocument();
    expect(screen.getByText("Score -0.42")).toBeInTheDocument();
    expect(screen.getByText("Estimator output 37%")).toBeInTheDocument();
    expect(screen.getByText(/not calibrated probabilities/)).toBeInTheDocument();
    expect(mockGetEquipmentHistory).toHaveBeenCalledWith(12, 50, 0);
    expect(screen.getByText("300.2 K")).toBeInTheDocument();
  });

  it("shows an honest empty state for a selected equipment with no records", async () => {
    mockGetEquipmentHistory.mockResolvedValue({ equipment, items: [] });
    renderPage();
    await selectEquipment();
    expect(await screen.findByText("No readings or predictions for this equipment")).toBeInTheDocument();
  });

  it("reports history errors without presenting fabricated records", async () => {
    mockGetEquipmentHistory.mockRejectedValue(new Error("unavailable"));
    renderPage();
    await selectEquipment();
    expect(await screen.findByText("Equipment history unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Anomaly detection · Anomaly")).not.toBeInTheDocument();
  });

  it("retrieves and verifies the selected saved prediction record with its associated reading", async () => {
    renderPage();
    await selectEquipment();
    await screen.findByText("Anomaly detection · Anomaly");
    fireEvent.click(screen.getAllByRole("button", { name: "View saved record" })[0]!);
    expect(await screen.findByText("Prediction details")).toBeInTheDocument();
    expect(await screen.findByText("Associated sensor reading #90")).toBeInTheDocument();
    expect(screen.getByText("History summary ID saved-anomaly matches the retrieved prediction record.")).toBeInTheDocument();
    expect(mockGetSavedPrediction).toHaveBeenCalledWith("saved-anomaly");
  });

  it("rejects a saved record whose equipment or reading differs from the selected history row", async () => {
    mockGetSavedPrediction.mockResolvedValue({ ...savedPrediction, equipment_id: 13 });
    renderPage();
    await selectEquipment();
    await screen.findByText("Anomaly detection · Anomaly");
    fireEvent.click(screen.getAllByRole("button", { name: "View saved record" })[0]!);
    expect(await screen.findByText("Saved record does not match history")).toBeInTheDocument();
  });

  it("paginates history using the backend offset when a full page is returned", async () => {
    const page = { equipment, items: Array.from({ length: 50 }, (_, index) => ({ reading: { ...reading, id: 100 + index }, predictions: [] })) };
    mockGetEquipmentHistory.mockResolvedValueOnce(page).mockResolvedValueOnce({ equipment, items: [{ reading: { ...reading, id: 50 }, predictions: [] }] });
    renderPage();
    await selectEquipment();
    expect(await screen.findByText(/SENSOR READING · #100/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load older readings" }));
    await waitFor(() => expect(mockGetEquipmentHistory).toHaveBeenCalledWith(12, 50, 50));
    expect(await screen.findByText(/SENSOR READING · #50/i)).toBeInTheDocument();
    expect(await screen.findByText("End of available equipment history.")).toBeInTheDocument();
  });
});
