import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { screen } from "@testing-library/dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useBackendStatus } from "./useBackendStatus";

const { mockGetBackendStatus } = vi.hoisted(() => ({ mockGetBackendStatus: vi.fn() }));
vi.mock("@/api/health", () => ({ getBackendStatus: () => mockGetBackendStatus() }));

function StatusProbe() {
  const status = useBackendStatus();
  return <div>{status.kind}</div>;
}

function renderStatus() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><StatusProbe /></QueryClientProvider>);
}

const healthSuccess = { kind: "success", statusCode: 200, data: { status: "ok" } } as const;
const readySuccess = { kind: "success", statusCode: 200, data: { status: "ready", models: { anomaly: true, failure: true }, database: true } } as const;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("backend connection state", () => {
  it("shows checking before the first probe completes", () => {
    mockGetBackendStatus.mockReturnValue(new Promise(() => undefined));
    renderStatus();
    expect(screen.getByText("checking")).toBeInTheDocument();
  });

  it("reports ready only for healthy liveness and complete readiness", async () => {
    mockGetBackendStatus.mockResolvedValue({ health: healthSuccess, readiness: readySuccess });
    renderStatus();
    expect(await screen.findByText("ready")).toBeInTheDocument();
  });

  it("distinguishes a valid reachable but unready response", async () => {
    mockGetBackendStatus.mockResolvedValue({
      health: healthSuccess,
      readiness: { kind: "success", statusCode: 503, data: { status: "not_ready", models: { anomaly: false, failure: true }, database: true } },
    });
    renderStatus();
    expect(await screen.findByText("not-ready")).toBeInTheDocument();
  });

  it("keeps a contradictory 503 dependency snapshot in the readiness-error state", async () => {
    mockGetBackendStatus.mockResolvedValue({
      health: healthSuccess,
      readiness: { kind: "error", reason: "malformed", statusCode: 503, message: "Readiness check returned an invalid response." },
    });
    renderStatus();
    expect(await screen.findByText("readiness-error")).toBeInTheDocument();
  });

  it.each([
    ["network", "Readiness check could not reach the API."],
    ["http", "Readiness check returned unexpected HTTP 500."],
    ["malformed", "Readiness check returned an invalid response."],
  ] as const)("keeps readiness %s failures distinct from not-ready", async (reason, message) => {
    mockGetBackendStatus.mockResolvedValue({
      health: healthSuccess,
      readiness: { kind: "error", reason, message, ...(reason === "http" ? { statusCode: 500 } : {}) },
    });
    renderStatus();
    expect(await screen.findByText("readiness-error")).toBeInTheDocument();
  });

  it("reports unreachable when liveness fails even if readiness succeeds", async () => {
    mockGetBackendStatus.mockResolvedValue({
      health: { kind: "error", reason: "network", message: "Health check could not reach the API." },
      readiness: readySuccess,
    });
    renderStatus();
    expect(await screen.findByText("unreachable")).toBeInTheDocument();
  });
});
