import { memo, useCallback, useMemo, useState } from "react";
import { ArrowDown, ChevronDown, Clock3, FileSearch, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingSkeleton } from "@/components/feedback/loading-skeleton";
import { useEquipment } from "@/hooks/useEquipment";
import { useEquipmentHistory } from "@/hooks/useEquipmentHistory";
import { useSavedPrediction } from "@/hooks/useSavedPrediction";
import type { EquipmentHistoryEntry, PredictionSummaryRecord } from "@/api/equipment";

export function PredictionHistoryPage() {
  const equipment = useEquipment();
  const [equipmentId, setEquipmentId] = useState("");
  const [predictionId, setPredictionId] = useState<string | null>(null);
  const selectedId = equipmentId ? Number(equipmentId) : null;
  const history = useEquipmentHistory(selectedId);
  const prediction = useSavedPrediction(predictionId);
  const equipmentPages = equipment.data?.pages;
  const equipmentRecords = useMemo(() => equipmentPages?.flat() ?? [], [equipmentPages]);
  const historyPages = history.data?.pages;
  const historyItems = useMemo(() => historyPages?.flatMap((page) => page.items) ?? [], [historyPages]);
  const predictionContext = useMemo(() => {
    if (!predictionId) return null;
    for (const entry of historyItems) {
      const match = entry.predictions.find((item) => item.id === predictionId);
      if (match) return { entry, summary: match };
    }
    return null;
  }, [historyItems, predictionId]);

  const chooseEquipment = useCallback((value: string) => {
    setEquipmentId(value);
    setPredictionId(null);
  }, []);

  const onSelectPrediction = useCallback((id: string) => {
    setPredictionId((current) => current === id ? null : id);
  }, []);

  const matchingSavedRecord = prediction.data && selectedId !== null && predictionContext &&
    prediction.data.equipment_id === selectedId && prediction.data.reading_id === predictionContext.entry.reading.id &&
    prediction.data.id === predictionContext.summary.id;

  return (
    <div className="page-stack history-page">
      <PageHeader eyebrow="PERSISTED RECORDS" title="Prediction history" description="Inspect saved sensor readings and model outputs for one equipment record at a time." badge="EQUIPMENT-SCOPED" />
      <Card className="history-selector-card">
        <div className="history-selector-heading"><div className="table-title-icon"><Clock3 size={17} aria-hidden="true" /></div><div><h2>Choose equipment</h2><p>History is retrieved only for the selected equipment.</p></div></div>
        {equipment.isPending ? <p role="status" className="form-help">Loading equipment records…</p> : equipment.isError && !equipment.data ? <ErrorState title="Equipment could not be loaded" description="The equipment endpoint did not return a valid list." onRetry={() => void equipment.refetch()} /> : equipmentRecords.length === 0 ? <EmptyState title="No equipment records are available" description="Create or associate equipment through a named prediction in the Prediction Lab. No records are fabricated here." icon={<FileSearch size={18} aria-hidden="true" />} /> : (
          <div className="history-select-row">
            <label className="field-control" htmlFor="history-equipment"><span>Equipment record</span><select id="history-equipment" value={equipmentId} onChange={(event) => chooseEquipment(event.currentTarget.value)}><option value="">Select equipment</option>{equipmentRecords.map((item) => <option key={item.id} value={item.id}>{item.name} · ID {item.id}{item.location ? ` · ${item.location}` : ""}</option>)}</select></label>
            {equipment.hasNextPage && <Button type="button" variant="secondary" disabled={equipment.isFetchingNextPage} onClick={() => void equipment.fetchNextPage()}>{equipment.isFetchingNextPage ? "Loading…" : "Load more equipment"}<ChevronDown size={14} aria-hidden="true" /></Button>}
          </div>
        )}
        {equipment.isError && equipment.data && <p className="history-stale-note" role="status">Equipment refresh failed. Showing the equipment records already retrieved.</p>}
      </Card>

      {selectedId === null ? <Card className="history-empty-panel"><EmptyState title="Select equipment to view history" description="The API does not expose a global prediction history." icon={<FileSearch size={18} aria-hidden="true" />} /></Card> : history.isPending ? (
        <section className="history-reading-list" aria-label="Equipment history loading" role="status" aria-live="polite"><span className="sr-only">Loading equipment history…</span><LoadingSkeleton className="history-reading-skeleton" /><LoadingSkeleton className="history-reading-skeleton" /></section>
      ) : history.isError && !history.data ? (
        <ErrorState title="Equipment history unavailable" description="The selected equipment history could not be retrieved." onRetry={() => void history.refetch()} />
      ) : historyItems.length === 0 ? (
        <Card className="history-empty-panel"><div className="history-section-heading"><h2>{history.data?.pages[0]?.equipment.name ?? "Equipment history"}</h2><span>ID {selectedId}</span></div><EmptyState title="No readings or predictions for this equipment" description="The backend returned an empty history for this equipment record." /></Card>
      ) : (
        <section className="history-reading-list" aria-label={`Prediction history for equipment ${selectedId}`}>
          {history.isError && <p className="history-stale-note" role="status">History refresh failed. Showing the last successfully retrieved records.</p>}
          {historyItems.map((entry) => <ReadingHistoryCard key={entry.reading.id} entry={entry} selectedPredictionId={entry.predictions.some((item) => item.id === predictionId) ? predictionId : null} onSelectPrediction={onSelectPrediction} />)}
          {history.hasNextPage && <Button className="history-load-more" type="button" variant="secondary" disabled={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>{history.isFetchingNextPage ? <RefreshCw className="spin" size={14} aria-hidden="true" /> : <ArrowDown size={14} aria-hidden="true" />}{history.isFetchingNextPage ? "Loading older readings…" : "Load older readings"}</Button>}
          {!history.hasNextPage && historyItems.length > 0 && <p className="history-end-note">End of available equipment history.</p>}
        </section>
      )}

      {predictionId && <Card className="saved-prediction-detail" aria-label="Saved prediction details">
        <div className="history-section-heading"><div><p className="panel-eyebrow">SAVED RECORD</p><h2>Prediction details</h2></div><Button type="button" variant="ghost" onClick={() => setPredictionId(null)}>Close</Button></div>
        {prediction.isPending ? <LoadingSkeleton /> : prediction.isError ? <ErrorState title="Saved prediction could not be loaded" description="The selected prediction detail endpoint did not return a valid record." onRetry={() => void prediction.refetch()} /> : !matchingSavedRecord ? <ErrorState title="Saved record does not match history" description="The retrieved prediction ID, equipment, or reading did not match the selected history entry." /> : predictionContext && <SavedPredictionDetail entry={predictionContext.entry} summary={predictionContext.summary} record={prediction.data} />}
      </Card>}
      <p className="scope-note">Readings are returned newest first by the backend. Pagination uses its supported limit/offset parameters; no global, date-filtered, or synthetic history is shown.</p>
    </div>
  );
}

const ReadingHistoryCard = memo(function ReadingHistoryCard({ entry, selectedPredictionId, onSelectPrediction }: { entry: EquipmentHistoryEntry; selectedPredictionId: string | null; onSelectPrediction: (id: string) => void }) {
  const reading = entry.reading;
  return (
    <Card className="history-reading-card">
      <div className="history-section-heading"><div><p className="panel-eyebrow">SENSOR READING · #{reading.id}</p><h2>{formatTimestamp(reading.timestamp)}</h2></div><span className="history-type-badge">Type {reading.Type}</span></div>
      <div className="history-sensor-grid">
        <ReadingValue label="Air temperature" value={reading["Air temperature [K]"]} unit="K" />
        <ReadingValue label="Process temperature" value={reading["Process temperature [K]"]} unit="K" />
        <ReadingValue label="Rotational speed" value={reading["Rotational speed [rpm]"]} unit="rpm" />
        <ReadingValue label="Torque" value={reading["Torque [Nm]"]} unit="Nm" />
        <ReadingValue label="Tool wear" value={reading["Tool wear [min]"]} unit="min" />
        <ReadingValue label="Source" value={reading.source} />
      </div>
      <div className="history-prediction-list">
        <h3>Saved model predictions <span>{entry.predictions.length}</span></h3>
        {entry.predictions.length === 0 ? <p className="history-no-prediction">This saved reading has no associated prediction record.</p> : entry.predictions.map((item) => {
          const isAnomaly = item.anomaly_score !== null && item.is_anomaly !== null;
          const label = isAnomaly ? `Anomaly detection · ${item.is_anomaly ? "Anomaly" : "Normal"}` : "Failure classification · estimator output";
          return <div className="history-prediction-row" key={item.id}>
            <div><span className={`history-family-mark ${isAnomaly ? "family-anomaly" : "family-failure"}`}>{isAnomaly ? "ANOMALY" : "FAILURE"}</span><strong>{label}</strong><small>{item.model_version} · {formatTimestamp(item.created_at)}</small></div>
            <div className="history-outcome-value">{isAnomaly ? `Score ${item.anomaly_score?.toLocaleString(undefined, { maximumFractionDigits: 5 })}` : `Estimator output ${((item.failure_probability ?? 0) * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`}</div>
            <Button type="button" variant={selectedPredictionId === item.id ? "primary" : "secondary"} onClick={() => onSelectPrediction(item.id)} aria-expanded={selectedPredictionId === item.id}>View saved record</Button>
          </div>;
        })}
        {entry.predictions.some((item) => item.failure_probability !== null) && <p className="history-semantics-note">Failure estimator outputs are not calibrated probabilities. Anomaly scores are not failure probabilities.</p>}
      </div>
    </Card>
  );
});

function SavedPredictionDetail({ entry, summary, record }: { entry: EquipmentHistoryEntry; summary: PredictionSummaryRecord; record: NonNullable<ReturnType<typeof useSavedPrediction>["data"]> }) {
  const isAnomaly = record.anomaly_score !== null && record.is_anomaly !== null;
  return (
    <div className="saved-record-content">
      <dl className="saved-record-grid">
        <div><dt>Prediction ID</dt><dd className="record-id">{record.id}</dd></div><div><dt>Model family</dt><dd>{isAnomaly ? "Isolation Forest anomaly detection" : "Random Forest failure classification"}</dd></div>
        <div><dt>Equipment / reading</dt><dd>{record.equipment_id} / {record.reading_id}</dd></div><div><dt>Model version</dt><dd>{record.model_version}</dd></div>
        <div><dt>Created</dt><dd>{formatTimestamp(record.created_at)}</dd></div><div><dt>Inference latency</dt><dd>{record.latency_ms.toLocaleString(undefined, { maximumFractionDigits: 3 })} ms</dd></div>
        {isAnomaly ? <><div><dt>Classification</dt><dd>{record.is_anomaly ? "Anomaly" : "Normal"}</dd></div><div><dt>Anomaly score</dt><dd>{record.anomaly_score?.toLocaleString(undefined, { maximumFractionDigits: 6 })}</dd></div></> : <div><dt>Class 1 estimator output</dt><dd>{((record.failure_probability ?? 0) * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}% · not calibrated</dd></div>}
      </dl>
      <div className="saved-reading-summary"><h3>Associated sensor reading #{entry.reading.id}</h3><p>{formatTimestamp(entry.reading.timestamp)} · Type {entry.reading.Type} · Air {entry.reading["Air temperature [K]"]} K · Process {entry.reading["Process temperature [K]"]} K · Speed {entry.reading["Rotational speed [rpm]"]} rpm · Torque {entry.reading["Torque [Nm]"]} Nm · Tool wear {entry.reading["Tool wear [min]"]} min</p><small>History summary ID {summary.id} matches the retrieved prediction record.</small></div>
    </div>
  );
}

function ReadingValue({ label, value, unit }: { label: string; value: number | string; unit?: string }) {
  return <div className="history-reading-value"><span>{label}</span><strong>{typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value}{unit ? ` ${unit}` : ""}</strong></div>;
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
