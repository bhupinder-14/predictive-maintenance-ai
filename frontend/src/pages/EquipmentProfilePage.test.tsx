import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useNavigate, MemoryRouter, Route, Routes } from "react-router-dom";
import { AxiosError, AxiosHeaders } from "axios";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EquipmentProfilePage } from "./EquipmentProfilePage";
import type { EquipmentHistoryEntry, EquipmentHistoryResponse } from "@/api/equipment";

const { mockGetEquipment, mockGetEquipmentHistory, mockBuildAnalytics } = vi.hoisted(() => ({ mockGetEquipment: vi.fn(), mockGetEquipmentHistory: vi.fn(), mockBuildAnalytics: vi.fn() }));
vi.mock("@/api/equipment", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/equipment")>();
  return { ...actual, getEquipment: (...args: unknown[]) => mockGetEquipment(...args), getEquipmentHistory: (...args: unknown[]) => mockGetEquipmentHistory(...args) };
});
vi.mock("@/lib/equipment-analytics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/equipment-analytics")>();
  return {
    ...actual,
    buildEquipmentAnalytics: (...args: Parameters<typeof actual.buildEquipmentAnalytics>) => {
      mockBuildAnalytics(...args);
      return actual.buildEquipmentAnalytics(...args);
    },
  };
});

const equipment = (id: number) => ({ id, name: `Machine ${id}`, equipment_type: "M", location: "Line A", created_at: "2026-10-30T08:00:00Z" });
const reading = (id: number, equipmentId = 4, timestamp = "2026-10-31T10:00:00Z"): EquipmentHistoryEntry["reading"] => ({
  id, equipment_id: equipmentId, timestamp, Type: "M", "Air temperature [K]": 300.2,
  "Process temperature [K]": 310.1, "Rotational speed [rpm]": 1450, "Torque [Nm]": 38.6,
  "Tool wear [min]": 80, source: "api",
});
const anomaly = { id: "anomaly-one", model_version: "anomaly_v1", anomaly_score: -0.42, is_anomaly: true, failure_probability: null, latency_ms: 2.1, created_at: "2026-10-31T10:01:00Z" };
const failure = { id: "failure-one", model_version: "failure_v1", anomaly_score: null, is_anomaly: null, failure_probability: 0.37, latency_ms: 3.4, created_at: "2026-10-31T10:02:00Z" };
const historyFor = (id: number, items: EquipmentHistoryEntry[] = [{ reading: reading(40, id), predictions: [anomaly, failure] }]): EquipmentHistoryResponse => ({ equipment: equipment(id), items });

function renderPage(path = "/equipment/4") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/equipment/:equipmentId" element={<><RouteSwitcher /><RerenderHarness /></>} /></Routes></MemoryRouter></QueryClientProvider>);
}
function RouteSwitcher() {
  const navigate = useNavigate();
  return <button type="button" onClick={() => navigate("/equipment/5")}>Switch equipment</button>;
}
function RerenderHarness() {
  const [revision, setRevision] = useState(0);
  return <><button type="button" onClick={() => setRevision((current) => current + 1)}>Unrelated update {revision}</button><div data-revision={revision}><EquipmentProfilePage /></div></>;
}
function unavailable404(): AxiosError {
  return new AxiosError("not found", "ERR_BAD_REQUEST", undefined, undefined, { status: 404, statusText: "Not Found", headers: new AxiosHeaders(), config: { headers: new AxiosHeaders() }, data: { detail: "Equipment was not found" } });
}

beforeEach(() => {
  mockBuildAnalytics.mockClear();
  mockGetEquipment.mockReset().mockResolvedValue([equipment(4), equipment(5)]);
  mockGetEquipmentHistory.mockReset().mockImplementation(async (id: number) => historyFor(id));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Equipment profile", () => {
  it("shows actual metadata, latest persisted sensor values, and timestamped trend charts", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Machine 4" })).toBeInTheDocument();
    expect(screen.getByText("Latest persisted observation")).toBeInTheDocument();
    expect(screen.getByText("Persisted reading #40")).toBeInTheDocument();
    expect(screen.getAllByText("300.2 K")).toHaveLength(2);
    expect(screen.getByRole("img", { name: /Air temperature in K across 1 loaded persisted observations/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Tool wear in min across 1 loaded persisted observations/ })).toBeInTheDocument();
    expect(screen.getByText(/Latest persisted observation; it does not represent live sensor telemetry/)).toBeInTheDocument();
  });

  it("reuses derived equipment analytics across unrelated profile renders", async () => {
    renderPage();
    expect(await screen.findByText("Persisted reading #40")).toBeInTheDocument();
    await waitFor(() => expect(mockBuildAnalytics).toHaveBeenCalled());
    const calculationCount = mockBuildAnalytics.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "Unrelated update 0" }));
    expect(screen.getByRole("button", { name: "Unrelated update 1" })).toBeInTheDocument();
    expect(mockBuildAnalytics).toHaveBeenCalledTimes(calculationCount);
  });

  it("rejects malformed IDs and gives an empty state for equipment with no readings", async () => {
    const invalid = renderPage("/equipment/0");
    expect(await screen.findByText("The requested equipment ID is not a valid positive integer.")).toBeInTheDocument();
    expect(mockGetEquipmentHistory).not.toHaveBeenCalled();
    invalid.unmount();
    mockGetEquipmentHistory.mockResolvedValueOnce(historyFor(4, []));
    renderPage();
    expect(await screen.findByText("No persisted observations")).toBeInTheDocument();
    expect(screen.getByText("No sensor observations to chart")).toBeInTheDocument();
  });

  it("shows not-found for a valid ID rejected by the backend", async () => {
    mockGetEquipmentHistory.mockRejectedValueOnce(unavailable404());
    renderPage("/equipment/999");
    expect(await screen.findByText("No matching equipment record")).toBeInTheDocument();
  });

  it("loads additional readings only on request and updates loaded coverage and chart data", async () => {
    const fullPage = Array.from({ length: 50 }, (_, index) => ({ reading: reading(100 + index, 4, `2026-10-${String(31 - Math.floor(index / 24)).padStart(2, "0")}T${String(index % 24).padStart(2, "0")}:00:00Z`), predictions: [] }));
    mockGetEquipmentHistory.mockResolvedValueOnce(historyFor(4, fullPage)).mockResolvedValueOnce(historyFor(4, [{ reading: reading(50, 4, "2026-10-29T00:00:00Z"), predictions: [] }]));
    renderPage();
    expect(await screen.findByText(/Based on 50 loaded sensor observations and 0 distinct saved prediction records/)).toBeInTheDocument();
    expect(screen.getByText(/Partial history: more readings are available to load/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load 50 older observations" }));
    await waitFor(() => expect(mockGetEquipmentHistory).toHaveBeenLastCalledWith(4, 50, 50));
    expect(await screen.findByText(/Based on 51 loaded sensor observations/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Air temperature in K across 51 loaded persisted observations/ })).toBeInTheDocument();
    fireEvent.click(screen.getByText("View air temperature observations as a table (51)"));
    const airTable = screen.getByRole("table", { name: /Air temperature \(K\) by sensor-reading timestamp/ });
    expect(within(airTable).getByRole("rowheader", { name: "50" })).toBeInTheDocument();
  });

  it("does not show the previous equipment history after switching route IDs", async () => {
    mockGetEquipmentHistory.mockImplementation(async (id: number) => historyFor(id, [{ reading: reading(id * 10, id), predictions: [] }]));
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Machine 4" })).toBeInTheDocument();
    expect(await screen.findByText("Persisted reading #40")).toBeInTheDocument();
    fireEvent.click(screen.getByText("View air temperature observations as a table (1)"));
    expect(within(screen.getByRole("table", { name: /Air temperature/ })).getByRole("rowheader", { name: "40" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch equipment" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Machine 5" })).toBeInTheDocument();
    expect(await screen.findByText("Persisted reading #50")).toBeInTheDocument();
    expect(screen.queryByText("Persisted reading #40")).not.toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: /Air temperature/ })).getByRole("rowheader", { name: "50" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Air temperature/ })).not.toHaveTextContent("40");
    expect(mockGetEquipmentHistory).toHaveBeenLastCalledWith(5, 50, 0);
  });
});
