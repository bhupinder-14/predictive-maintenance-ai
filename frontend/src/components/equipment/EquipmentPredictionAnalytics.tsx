import { memo, useMemo } from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { PredictionSummaryRecord } from "@/api/equipment";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/feedback/empty-state";

function versionSummary(versions: Record<string, number>): string {
  const entries = Object.entries(versions).sort(([left], [right]) => left.localeCompare(right));
  return entries.length ? entries.map(([version, count]) => `${version} · ${count}`).join(" / ") : "No saved model versions";
}

function OutputScatter({ predictions, valueKey, title, disclaimer }: {
  predictions: PredictionSummaryRecord[];
  valueKey: "anomaly_score" | "failure_probability";
  title: string;
  disclaimer: string;
}) {
  const points = useMemo(() => predictions.flatMap((prediction) => {
    const value = prediction[valueKey];
    return value === null ? [] : [{ timestampMs: Date.parse(prediction.created_at), timestamp: prediction.created_at, id: prediction.id, value, modelVersion: prediction.model_version }];
  }).sort((left, right) => left.timestampMs - right.timestampMs || left.id.localeCompare(right.id)), [predictions, valueKey]);
  const familyLabel = valueKey === "anomaly_score" ? "Isolation Forest anomaly prediction" : "Random Forest failure classification prediction";
  const axisDescription = valueKey === "anomaly_score"
    ? "Horizontal axis: prediction creation timestamp. Vertical axis: raw Isolation Forest score_samples output; this is not a failure probability."
    : "Horizontal axis: prediction creation timestamp. Vertical axis: uncalibrated class-1 estimator output; this is not a calibrated probability or forecast.";
  return <Card className="prediction-output-card"><div className="sensor-chart-heading"><h3>{title}</h3><span>{points.length} records</span></div><p>{disclaimer}</p>{points.length === 0 ? <EmptyState title="No saved outputs in loaded history" description="Load more persisted readings or return when predictions exist for this equipment." /> : <div className="prediction-output-chart" role="img" aria-label={`${title} for ${points.length} saved prediction records`}><ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{ top: 8, right: 12, bottom: 8, left: 2 }}><CartesianGrid stroke="hsl(var(--line) / .65)" strokeDasharray="3 4" /><XAxis type="number" dataKey="timestampMs" name="Prediction created" domain={["dataMin", "dataMax"]} tickFormatter={(value: number) => new Date(value).toLocaleDateString()} tick={{ fill: "hsl(var(--muted))", fontSize: 9 }} tickLine={false} axisLine={{ stroke: "hsl(var(--line))" }} /><YAxis type="number" dataKey="value" name={title} width={54} tick={{ fill: "hsl(var(--muted))", fontSize: 9 }} tickLine={false} axisLine={false} domain={["auto", "auto"]} /><Tooltip labelFormatter={(value) => `Prediction created: ${new Date(Number(value)).toLocaleString()}`} formatter={(value, _name, item) => [`${Number(value).toLocaleString(undefined, { maximumFractionDigits: 5 })}`, `${title} · ${String(item.payload.modelVersion)}`]} contentStyle={{ background: "hsl(var(--surface))", border: "1px solid hsl(var(--line))", borderRadius: 8, color: "hsl(var(--ink))" }} /><Scatter data={points} dataKey="value" fill="hsl(var(--cyan))" name={title} isAnimationActive={false} /></ScatterChart></ResponsiveContainer></div>}
    <p className="chart-axis-description">{axisDescription} Data are limited to the currently loaded equipment history pages.</p>
    {points.length > 0 && <details className="chart-data-disclosure">
      <summary>View {familyLabel.toLowerCase()} data as a table ({points.length})</summary>
      <div className="chart-data-table-wrap"><table className="chart-data-table">
        <caption>{familyLabel}: {title} by prediction creation timestamp, chronological. Only saved predictions in loaded history are included.</caption>
        <thead><tr><th scope="col">Prediction created</th><th scope="col">Prediction ID</th><th scope="col">{title}</th><th scope="col">Model version</th></tr></thead>
        <tbody>{points.map((point) => <tr key={point.id}>
          <td><time dateTime={point.timestamp}>{new Date(point.timestampMs).toISOString()}</time></td>
          <th scope="row">{point.id}</th>
          <td>{String(point.value)}</td>
          <td>{point.modelVersion}</td>
        </tr>)}</tbody>
      </table></div>
    </details>}
    <small>Each point is one distinct saved prediction ID; horizontal position uses prediction creation time.</small></Card>;
}

export const EquipmentPredictionAnalytics = memo(function EquipmentPredictionAnalytics({ anomalyPredictions, failurePredictions, normalCount, anomalyCount, anomalyVersions, failureVersions }: {
  anomalyPredictions: PredictionSummaryRecord[];
  failurePredictions: PredictionSummaryRecord[];
  normalCount: number;
  anomalyCount: number;
  anomalyVersions: Record<string, number>;
  failureVersions: Record<string, number>;
}) {
  const predictionCount = anomalyPredictions.length + failurePredictions.length;
  const anomalyVersionLabel = useMemo(() => versionSummary(anomalyVersions), [anomalyVersions]);
  const failureVersionLabel = useMemo(() => versionSummary(failureVersions), [failureVersions]);
  return <section className="equipment-analytics-section" aria-labelledby="prediction-analytics-title">
    <div className="equipment-section-heading"><div><p className="panel-eyebrow">PERSISTED MODEL OUTPUTS</p><h2 id="prediction-analytics-title">Prediction analytics</h2><p className="equipment-analytics-coverage">Based on {predictionCount} unique saved prediction records attached to the loaded history.</p></div><span className="equipment-section-caption">Separate model families · loaded history only</span></div>
    <div className="equipment-prediction-grid">
      <Card className="equipment-prediction-card anomaly-analytics"><p className="panel-eyebrow">ISOLATION FOREST</p><h3>Anomaly detection</h3><div className="prediction-count-row"><span><strong>{anomalyPredictions.length}</strong> saved runs</span><span><strong>{normalCount}</strong> normal</span><span><strong>{anomalyCount}</strong> anomaly</span></div><p className="model-version-summary">Model versions: {anomalyVersionLabel}</p><OutputScatter predictions={anomalyPredictions} valueKey="anomaly_score" title="Anomaly score" disclaimer="Isolation Forest score_samples output; this is not a failure probability." />
      </Card>
      <Card className="equipment-prediction-card failure-analytics"><p className="panel-eyebrow">SUPERVISED CLASSIFICATION</p><h3>Failure model outputs</h3><div className="prediction-count-row"><span><strong>{failurePredictions.length}</strong> saved runs</span><span className="prediction-class-note">Historical predicted classes are not persisted.</span></div><p className="model-version-summary">Model versions: {failureVersionLabel}</p><OutputScatter predictions={failurePredictions} valueKey="failure_probability" title="Uncalibrated class-1 estimator output" disclaimer="Stored Random Forest predict_proba output; not calibrated and not a future-failure forecast." />
      </Card>
    </div>
  </section>;
});
