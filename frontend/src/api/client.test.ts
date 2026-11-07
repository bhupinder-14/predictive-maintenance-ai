import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("API base URL configuration", () => {
  it("keeps the /api base for the existing development proxy by default", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const { apiClient } = await import("./client");

    expect(apiClient.defaults.baseURL).toBe("/api");
    expect(apiClient.getUri({ url: "/health" })).toBe("/api/health");
  });

  it("uses the configured production backend origin without a /api prefix", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://predictive-api.example.onrender.com/");
    const { apiClient } = await import("./client");

    expect(apiClient.defaults.baseURL).toBe("https://predictive-api.example.onrender.com");
    expect(apiClient.getUri({ url: "/health" })).toBe(
      "https://predictive-api.example.onrender.com/health",
    );
  });
});
