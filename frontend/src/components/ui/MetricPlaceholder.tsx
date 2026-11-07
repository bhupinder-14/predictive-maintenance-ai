import type { LucideIcon } from "lucide-react";
import { Card } from "./card";

export function MetricPlaceholder({ label, icon: Icon, note = "Integration pending" }: {
  label: string;
  icon: LucideIcon;
  note?: string;
}) {
  return (
    <Card className="metric-card">
      <div className="metric-card-top"><span className="metric-icon"><Icon size={17} /></span></div>
      <p className="metric-label">{label}</p>
      <div className="metric-value-placeholder" aria-label={`${label}: integration pending`}>—</div>
      <p className="metric-note">{note}</p>
    </Card>
  );
}
