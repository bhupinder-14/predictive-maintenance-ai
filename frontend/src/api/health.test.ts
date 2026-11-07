import { AxiosError } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { getBackendStatus } from "./health";

afterEach(() => vi.restoreAllMocks());

const healthy = { status: "ready", models: { anomaly: true, failure: true }, database: true };
const unready = { status: "not_ready", models: { anomaly: false, failure: true }, database: true };

function mockProbes(health: unknown, readiness: unknown, healthStatus = 200, readinessStatus = 200) {
  const get = vi.spyOn(apiClient, "get");
  get.mockResolvedValueOnce({ data: health, status: healthStatus } as never);
  get.mockResolvedValueOnce({ data: readiness, status: readinessStatus } as never);
  return get;
}

describe("backend health service", () => {
  it("requests the real liveness and readiness paths and accepts valid 200 responses", async () => {
    const get = mockProbes({ status: "ok" }, healthy);
    const result = await getBackendStatus();

    expect(get).toHaveBeenNthCalledWith(1, "/health", { validateStatus: expect.any(Function) });
    expect(get).toHaveBeenNthCalledWith(2, "/ready", { validateStatus: expect.any(Function) });
    expect(result.health).toEqual({ kind: "success", statusCode: 200, data: { status: "ok" } });
    expect(result.readiness).toEqual({ kind: "success", statusCode: 200, data: healthy });
  });

  it("accepts a valid readiness 503 as a reachable unready response", async () => {
    mockProbes({ status: "ok" }, unready, 200, 503);
    const result = await getBackendStatus();
    expect(result.readiness).toEqual({ kind: "success", statusCode: 503, data: unready });
  });

  it("rejects HTTP 503 when every readiness dependency is available", async () => {
    mockProbes({ status: "ok" }, healthy, 200, 503);
    expect((await getBackendStatus()).readiness).toMatchObject({ kind: "error", reason: "malformed", statusCode: 503 });
  });

  it.each([
    ["times out", new AxiosError("timeout", "ECONNABORTED"), "Readiness check timed out."],
    ["has a network error", new AxiosError("Network Error", "ERR_NETWORK"), "Readiness check could not reach the API."],
  ])("reports readiness network errors when the request %s", async (_label, error, message) => {
    const get = vi.spyOn(apiClient, "get");
    get.mockResolvedValueOnce({ data: { status: "ok" }, status: 200 } as never);
    get.mockRejectedValueOnce(error);
    const result = await getBackendStatus();
    expect(result.readiness).toMatchObject({ kind: "error", reason: "network", message });
  });

  it("reports unexpected readiness HTTP 500 without treating it as not-ready", async () => {
    mockProbes({ status: "ok" }, { detail: "internal" }, 200, 500);
    expect((await getBackendStatus()).readiness).toMatchObject({
      kind: "error", reason: "http", statusCode: 500, message: "Readiness check returned unexpected HTTP 500.",
    });
  });

  it("rejects malformed readiness bodies", async () => {
    mockProbes({ status: "ok" }, { status: "ready", database: true });
    expect((await getBackendStatus()).readiness).toMatchObject({ kind: "error", reason: "malformed", statusCode: 200 });
  });

  it("rejects a readiness body whose status conflicts with its HTTP status", async () => {
    mockProbes({ status: "ok" }, healthy, 200, 503);
    expect((await getBackendStatus()).readiness).toMatchObject({ kind: "error", reason: "malformed" });
  });

  it("does not accept ready responses with missing or false model/database fields", async () => {
    for (const response of [
      { status: "ready", models: { anomaly: true }, database: true },
      { status: "ready", models: { anomaly: true, failure: true }, database: false },
    ]) {
      mockProbes({ status: "ok" }, response);
      expect((await getBackendStatus()).readiness).toMatchObject({ kind: "error", reason: "malformed" });
      vi.restoreAllMocks();
    }
  });

  it("reports malformed health even when readiness succeeds", async () => {
    mockProbes({ status: "degraded" }, healthy);
    expect((await getBackendStatus()).health).toMatchObject({ kind: "error", reason: "malformed" });
  });

  it("keeps health unreachable when health fails even if readiness succeeds", async () => {
    const get = vi.spyOn(apiClient, "get");
    get.mockRejectedValueOnce(new AxiosError("Network Error", "ERR_NETWORK"));
    get.mockResolvedValueOnce({ data: healthy, status: 200 } as never);
    const result = await getBackendStatus();
    expect(result.health).toMatchObject({ kind: "error", reason: "network" });
    expect(result.readiness).toMatchObject({ kind: "success", statusCode: 200 });
  });

  it("does not expose Axios response internals in sanitized HTTP probe errors", async () => {
    const get = vi.spyOn(apiClient, "get");
    get.mockResolvedValueOnce({ data: { status: "ok" }, status: 200 } as never);
    get.mockRejectedValueOnce(new AxiosError("Request failed", "ERR_BAD_RESPONSE", undefined, undefined, {
      status: 500, statusText: "Error", headers: {}, config: {} as never, data: { detail: "private path" },
    }));
    const result = await getBackendStatus();
    expect(result.readiness).toMatchObject({ kind: "error", reason: "http", statusCode: 500 });
    expect(JSON.stringify(result)).not.toContain("private path");
  });
});
