import { Activity, AlertTriangle, Clock3, Database, HeartPulse, Server, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import type { ApiConnectionState } from "@/api/types";
import { formatCount, formatDuration } from "@/api/metrics";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingSkeleton } from "@/components/feedback/loading-skeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { useBackendStatus } from "@/hooks/useBackendStatus";
import { useOperationalMetrics } from "@/hooks/useOperationalMetrics";

type Tone = "good" | "warn" | "danger" | "neutral";

export function SystemHealthPage() {
  const state = useBackendStatus();
  const metrics = useOperationalMetrics();
  const healthReachable = state.kind === "ready" || state.kind === "not-ready" || state.kind === "readiness-error";
  const readiness = state.kind === "ready" || state.kind === "not-ready" ? state.readiness : null;
  const metricsAvailable = Boolean(metrics.data);

  return (
    <div className="page-stack system-health-page">
      <PageHeader eyebrow="SERVICE OBSERVABILITY" title="System health" description="Shared API liveness and readiness probes alongside process-local operational metrics." />
      <div className="health-summary-grid">
        <HealthSummary icon={HeartPulse} title="Application liveness" value={state.kind === "checking" ? "Checking" : healthReachable ? "Reachable" : "Unreachable"} tone={healthReachable ? "good" : state.kind === "unreachable" ? "danger" : "neutral"} />
        <HealthSummary icon={ShieldCheck} title="Service readiness" value={readinessLabel(state)} tone={readinessTone(state)} />
        <HealthSummary icon={Activity} title="Operational metrics" value={metrics.isPending ? "Loading" : metricsAvailable ? "Available" : "Unavailable"} tone={metricsAvailable ? "good" : metrics.isError ? "danger" : "neutral"} />
      </div>

      <Card className="readiness-card">
        <div className="panel-heading"><div><p className="panel-eyebrow">CURRENT PROBE RESULTS</p><h2>Backend connectivity</h2></div><Activity size={17} className="panel-icon" aria-hidden="true" /></div>
        {state.kind === "checking" ? <div className="probe-skeletons" role="status" aria-label="Checking backend health"><LoadingSkeleton /><LoadingSkeleton /><LoadingSkeleton /></div> : (
          <div className="probe-list">
            <ProbeRow label="GET /api/health · liveness" value={state.kind === "unreachable" ? "Unreachable" : "Reachable"} tone={healthReachable ? "good" : "danger"} />
            <ProbeRow label="GET /api/ready · readiness" value={readinessLabel(state)} tone={readinessTone(state)} />
            {state.kind === "unreachable" ? <ErrorState title="API liveness could not be confirmed" description={state.error?.message ?? "The health request did not return a valid response. Dependency availability is unknown."} />
              : state.kind === "readiness-error" ? <ErrorState title="Readiness could not be confirmed" description={state.error.message} />
                : <div className="probe-details">
                  <Dependency label="ANOMALY MODEL" value={readiness?.models.anomaly === true ? "Available" : readiness?.models.anomaly === false ? "Unavailable" : "Unknown"} />
                  <Dependency label="FAILURE MODEL" value={readiness?.models.failure === true ? "Available" : readiness?.models.failure === false ? "Unavailable" : "Unknown"} />
                  <Dependency label="DATABASE" value={readiness?.database === true ? "Connected" : readiness?.database === false ? "Unavailable" : "Unknown"} />
                </div>}
          </div>
        )}
        <p className="scope-note system-health-probe-note">Liveness only confirms that the API process can respond. Readiness also checks that both model artifacts are loaded and the database answers a connection probe.</p>
      </Card>

      <OperationalMetricsPanel query={metrics} />
    </div>
  );
}

function OperationalMetricsPanel({ query }: { query: ReturnType<typeof useOperationalMetrics> }) {
  if (query.isPending) {
    return <section className="system-metrics-section" aria-label="Operational metrics loading"><div className="system-metrics-grid">{Array.from({ length: 5 }, (_, index) => <LoadingSkeleton key={index} className="system-metric-skeleton" />)}</div></section>;
  }
  if (!query.data) {
    return <section className="system-metrics-section"><div className="system-section-heading"><div><p className="panel-eyebrow">PROCESS-LOCAL TELEMETRY</p><h2>Operational metrics</h2></div><StatusBadge label="Unavailable" tone="danger" /></div><ErrorState title="Operational metrics unavailable" description="The metrics endpoint did not return a valid response. Liveness and readiness remain available independently." onRetry={() => void query.refetch()} /></section>;
  }

  const data = query.data;
  const cards = [
    { label: "Requests recorded", value: formatCount(data.requests.total), note: "Cumulative since process start" },
    { label: "Anomaly predictions", value: formatCount(data.predictions.anomaly.total), note: "Isolation Forest · cumulative" },
    { label: "Failure classifications", value: formatCount(data.predictions.failure.total), note: "Supervised model · cumulative" },
    { label: "Failed requests", value: formatCount(data.requests.failed), note: "HTTP responses ≥ 400 · cumulative" },
    { label: "Process uptime", value: formatDuration(data.runtime.uptime_seconds), note: "Current API process" },
  ];
  const rolling = data.rolling_window;

  return (
    <section className="system-metrics-section" aria-label="Operational metrics">
      <div className="system-section-heading"><div><p className="panel-eyebrow">PROCESS-LOCAL TELEMETRY</p><h2>Operational metrics</h2></div><span className="system-metrics-updated">{query.isFetching ? "Refreshing…" : `Updated ${formatUpdatedAt(query.dataUpdatedAt)}`}</span></div>
      {query.isError && <p className="overview-stale-note" role="status">Metrics refresh failed. Showing the last successful snapshot from {formatUpdatedAt(query.dataUpdatedAt)}.</p>}
      <div className="system-metrics-grid">
        {cards.map(({ label, value, note }) => <Card className="system-metric-card" key={label}><p>{label}</p><strong aria-label={`${label}: ${value}`}>{value}</strong><small>{note}</small></Card>)}
      </div>
      <Card className="system-availability-card">
        <div className="system-section-heading"><div><p className="panel-eyebrow">CURRENT METRICS SNAPSHOT</p><h3>Loaded components</h3></div></div>
        <div className="system-availability-grid">
          <Availability label="Anomaly model" availability={data.availability.models.anomaly.available} status={data.availability.models.anomaly.status} version={data.availability.models.anomaly.model_version} />
          <Availability label="Failure model" availability={data.availability.models.failure.available} status={data.availability.models.failure.status} version={data.availability.models.failure.model_version} />
          <Availability label="Database" availability={data.availability.database_available} status={data.availability.database_available === null ? "unknown" : data.availability.database_available ? "connected" : "unavailable"} />
        </div>
      </Card>
      <Card className="system-rolling-card">
        <div className="system-section-heading"><div><p className="panel-eyebrow">RECENT PROCESS ACTIVITY</p><h3>Rolling window · {formatWindow(rolling.window_seconds)}</h3></div></div>
        <div className="system-rolling-grid">
          <RollingValue label="Requests" value={rolling.requests.total} note={`${formatCount(rolling.requests.failed)} failed`} icon={<Server size={15} aria-hidden="true" />} />
          <RollingValue label="Anomaly detections" value={rolling.predictions.anomaly.total} note={`${formatCount(rolling.predictions.anomaly.anomaly)} anomalous · separate model`} icon={<AlertTriangle size={15} aria-hidden="true" />} />
          <RollingValue label="Failure classifications" value={rolling.predictions.failure.total} note={`${formatCount(rolling.predictions.failure.predicted_class_1)} class 1 · not actual failures`} icon={<Activity size={15} aria-hidden="true" />} />
          <RollingValue label="Prediction errors" value={rolling.predictions.errors.total} note="Anomaly and failure requests" icon={<Database size={15} aria-hidden="true" />} />
        </div>
      </Card>
      <p className="scope-note system-health-reset-note"><Clock3 size={13} aria-hidden="true" /> These counters are stored in memory for this API process and reset when it restarts. They are not lifetime factory totals.</p>
    </section>
  );
}

function Availability({ label, availability, status, version }: { label: string; availability: boolean | null; status: string; version?: string | null }) {
  const tone: Tone = availability === true ? "good" : availability === false ? "danger" : "neutral";
  const value = availability === true ? "Available" : availability === false ? "Unavailable" : "Unknown";
  return <div className="system-availability-item"><span>{label}</span><StatusBadge label={value} tone={tone} /><small>{status}{version ? ` · ${version}` : ""}</small></div>;
}

function RollingValue({ label, value, note, icon }: { label: string; value: number; note: string; icon: ReactNode }) {
  return <div className="system-rolling-value"><span>{icon}{label}</span><strong>{formatCount(value)}</strong><small>{note}</small></div>;
}

function Dependency({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function readinessLabel(state: ApiConnectionState): string {
  if (state.kind === "checking") return "Checking";
  if (state.kind === "ready") return "Ready";
  if (state.kind === "not-ready") return "Reachable, not ready";
  if (state.kind === "readiness-error") return "Probe failed";
  return "Unknown";
}

function readinessTone(state: ApiConnectionState): Tone {
  if (state.kind === "ready") return "good";
  if (state.kind === "not-ready") return "warn";
  if (state.kind === "readiness-error" || state.kind === "unreachable") return "danger";
  return "neutral";
}

function HealthSummary({ icon: Icon, title, value, tone }: { icon: typeof Activity; title: string; value: string; tone: Tone }) {
  return <Card className="health-summary"><span className="health-summary-icon"><Icon size={17} aria-hidden="true" /></span><p>{title}</p><StatusBadge label={value} tone={tone} /></Card>;
}

function ProbeRow({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return <div className="probe-row"><span className="probe-endpoint">{label}</span><StatusBadge label={value} tone={tone} /></div>;
}

function formatUpdatedAt(timestamp: number): string {
  if (!timestamp) return "not yet";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(timestamp);
}

function formatWindow(seconds: number): string {
  if (seconds % 60 === 0) return `${seconds / 60} min`;
  return `${seconds} sec`;
}
