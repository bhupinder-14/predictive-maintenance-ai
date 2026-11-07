import { ClipboardList } from "lucide-react";
import { EmptyState } from "@/components/feedback/empty-state";
import { Card } from "@/components/ui/card";
import { LatestDriftPanel } from "@/components/overview/LatestDriftPanel";
import { OperationalKpis } from "@/components/overview/OperationalKpis";
import { OverviewSystemStatus } from "@/components/overview/OverviewSystemStatus";
import { PredictionActivity } from "@/components/overview/PredictionActivity";
import { useBackendStatus } from "@/hooks/useBackendStatus";
import { useLatestDriftReport } from "@/hooks/useLatestDriftReport";
import { useOperationalMetrics } from "@/hooks/useOperationalMetrics";
import { PageHeader } from "@/components/layout/PageHeader";

export function OverviewPage() {
  const backendStatus = useBackendStatus();
  const metrics = useOperationalMetrics();
  const drift = useLatestDriftReport();
  const freshness = getOverviewFreshness(metrics, drift);

  return (
    <div className="page-stack overview-page">
      <PageHeader
        eyebrow="COMMAND CENTER"
        title="Operations overview"
        description="Current API readiness, process metrics, prediction outcomes and the latest persisted input-drift report."
        badge={freshness}
      />
      <OverviewSystemStatus state={backendStatus} />
      <OperationalKpis query={metrics} />
      <PredictionActivity query={metrics} />
      <LatestDriftPanel query={drift} />
      <Card className="overview-activity-note">
        <div className="overview-section-heading"><div><p className="panel-eyebrow">HISTORY SCOPE</p><h2>Recent operational activity</h2></div><ClipboardList size={17} className="panel-icon" aria-hidden="true" /></div>
        <EmptyState title="No global activity feed is available" description="The API exposes prediction history per equipment, not as a global recent-events stream. This overview does not synthesize events from aggregate counters." />
      </Card>
      <p className="scope-note overview-scope-note">Anomaly detection and failure classification are separate model outputs. Drift describes input-distribution changes and does not by itself establish reduced model accuracy. Metrics are process-local and reset on API restart.</p>
    </div>
  );
}

export type OverviewFreshness = "LIVE" | "PARTIAL DATA" | "LOADING" | "DATA UNAVAILABLE";

interface OverviewSourceState {
  data: unknown;
  status: "pending" | "success" | "error";
}

export function getOverviewFreshness(
  metrics: OverviewSourceState,
  drift: OverviewSourceState,
): OverviewFreshness {
  const hasMetrics = metrics.data !== undefined;
  const hasDrift = drift.data !== undefined;
  const hasFailure = metrics.status === "error" || drift.status === "error";
  if (hasFailure) return hasMetrics || hasDrift ? "PARTIAL DATA" : "DATA UNAVAILABLE";
  if (metrics.status === "pending" || drift.status === "pending") return "LOADING";
  if (hasMetrics && hasDrift) return "LIVE";
  return "DATA UNAVAILABLE";
}
