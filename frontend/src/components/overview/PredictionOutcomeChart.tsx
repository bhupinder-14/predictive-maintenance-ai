import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCount } from "@/api/metrics";

interface PredictionOutcomeChartProps {
  title: string;
  windowLabel: string;
  data: Array<{ label: string; count: number; color: string }>;
}

export function PredictionOutcomeChart({ title, windowLabel, data }: PredictionOutcomeChartProps) {
  return (
    <div
      role="img"
      aria-label={`${title} outcomes in the last ${windowLabel}: ${data.map(({ label, count }) => `${label} ${count}`).join(", ")}`}
      className="overview-activity-chart"
    >
      <ResponsiveContainer width="100%" height={190}>
        <BarChart data={data} layout="vertical" margin={{ top: 8, right: 14, bottom: 4, left: 2 }} accessibilityLayer>
          <CartesianGrid stroke="rgba(131, 159, 186, 0.12)" horizontal={false} />
          <XAxis type="number" allowDecimals={false} tick={{ fill: "#8799ad", fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="label" width={76} tick={{ fill: "#c5d0dc", fontSize: 10 }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: "rgba(91, 130, 164, 0.1)" }}
            contentStyle={{ background: "#111e2e", border: "1px solid #2a3b4f", borderRadius: 8, color: "#e9f0f7", fontSize: 11 }}
            formatter={(value) => [formatCount(Number(value)), "Predictions"]}
          />
          <Bar dataKey="count" name="Predictions" radius={[0, 4, 4, 0]} maxBarSize={24}>
            {data.map((entry) => <Cell key={entry.label} fill={entry.color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
