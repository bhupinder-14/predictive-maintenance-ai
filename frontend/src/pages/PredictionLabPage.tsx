import { Cpu, ScanSearch } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { SensorObservationForm } from "@/components/prediction/SensorObservationForm";

export function PredictionLabPage() {
  return (
    <div className="page-stack prediction-lab-page">
      <PageHeader eyebrow="MODEL WORKSPACE" title="Prediction lab" description="Run one selected model against a validated sensor observation and save its result to equipment history." badge="INDEPENDENT MODEL RUNS" />
      <div className="model-grid">
        <Card className="model-card model-anomaly"><div className="model-card-header"><span className="model-icon"><ScanSearch size={18} aria-hidden="true" /></span><span className="model-tag">UNSUPERVISED</span></div><h2>Anomaly detection</h2><p className="model-subtitle">Isolation Forest</p><div className="model-rule" /><p className="model-description">Returns a normal/anomaly classification and raw score_samples value. A lower score is more anomalous; the score is not a failure probability.</p><div className="model-card-footer"><span>Saved output</span><strong>Classification + anomaly score</strong></div></Card>
        <Card className="model-card model-failure"><div className="model-card-header"><span className="model-icon"><Cpu size={18} aria-hidden="true" /></span><span className="model-tag">SUPERVISED</span></div><h2>Failure classification</h2><p className="model-subtitle">Random Forest</p><div className="model-rule" /><p className="model-description">Returns a binary class and the estimator’s class 1 predict_proba output. That value is not calibrated or forward-looking.</p><div className="model-card-footer"><span>Saved output</span><strong>Class + estimator output</strong></div></Card>
      </div>
      <SensorObservationForm />
    </div>
  );
}
