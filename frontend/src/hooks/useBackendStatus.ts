import { useQuery } from "@tanstack/react-query";
import { getBackendStatus } from "@/api/health";
import type { ApiConnectionState } from "@/api/types";

export function useBackendStatus(): ApiConnectionState {
  const query = useQuery({
    queryKey: ["backend-status"],
    queryFn: getBackendStatus,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    retry: 0,
  });

  if (query.isPending) return { kind: "checking" };
  if (query.isError || !query.data || query.data.health.kind !== "success") {
    return { kind: "unreachable", error: query.data?.health.kind === "error" ? query.data.health : undefined };
  }

  const health = query.data.health.data;
  const readiness = query.data.readiness;
  if (readiness.kind === "error") return { kind: "readiness-error", health, error: readiness };
  if (readiness.statusCode === 503) return { kind: "not-ready", health, readiness: readiness.data };
  return { kind: "ready", health, readiness: readiness.data };
}
