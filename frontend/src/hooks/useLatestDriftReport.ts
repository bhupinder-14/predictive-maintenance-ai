import { useQuery } from "@tanstack/react-query";
import { getLatestDriftReport } from "@/api/drift";

export function useLatestDriftReport() {
  return useQuery({
    queryKey: ["overview", "latest-drift-report"],
    queryFn: getLatestDriftReport,
    staleTime: 45_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    retry: false,
  });
}
