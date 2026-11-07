import { AlertTriangle, CheckCircle2, CircleAlert, Cpu, ScanSearch } from "lucide-react";
import type { ReactNode } from "react";
import { isPredictionOutcomeUnknown, predictionErrorMessage } from "@/api/predictions";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { useAnomalyPrediction, useFailurePrediction } from "@/hooks/usePredictionMutations";

type AnomalyMutation = ReturnType<typeof useAnomalyPrediction>;
type FailureMutation = ReturnType<typeof useFailurePrediction>;

export function PredictionResults({ anomaly, failure }: { anomaly: AnomalyMutation; failure: FailureMutation }) {
  return (
    <div className="prediction-result-stack">
      {anomaly.data && <Card className="prediction-result-card anomaly-result" aria-label="Anomaly detection result">
        <div className="prediction-result-header"><span className="model-icon"><ScanSearch size={17} aria-hidden="true" /></span><div><p className="panel-eyebrow">ISOLATION FOREST</p><h2>Anomaly detection result</h2></div><StatusBadge label={anomaly.data.classification === "anomaly" ? "Anomaly" : "Normal"} tone={anomaly.data.classification === "anomaly" ? "warn" : "good"} /></div>
        <div className="prediction-result-primary"><span>Classification</span><strong>{anomaly.data.classification === "anomaly" ? "Anomalous sensor pattern" : "Normal sensor pattern"}</strong></div>
        <div className="prediction-result-metadata"><div><span>ANOMALY SCORE</span><strong>{anomaly.data.anomaly_score.toLocaleString(undefined, { maximumFractionDigits: 6 })}</strong></div><div><span>MODEL VERSION</span><strong>{anomaly.data.model_version}</strong></div><div><span>PREDICTION ID</span><strong className="record-id">{anomaly.data.prediction_id}</strong></div></div>
        <p className="prediction-result-note">This is the raw Isolation Forest <code>score_samples</code> output. Lower scores are more anomalous; the score is not a failure probability.</p>
        {anomaly.data.explanation.top_suspicious_features.length > 0 && <div className="suspicious-feature-list"><h3>Suspicious transformed features</h3>{anomaly.data.explanation.top_suspicious_features.map((feature) => <div key={feature.feature}><span>{feature.feature}</span><span>Standardised value {feature.standardised_value.toLocaleString()}</span><strong>Deviation {feature.abs_deviation.toLocaleString()}</strong></div>)}</div>}
        {anomaly.isSuccess && !anomaly.isPending && <p className="prediction-success-note" role="status" aria-live="polite" aria-atomic="true"><CheckCircle2 size={14} aria-hidden="true" /> Anomaly detection result: {anomaly.data.classification === "anomaly" ? "anomalous sensor pattern" : "normal sensor pattern"}. Isolation Forest score_samples output: {anomaly.data.anomaly_score.toLocaleString(undefined, { maximumFractionDigits: 6 })}; lower scores are more anomalous, and this is not a failure probability. Saved prediction {anomaly.data.prediction_id}; equipment {anomaly.data.equipment_id}, reading {anomaly.data.reading_id}.</p>}
      </Card>}
      {anomaly.isError && <ResultError title="Anomaly detection failed" message={predictionErrorMessage(anomaly.error)} outcomeUnknown={isPredictionOutcomeUnknown(anomaly.error)} icon={<ScanSearch size={16} aria-hidden="true" />} />}

      {failure.data && <Card className="prediction-result-card failure-result" aria-label="Failure classification result">
        <div className="prediction-result-header"><span className="model-icon"><Cpu size={17} aria-hidden="true" /></span><div><p className="panel-eyebrow">RANDOM FOREST</p><h2>Failure classification result</h2></div><StatusBadge label={failure.data.predicted_class === 1 ? "Class 1 predicted" : "Class 0 predicted"} tone={failure.data.predicted_class === 1 ? "danger" : "good"} /></div>
        <div className="prediction-result-primary"><span>Predicted class</span><strong>{failure.data.predicted_class === 1 ? "Machine failure class 1" : "No machine failure class 0"}</strong></div>
        <div className="prediction-result-metadata"><div><span>CLASS 1 ESTIMATOR OUTPUT</span><strong>{(failure.data.failure_probability * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%</strong></div><div><span>MODEL VERSION</span><strong>{failure.data.model_version}</strong></div><div><span>PREDICTION ID</span><strong className="record-id">{failure.data.prediction_id}</strong></div></div>
        <p className="prediction-result-note">The class is the model’s binary prediction. The displayed value is the estimator’s <code>predict_proba</code> output for class 1; it is not calibrated and does not forecast future failure.</p>
        {failure.isSuccess && !failure.isPending && <p className="prediction-success-note" role="status" aria-live="polite" aria-atomic="true"><CheckCircle2 size={14} aria-hidden="true" /> Failure classification result: class {failure.data.predicted_class}. Class-1 predict_proba estimator output: {(failure.data.failure_probability * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%; this output is uncalibrated, not a calibrated probability or future-failure forecast. Saved prediction {failure.data.prediction_id}; equipment {failure.data.equipment_id}, reading {failure.data.reading_id}.</p>}
      </Card>}
      {failure.isError && <ResultError title="Failure classification failed" message={predictionErrorMessage(failure.error)} outcomeUnknown={isPredictionOutcomeUnknown(failure.error)} icon={<CircleAlert size={16} aria-hidden="true" />} />}
    </div>
  );
}

function ResultError({ title, message, outcomeUnknown, icon }: { title: string; message: string; outcomeUnknown: boolean; icon: ReactNode }) {
  return <Card className="prediction-result-error" role="alert"><AlertTriangle size={18} aria-hidden="true" /><div><span className="result-error-icon">{icon}</span><h2>{title}</h2><p>{message}</p><small>{outcomeUnknown ? "Do not resubmit until you have checked equipment history. The other model action remains independent." : "Correct the request or retry this model. The other model action remains independent."}</small></div></Card>;
}
