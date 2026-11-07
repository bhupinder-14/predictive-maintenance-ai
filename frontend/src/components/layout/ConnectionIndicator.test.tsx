import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConnectionIndicator } from "./ConnectionIndicator";

const { mockState } = vi.hoisted(() => ({ mockState: vi.fn() }));
vi.mock("@/hooks/useBackendStatus", () => ({ useBackendStatus: () => mockState() }));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ConnectionIndicator", () => {
  it.each([
    [{ kind: "checking" }, "Checking API"],
    [{ kind: "ready", health: { status: "ok" }, readiness: { status: "ready", models: { anomaly: true, failure: true }, database: true } }, "System operational"],
    [{ kind: "not-ready", health: { status: "ok" }, readiness: { status: "not_ready", models: { anomaly: false, failure: true }, database: true } }, "API reachable · not ready"],
    [{ kind: "readiness-error", health: { status: "ok" }, error: { kind: "error", reason: "http", statusCode: 500, message: "Readiness check returned HTTP 500." } }, "Readiness check failed"],
    [{ kind: "unreachable", error: { kind: "error", reason: "network", message: "Health check could not reach the API." } }, "API unreachable"],
  ] as const)("renders the %s state distinctly", (state, label) => {
    mockState.mockReturnValue(state);
    render(<ConnectionIndicator />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("exposes the sanitized readiness failure reason as a tooltip", () => {
    mockState.mockReturnValue({ kind: "readiness-error", health: { status: "ok" }, error: { kind: "error", reason: "http", statusCode: 500, message: "Readiness check returned unexpected HTTP 500." } });
    render(<ConnectionIndicator />);
    expect(screen.getByText("Readiness check failed")).toHaveAttribute("title", "Readiness check returned unexpected HTTP 500.");
  });
});
