import { lazy, Suspense } from "react";
import { Activity, RadioTower } from "lucide-react";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingSkeleton } from "@/components/feedback/loading-skeleton";
import { Card } from "@/components/ui/card";
import { formatCount } from "@/api/metrics";
import type { useOperationalMetrics } from "@/hooks/useOperationalMetrics";

const PredictionOutcomeChart = lazy(async () => {
  const module = await import("./PredictionOutcomeChart");
  return { default: module.PredictionOutcomeChart };
});

type MetricsQuery = ReturnType<typeof useOperationalMetrics>;

export function PredictionActivity({ query }: { query: MetricsQuery }) {
  if (query.isPending) {
    return <section className="overview-activity-grid" aria-label="Prediction activity loading"><LoadingSkeleton className="overview-chart-skeleton" /><LoadingSkeleton className="overview-chart-skeleton" /></section>;
  }
  if (!query.data) {
    return <ErrorState title="Prediction activity unavailable" description="Rolling prediction counts were not returned by the metrics endpoint." onRetry={() => void query.refetch()} />;
  }

  const { anomaly, failure } = query.data.rolling_window.predictions;
  const windowLabel = formatWindow(query.data.rolling_window.window_seconds);
  return (
    <section className="overview-activity-section" aria-label="Prediction activity">
      <div className="overview-section-heading"><div><p className="panel-eyebrow">ROLLING WINDOW · {windowLabel.toUpperCase()}</p><h2>Prediction activity</h2></div><span className="overview-freshness">Refreshed with metrics</span></div>
      {query.isError && <p className="overview-stale-note" role="status">Refresh failed. The charts show the last successful rolling-window snapshot.</p>}
      <div className="overview-activity-grid">
        <ActivityChart
          title="Anomaly detection"
          description="Isolation Forest outcomes · not machine-failure labels"
          icon={RadioTower}
          total={anomaly.total}
          windowLabel={windowLabel}
          data={[{ label: "Normal", count: anomaly.normal, color: "#2bdc91" }, { label: "Anomaly", count: anomaly.anomaly, color: "#f6b44b" }]}
          emptyTitle="No anomaly predictions in this window"
        />
        <ActivityChart
          title="Failure classification"
          description="Supervised model classes · separate from anomaly detection"
          icon={Activity}
          total={failure.total}
          windowLabel={windowLabel}
          data={[{ label: "Class 0", count: failure.predicted_class_0, color: "#58c5ff" }, { label: "Class 1", count: failure.predicted_class_1, color: "#ff646e" }]}
          emptyTitle="No failure classifications in this window"
        />
      </div>
    </section>
  );
}

function ActivityChart({
  title, description, icon: Icon, total, windowLabel, data, emptyTitle,
}: {
  title: string;
  description: string;
  icon: typeof Activity;
  total: number;
  windowLabel: string;
  data: Array<{ label: string; count: number; color: string }>;
  emptyTitle: string;
}) {
  return (
    <Card className="overview-activity-card">
      <div className="overview-section-heading activity-heading">
        <div className="activity-title"><span className="overview-status-icon"><Icon size={15} aria-hidden="true" /></span><div><h3>{title}</h3><p>{description}</p></div></div>
        <span className="activity-total"><strong>{formatCount(total)}</strong><small>in {windowLabel}</small></span>
      </div>
      {total === 0 ? <EmptyState title={emptyTitle} description="The rolling count is zero; no synthetic events are shown." /> : (
        <Suspense fallback={<LoadingSkeleton className="overview-chart-skeleton" />}>
          <PredictionOutcomeChart title={title} windowLabel={windowLabel} data={data} />
        </Suspense>
      )}
      <ul className="sr-only">{data.map(({ label, count }) => <li key={label}>{label}: {formatCount(count)}</li>)}</ul>
    </Card>
  );
}

export function formatWindow(seconds: number): string {
  if (seconds % 60 === 0) return `${seconds / 60} min`;
  return `${seconds} sec`;
}
