import { useQuery } from "@tanstack/react-query";
import { getOperationalMetrics } from "@/api/metrics";

export function useOperationalMetrics() {
  return useQuery({
    queryKey: ["overview", "operational-metrics"],
    queryFn: getOperationalMetrics,
    staleTime: 20_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: false,
  });
}
