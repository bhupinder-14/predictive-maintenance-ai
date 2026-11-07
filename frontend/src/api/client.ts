import axios from "axios";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const apiClient = axios.create({
  // Keep the same-origin Vite proxy in development unless an explicit API
  // origin is supplied. Production builds can target the standalone FastAPI
  // service directly; its routes do not include the development-only /api.
  baseURL: configuredBaseUrl ? configuredBaseUrl.replace(/\/+$/, "") : "/api",
  timeout: 5_000,
  headers: { Accept: "application/json" },
});
