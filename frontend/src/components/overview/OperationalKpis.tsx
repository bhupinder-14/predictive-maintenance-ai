import { Activity, AlertTriangle, Clock3, RadioTower, Server, Waypoints } from "lucide-react";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingSkeleton } from "@/components/feedback/loading-skeleton";
import { Card } from "@/components/ui/card";
import { formatCount, formatDuration } from "@/api/metrics";
import type { useOperationalMetrics } from "@/hooks/useOperationalMetrics";

type MetricsQuery = ReturnType<typeof useOperationalMetrics>;

export function OperationalKpis({ query }: { query: MetricsQuery }) {

  if (query.isPending) {
    return <section aria-label="Operational metrics loading" className="overview-kpi-grid">{Array.from({ length: 5 }, (_, index) => <LoadingSkeleton key={index} className="overview-kpi-skeleton" />)}</section>;
  }

  if (!query.data) {
    return <ErrorState title="Operational metrics unavailable" description="The metrics service did not return a valid response. Other dashboard sections remain available." onRetry={() => void query.refetch()} />;
  }

  const metrics = query.data;
  const cards = [
    { label: "Requests recorded", value: formatCount(metrics.requests.total), note: "Cumulative since process start", icon: Waypoints },
    { label: "Anomaly predictions", value: formatCount(metrics.predictions.anomaly.total), note: "Isolation Forest · cumulative", icon: RadioTower },
    { label: "Failure classifications", value: formatCount(metrics.predictions.failure.total), note: "Supervised classifier · cumulative", icon: Activity },
    { label: "Failed requests", value: formatCount(metrics.requests.failed), note: "HTTP responses ≥ 400 · cumulative", icon: AlertTriangle },
    { label: "Process uptime", value: formatDuration(metrics.runtime.uptime_seconds), note: "Current API process", icon: Clock3 },
  ];

  return (
    <section className="overview-metrics-section" aria-label="Operational metrics">
      <div className="overview-section-heading overview-metrics-heading">
        <div><p className="panel-eyebrow">CUMULATIVE SINCE PROCESS START</p><h2>Operational metrics</h2></div>
        <span className="overview-freshness">{query.isFetching ? "Refreshing…" : `Updated ${formatUpdatedAt(query.dataUpdatedAt)}`}</span>
      </div>
      {query.isError && <p className="overview-stale-note" role="status">Refresh failed. Showing the last successful metrics snapshot from {formatUpdatedAt(query.dataUpdatedAt)}.</p>}
      <div className="overview-kpi-grid">
        {cards.map(({ label, value, note, icon: Icon }) => (
          <Card className="metric-card overview-kpi-card" key={label}>
            <div className="metric-card-top"><span className="metric-icon"><Icon size={17} aria-hidden="true" /></span></div>
            <p className="metric-label">{label}</p>
            <div className="metric-value-placeholder" aria-label={`${label}: ${value}`}>{value}</div>
            <p className="metric-note">{note}</p>
          </Card>
        ))}
      </div>
      <p className="overview-reset-note"><Server size={13} aria-hidden="true" /> Metrics are held in memory for this API process and reset when it restarts.</p>
    </section>
  );
}

export function formatUpdatedAt(timestamp: number): string {
  if (!timestamp) return "not yet";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(timestamp);
}
