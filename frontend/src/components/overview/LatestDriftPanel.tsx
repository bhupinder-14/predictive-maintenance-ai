import { Activity, ChartNoAxesCombined, FileSearch } from "lucide-react";
import { formatCount } from "@/api/metrics";
import type { LatestDriftReport } from "@/api/drift";
import { ErrorState } from "@/components/feedback/error-state";
import { EmptyState } from "@/components/feedback/empty-state";
import { LoadingSkeleton } from "@/components/feedback/loading-skeleton";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatUpdatedAt } from "./OperationalKpis";
import type { useLatestDriftReport } from "@/hooks/useLatestDriftReport";

type DriftQuery = ReturnType<typeof useLatestDriftReport>;

export function LatestDriftPanel({ query }: { query: DriftQuery }) {
  if (query.isPending) {
    return <Card className="overview-drift-panel"><PanelHeading /><div className="overview-drift-skeletons"><LoadingSkeleton /><LoadingSkeleton /><LoadingSkeleton /></div></Card>;
  }
  if (!query.data && query.isError) {
    return <Card className="overview-drift-panel"><PanelHeading /><ErrorState title="Latest drift report unavailable" description="The drift service could not return a valid report. Operational metrics remain available." onRetry={() => void query.refetch()} /></Card>;
  }
  if (query.data === null) {
    return <Card className="overview-drift-panel"><PanelHeading /><EmptyState title="No drift report has been generated yet." description="This endpoint returns the latest saved report only. No historical drift trend is available." icon={<FileSearch size={19} aria-hidden="true" />} /></Card>;
  }
  if (!query.data) return null;

  const report = query.data;
  const driftedCount = report.features.filter((feature) => feature.drift_detected === true).length;
  const overall = statusDetails(report.overall_status);

  return (
    <Card className="overview-drift-panel">
      <div className="overview-drift-header">
        <PanelHeading />
        <StatusBadge label={overall.label} tone={overall.tone} />
      </div>
      {query.isError && <p className="overview-stale-note" role="status">Refresh failed. Showing the last successful drift report from {formatUpdatedAt(query.dataUpdatedAt)}.</p>}
      <div className="overview-drift-summary">
        <div><span>REPORT</span><strong>#{formatCount(report.report_id)}</strong><small>{formatTimestamp(report.generated_at)}</small></div>
        <div><span>REFERENCE SAMPLE</span><strong>{formatCount(report.reference_sample_size)}</strong><small>{report.reference_version}</small></div>
        <div><span>CURRENT BATCH</span><strong>{formatCount(report.current_sample_size)}</strong><small>Minimum {formatCount(report.minimum_sample_size)}</small></div>
        <div><span>FEATURES FLAGGED</span><strong>{formatCount(driftedCount)} / {formatCount(report.features.length)}</strong><small>{report.overall_status === "insufficient_data" ? "Batch below required sample size" : "Per-feature results below"}</small></div>
      </div>
      <div className="overview-drift-feature-heading"><div><p className="panel-eyebrow">FEATURE RESULTS</p><h3>Input distribution checks</h3></div><span className="overview-freshness">{query.isFetching ? "Refreshing…" : `Updated ${formatUpdatedAt(query.dataUpdatedAt)}`}</span></div>
      <div className="overview-drift-feature-list" role="list" aria-label="Per-feature drift results">
        {report.features.map((feature) => {
          const result = feature.drift_detected === null ? { label: "Insufficient data", tone: "neutral" as const } : feature.drift_detected ? { label: "Drift detected", tone: "warn" as const } : { label: "No drift", tone: "good" as const };
          return (
            <div className="overview-drift-feature" role="listitem" key={feature.feature_name}>
              <div className="overview-feature-name"><strong>{feature.feature_name}</strong><small>{feature.method === "kolmogorov_smirnov_two_sample" ? "Two-sample KS" : "Total variation distance"}</small></div>
              <div className="overview-feature-stat"><span>{feature.method === "kolmogorov_smirnov_two_sample" ? "KS statistic" : "Distance"}</span><strong>{formatOptional(feature.statistic)}</strong></div>
              <div className="overview-feature-threshold"><span>{feature.threshold_kind === "p_value_significance_level" ? "p-value threshold" : "Distance threshold"}</span><strong>{formatOptional(feature.threshold)}</strong>{feature.p_value !== null && <small>p = {formatOptional(feature.p_value)}</small>}</div>
              <StatusBadge label={result.label} tone={result.tone} />
            </div>
          );
        })}
      </div>
      <p className="overview-drift-interpretation"><Activity size={13} aria-hidden="true" /> {report.interpretation}</p>
    </Card>
  );
}

function PanelHeading() {
  return (
    <div className="overview-section-heading overview-drift-title">
      <div><p className="panel-eyebrow">LATEST PERSISTED REPORT</p><h2>Drift monitoring</h2></div>
      <ChartNoAxesCombined size={17} className="panel-icon" aria-hidden="true" />
    </div>
  );
}

function statusDetails(status: LatestDriftReport["overall_status"]) {
  if (status === "drift_detected") return { label: "Input drift detected", tone: "warn" as const };
  if (status === "insufficient_data") return { label: "Insufficient data", tone: "neutral" as const };
  return { label: "No drift detected", tone: "good" as const };
}

function formatOptional(value: number | null): string {
  return value === null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
