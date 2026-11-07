import { ChartNoAxesCombined, RadioTower } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { LatestDriftPanel } from "@/components/overview/LatestDriftPanel";
import { useLatestDriftReport } from "@/hooks/useLatestDriftReport";

export function DriftMonitoringPage() {
  const report = useLatestDriftReport();

  return (
    <div className="page-stack drift-monitoring-page">
      <PageHeader eyebrow="INPUT DISTRIBUTION" title="Drift monitoring" description="Inspect the latest persisted comparison between a validated sensor batch and the training reference." badge="LATEST REPORT ONLY" />
      <div className="drift-method-grid">
        <Card className="method-card"><span className="method-icon"><ChartNoAxesCombined size={18} /></span><span className="method-label">NUMERICAL FEATURES</span><h2>Two-sample KS test</h2><p>Tests whether current and reference empirical distributions differ.</p><span className="method-threshold">Default significance level · 0.05</span></Card>
        <Card className="method-card"><span className="method-icon"><RadioTower size={18} /></span><span className="method-label">CATEGORICAL FEATURE</span><h2>Total variation distance</h2><p>Measures distribution distance for the categorical equipment type.</p><span className="method-threshold">Default detection threshold · 0.10</span></Card>
      </div>
      <LatestDriftPanel query={report} />
      <p className="scope-note">This dataset is not a chronological machine telemetry stream. No time-series forecast or performance-degradation claim is made.</p>
      <p className="scope-note">This page shows the latest persisted report only. It does not provide report history or generate a new report.</p>
    </div>
  );
}
