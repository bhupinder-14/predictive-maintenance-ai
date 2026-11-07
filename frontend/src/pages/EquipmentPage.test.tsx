import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EquipmentPage } from "./EquipmentPage";

const { mockGetEquipment } = vi.hoisted(() => ({ mockGetEquipment: vi.fn() }));
vi.mock("@/api/equipment", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/equipment")>();
  return { ...actual, getEquipment: (...args: unknown[]) => mockGetEquipment(...args) };
});

const record = (id: number, name = `Machine ${id}`) => ({ id, name, equipment_type: "M", location: id % 2 ? "Line A" : null, created_at: "2026-10-31T10:00:00Z" });
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/equipment"]}><Routes><Route path="/equipment" element={<EquipmentPage />} /><Route path="/equipment/:equipmentId" element={<p>Equipment profile route</p>} /></Routes></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => mockGetEquipment.mockReset().mockResolvedValue([record(1), record(2, "Press Two")]));
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Equipment explorer", () => {
  it("shows real equipment metadata and navigates to a selected profile", async () => {
    renderPage();
    expect((await screen.findAllByText("Machine 1")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Line A").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("link", { name: "Open Machine 1 profile" }));
    expect(await screen.findByText("Equipment profile route")).toBeInTheDocument();
  });

  it("searches loaded records only and loads supported subsequent pages", async () => {
    const first = Array.from({ length: 100 }, (_, index) => record(index + 1));
    mockGetEquipment.mockResolvedValueOnce(first).mockResolvedValueOnce([record(101, "Later Press")]);
    renderPage();
    await screen.findAllByText("Machine 1");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "later" } });
    expect(screen.getByText("No loaded records match this search")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more equipment" }));
    expect((await screen.findAllByText("Later Press")).length).toBeGreaterThan(0);
    await waitFor(() => expect(mockGetEquipment).toHaveBeenLastCalledWith(100, 100));
  });

  it("renders backend empty and retryable error states", async () => {
    mockGetEquipment.mockResolvedValueOnce([]);
    const { unmount } = renderPage();
    expect(await screen.findByText("No equipment records available")).toBeInTheDocument();
    unmount();
    mockGetEquipment.mockClear();
    mockGetEquipment.mockRejectedValueOnce(new Error("offline"));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(mockGetEquipment).toHaveBeenCalledTimes(2);
  });

  it("renders API-provided HTML-like names and locations as inert text", async () => {
    const htmlName = '<img src=x onerror="alert(1)"> Press';
    const htmlLocation = '<script>alert("x")</script>';
    mockGetEquipment.mockResolvedValueOnce([{ ...record(22, htmlName), location: htmlLocation }]);
    const { container } = renderPage();

    expect(await screen.findAllByText(htmlName)).not.toHaveLength(0);
    expect(screen.getAllByText(htmlLocation)).not.toHaveLength(0);
    expect(container.querySelector("img, script")).toBeNull();
  });
});
