import { memo, useMemo } from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { SensorReadingRecord } from "@/api/equipment";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/feedback/empty-state";

const sensorSeries = [
  { key: "Air temperature [K]", label: "Air temperature", unit: "K" },
  { key: "Process temperature [K]", label: "Process temperature", unit: "K" },
  { key: "Rotational speed [rpm]", label: "Rotational speed", unit: "rpm" },
  { key: "Torque [Nm]", label: "Torque", unit: "Nm" },
  { key: "Tool wear [min]", label: "Tool wear", unit: "min" },
] as const;

export const SensorTrendCharts = memo(function SensorTrendCharts({ readings }: { readings: SensorReadingRecord[] }) {
  const chartSeries = useMemo(() => sensorSeries.map((series) => ({
    series,
    points: readings.map((reading) => ({
      timestampMs: Date.parse(reading.timestamp),
      timestamp: reading.timestamp,
      readingId: reading.id,
      value: reading[series.key],
    })).sort((left, right) => left.timestampMs - right.timestampMs || left.readingId - right.readingId),
  })), [readings]);

  return <section className="equipment-analytics-section" aria-labelledby="sensor-trends-title">
    <div className="equipment-section-heading"><div><p className="panel-eyebrow">RECORDED OBSERVATIONS</p><h2 id="sensor-trends-title">Sensor trends</h2><p className="equipment-analytics-coverage">Based on {readings.length} unique loaded sensor observations.</p></div><span className="equipment-section-caption">Discrete persisted samples · no interpolation</span></div>
    {readings.length === 0 ? <Card className="equipment-empty-card"><EmptyState title="No sensor observations to chart" description="A trend will appear after sensor readings have been persisted for this equipment." /></Card> :
      <div className="sensor-chart-grid">{chartSeries.map(({ series, points }) => {
        return <Card key={series.key} className="sensor-chart-card"><div className="sensor-chart-heading"><h3>{series.label}</h3><span>{series.unit}</span></div><p>Recorded value by sensor-reading timestamp</p><div className="sensor-chart" role="img" aria-label={`${series.label} in ${series.unit} across ${points.length} loaded persisted observations`}>
          <ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{ top: 8, right: 14, bottom: 8, left: 2 }}><CartesianGrid stroke="hsl(var(--line) / .65)" strokeDasharray="3 4" /><XAxis type="number" dataKey="timestampMs" name="Reading time" domain={["dataMin", "dataMax"]} tickFormatter={(value: number) => new Date(value).toLocaleDateString()} tick={{ fill: "hsl(var(--muted))", fontSize: 9 }} tickLine={false} axisLine={{ stroke: "hsl(var(--line))" }} /><YAxis type="number" dataKey="value" name={series.label} width={52} tick={{ fill: "hsl(var(--muted))", fontSize: 9 }} tickLine={false} axisLine={false} domain={["auto", "auto"]} /><Tooltip labelFormatter={(value) => `Reading time: ${new Date(Number(value)).toLocaleString()}`} formatter={(value) => [`${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${series.unit}`, series.label]} contentStyle={{ background: "hsl(var(--surface))", border: "1px solid hsl(var(--line))", borderRadius: 8, color: "hsl(var(--ink))" }} /><Scatter data={points} dataKey="value" fill="hsl(var(--cyan))" name={series.label} isAnimationActive={false} /></ScatterChart></ResponsiveContainer>
        </div><small>{points.length} actual readings · timestamps may repeat</small>
          <details className="chart-data-disclosure">
            <summary>View {series.label.toLowerCase()} observations as a table ({points.length})</summary>
            <div className="chart-data-table-wrap">
              <table className="chart-data-table">
                <caption>{series.label} ({series.unit}) by sensor-reading timestamp, chronological. Only loaded persisted observations are included.</caption>
                <thead><tr><th scope="col">Reading timestamp</th><th scope="col">Reading ID</th><th scope="col">{series.label} ({series.unit})</th></tr></thead>
                <tbody>{points.map((point) => <tr key={point.readingId}>
                  <td><time dateTime={point.timestamp}>{new Date(point.timestampMs).toISOString()}</time></td>
                  <th scope="row">{point.readingId}</th>
                  <td>{String(point.value)} {series.unit}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </details>
        </Card>;
      })}</div>}
  </section>;
});
