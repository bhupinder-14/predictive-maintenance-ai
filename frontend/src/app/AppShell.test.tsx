import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { fireEvent, screen, within } from "@testing-library/dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { OverviewPage } from "@/pages/OverviewPage";
import { EquipmentPage } from "@/pages/EquipmentPage";
import { PredictionLabPage } from "@/pages/PredictionLabPage";
import { PredictionHistoryPage } from "@/pages/PredictionHistoryPage";
import { DriftMonitoringPage } from "@/pages/DriftMonitoringPage";
import { SystemHealthPage } from "@/pages/SystemHealthPage";

const { mockGetMetrics, mockGetDrift, mockGetEquipment, mockGetEquipmentHistory, mockPredictAnomaly, mockPredictFailure, mockGetSavedPrediction } = vi.hoisted(() => ({
  mockGetMetrics: vi.fn(),
  mockGetDrift: vi.fn(),
  mockGetEquipment: vi.fn(),
  mockGetEquipmentHistory: vi.fn(),
  mockPredictAnomaly: vi.fn(),
  mockPredictFailure: vi.fn(),
  mockGetSavedPrediction: vi.fn(),
}));

vi.mock("@/api/metrics", () => ({
  getOperationalMetrics: () => mockGetMetrics(),
  formatCount: (value: number) => new Intl.NumberFormat().format(value),
  formatDuration: () => "0m 0s",
}));
vi.mock("@/api/drift", () => ({ getLatestDriftReport: () => mockGetDrift() }));
vi.mock("@/api/equipment", () => ({
  getEquipment: (...args: unknown[]) => mockGetEquipment(...args),
  getEquipmentHistory: (...args: unknown[]) => mockGetEquipmentHistory(...args),
}));
vi.mock("@/api/predictions", () => ({
  predictAnomaly: (...args: unknown[]) => mockPredictAnomaly(...args),
  predictFailure: (...args: unknown[]) => mockPredictFailure(...args),
  getSavedPrediction: (...args: unknown[]) => mockGetSavedPrediction(...args),
  predictionErrorMessage: () => "Prediction request unavailable.",
}));

vi.mock("@/hooks/useBackendStatus", () => ({
  useBackendStatus: () => ({
    kind: "ready",
    health: { status: "ok" },
    readiness: { status: "ready", models: { anomaly: true, failure: true }, database: true },
  }),
}));

const pages = [
  ["/", OverviewPage, "Operations overview"],
  ["/equipment", EquipmentPage, "Equipment"],
  ["/prediction-lab", PredictionLabPage, "Prediction lab"],
  ["/prediction-history", PredictionHistoryPage, "Prediction history"],
  ["/drift", DriftMonitoringPage, "Drift monitoring"],
  ["/system", SystemHealthPage, "System health"],
] as const;

const emptyRequests = { total: 0, successful: 0, failed: 0, status_codes: {}, by_endpoint: {}, duration_ms: { total: 0, average: 0, max: 0 } };
const emptyPredictions = {
  anomaly: { total: 0, normal: 0, anomaly: 0, by_model_version: {} },
  failure: { total: 0, predicted_class_0: 0, predicted_class_1: 0, by_model_version: {} },
  errors: { total: 0, by_model: {} },
};
const emptyMetrics = {
  requests: emptyRequests,
  predictions: emptyPredictions,
  runtime: { uptime_seconds: 0, metrics_storage: "in_memory_process_local" as const },
  availability: { models: {
    anomaly: { available: true, status: "available", model_version: "anomaly_v1" },
    failure: { available: true, status: "available", model_version: "failure_v1" },
  }, database_available: true },
  rolling_window: { window_seconds: 300, requests: emptyRequests, predictions: emptyPredictions },
};

beforeEach(() => {
  mockGetMetrics.mockReset().mockResolvedValue(emptyMetrics);
  mockGetDrift.mockReset().mockResolvedValue(null);
  mockGetEquipment.mockReset().mockResolvedValue([]);
  mockGetEquipmentHistory.mockReset().mockResolvedValue({ equipment: { id: 1, name: "Test", equipment_type: "M", location: null, created_at: "2026-10-30T00:00:00Z" }, items: [] });
  mockPredictAnomaly.mockReset();
  mockPredictFailure.mockReset();
  mockGetSavedPrediction.mockReset();
});

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([
    {
      path: "/",
      element: <AppShell />,
      children: pages.map(([route, Page]) => ({
        path: route === "/" ? undefined : route.slice(1),
        index: route === "/",
        element: <Page />,
      })),
    },
  ], {
    initialEntries: [path],
    future: { v7_relativeSplatPath: true },
  });
  return render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("M6.1 application shell", () => {
  it.each(pages)("renders route %s without fabricated data", async (path, _Page, heading) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { name: heading, level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
  });

  it("renders the overview call to action without nested interactive elements", () => {
    const { container } = renderAt("/");
    expect(container.querySelector("a button")).toBeNull();
    expect(container.querySelector("button a")).toBeNull();
  });

  it("provides a keyboard skip link and keeps collapsed navigation links named", () => {
    renderAt("/");
    const skipLink = screen.getByRole("link", { name: "Skip to main content" });
    expect(skipLink).toHaveAttribute("href", "#main-content");
    skipLink.focus();
    expect(skipLink).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByRole("link", { name: "Equipment" })).toBeInTheDocument();
  });

  it("opens an accessible mobile dialog and moves focus inside", () => {
    renderAt("/");
    const trigger = screen.getByRole("button", { name: "Open navigation" });
    expect(trigger).toHaveAttribute("aria-controls", "mobile-navigation");
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Mobile navigation" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveFocus();
  });

  it("traps keyboard focus in the drawer and restores it after Escape", () => {
    renderAt("/");
    const trigger = screen.getByRole("button", { name: "Open navigation" });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Mobile navigation" });
    const close = within(dialog).getByRole("button", { name: "Close navigation" });
    const firstLink = within(dialog).getAllByRole("link")[0];
    expect(firstLink).toBeDefined();
    firstLink?.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(close).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(firstLink).toHaveFocus();

    trigger.focus();
    expect(close).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(document.getElementById("mobile-navigation")).not.toHaveAttribute("open");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("closes the mobile drawer when a navigation route is selected", async () => {
    renderAt("/");
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    const dialog = screen.getByRole("dialog", { name: "Mobile navigation" });
    fireEvent.click(within(dialog).getByRole("link", { name: "Equipment" }));
    expect(document.getElementById("mobile-navigation")).not.toHaveAttribute("open");
    expect(await screen.findByRole("heading", { name: "Equipment" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open navigation" })).toHaveFocus();
  });

  it("exposes desktop sidebar collapse controls accessibly", () => {
    renderAt("/");
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
  });
});
