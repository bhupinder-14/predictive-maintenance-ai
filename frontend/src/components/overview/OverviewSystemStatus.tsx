import { Activity, Database, HeartPulse, ShieldCheck } from "lucide-react";
import type { ApiConnectionState } from "@/api/types";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";

export function OverviewSystemStatus({ state }: { state: ApiConnectionState }) {
  const readyData = state.kind === "ready" || state.kind === "not-ready" ? state.readiness : null;
  const healthTone = state.kind === "ready" || state.kind === "not-ready" || state.kind === "readiness-error" ? "good" : state.kind === "unreachable" ? "danger" : "neutral";
  const readinessLabel = state.kind === "checking" ? "Checking" : state.kind === "ready" ? "Ready" : state.kind === "not-ready" ? "Not ready" : state.kind === "readiness-error" ? "Probe error" : "Unreachable";
  const readinessTone = state.kind === "ready" ? "good" : state.kind === "not-ready" ? "warn" : state.kind === "readiness-error" || state.kind === "unreachable" ? "danger" : "neutral";
  const modelTone = (available: boolean | undefined) => available === true ? "good" : available === false ? "danger" : "neutral";

  return (
    <Card className="overview-status-panel" aria-label="System status">
      <div className="overview-section-heading">
        <div><p className="panel-eyebrow">LIVE SERVICE CHECK</p><h2>System status</h2></div>
        <Activity size={17} className="panel-icon" aria-hidden="true" />
      </div>
      <div className="overview-status-grid">
        <StatusCell icon={HeartPulse} label="API liveness" value={state.kind === "checking" ? "Checking" : healthTone === "good" ? "Reachable" : healthTone === "danger" ? "Unreachable" : "Unknown"} tone={healthTone} />
        <StatusCell icon={ShieldCheck} label="Overall readiness" value={readinessLabel} tone={readinessTone} />
        <StatusCell icon={Activity} label="Anomaly model" value={readyData ? readyData.models.anomaly ? "Available" : "Unavailable" : "Unknown"} tone={modelTone(readyData?.models.anomaly)} />
        <StatusCell icon={Activity} label="Failure model" value={readyData ? readyData.models.failure ? "Available" : "Unavailable" : "Unknown"} tone={modelTone(readyData?.models.failure)} />
        <StatusCell icon={Database} label="Database" value={readyData ? readyData.database ? "Connected" : "Unavailable" : "Unknown"} tone={modelTone(readyData?.database)} />
      </div>
      {state.kind === "readiness-error" && <p className="overview-status-note" role="status">Readiness could not be confirmed: {state.error.message}</p>}
      {state.kind === "unreachable" && <p className="overview-status-note" role="status">The health endpoint could not be confirmed. {state.error?.message ?? "Check API connectivity."}</p>}
    </Card>
  );
}

function StatusCell({ icon: Icon, label, value, tone }: {
  icon: typeof Activity;
  label: string;
  value: string;
  tone: "good" | "warn" | "danger" | "neutral";
}) {
  return (
    <div className="overview-status-cell">
      <span className="overview-status-icon"><Icon size={15} aria-hidden="true" /></span>
      <span className="overview-status-label">{label}</span>
      <StatusBadge label={value} tone={tone} />
    </div>
  );
}
