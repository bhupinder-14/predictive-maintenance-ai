export interface HealthResponse {
  status: "ok";
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  models: Record<string, boolean>;
  database: boolean;
}

export interface ProbeFailure {
  kind: "error";
  reason: "network" | "http" | "malformed";
  statusCode?: number;
  message: string;
}

export type ApiConnectionState =
  | { kind: "checking" }
  | { kind: "ready"; health: HealthResponse; readiness: ReadinessResponse }
  | { kind: "not-ready"; health: HealthResponse; readiness: ReadinessResponse }
  | { kind: "readiness-error"; health: HealthResponse; error: ProbeFailure }
  | { kind: "unreachable"; error?: ProbeFailure };
