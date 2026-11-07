import { useMemo } from "react";
import axios from "axios";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Boxes, Clock3, Gauge } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingSkeleton } from "@/components/feedback/loading-skeleton";
import { useEquipment } from "@/hooks/useEquipment";
import { useEquipmentHistory } from "@/hooks/useEquipmentHistory";
import { buildEquipmentAnalytics } from "@/lib/equipment-analytics";
import { SensorTrendCharts } from "@/components/equipment/SensorTrendCharts";
import { EquipmentPredictionAnalytics } from "@/components/equipment/EquipmentPredictionAnalytics";

function formatTimestamp(value: string): string {
  const formatted = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value));
  return `${formatted} UTC`;
}

function isValidEquipmentId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}

export function EquipmentProfilePage() {
  const { equipmentId: routeId } = useParams();
  const equipmentId = isValidEquipmentId(routeId);
  const equipmentQuery = useEquipment();
  const history = useEquipmentHistory(equipmentId);
  const historyPages = history.data?.pages;
  const loadedEntries = useMemo(() => historyPages?.flatMap((page) => page.items) ?? [], [historyPages]);
  const analytics = useMemo(() => buildEquipmentAnalytics(loadedEntries), [loadedEntries]);
  const equipmentPages = equipmentQuery.data?.pages;
  const firstHistoryPage = historyPages?.[0];
  const profile = useMemo(
    () => equipmentPages?.flat().find((record) => record.id === equipmentId) ?? firstHistoryPage?.equipment,
    [equipmentId, equipmentPages, firstHistoryPage],
  );
  const hasMore = history.hasNextPage;

  if (equipmentId === null) return <div className="page-stack"><PageHeader eyebrow="EQUIPMENT PROFILE" title="Equipment not found" description="The requested equipment ID is not a valid positive integer." /><Link to="/equipment" className="back-link"><ArrowLeft size={15} />Back to equipment</Link></div>;
  if (history.isPending) return <div className="page-stack"><PageHeader eyebrow="EQUIPMENT PROFILE" title="Loading equipment…" description="Retrieving persisted equipment history." /><LoadingSkeleton className="equipment-profile-skeleton" /><LoadingSkeleton className="equipment-profile-skeleton" /></div>;
  if (history.isError && !history.data) {
    const notFound = axios.isAxiosError(history.error) && history.error.response?.status === 404;
    return <div className="page-stack"><PageHeader eyebrow="EQUIPMENT PROFILE" title={notFound ? "Equipment not found" : "Equipment profile unavailable"} description={notFound ? `No equipment record exists for ID ${equipmentId}.` : "The equipment-scoped history could not be retrieved."} /><ErrorState title={notFound ? "No matching equipment record" : "History endpoint unavailable"} description={notFound ? "Return to the equipment register to select an available record." : "Retry the history request to load this profile."} onRetry={notFound ? undefined : () => void history.refetch()} /><Link to="/equipment" className="back-link"><ArrowLeft size={15} />Back to equipment</Link></div>;
  }
  if (!profile) return <div className="page-stack"><PageHeader eyebrow="EQUIPMENT PROFILE" title="Equipment metadata unavailable" description={`The API did not provide metadata for equipment ID ${equipmentId}.`} /><ErrorState title="Equipment response incomplete" description="No metadata is fabricated for this profile." onRetry={() => void history.refetch()} /><Link to="/equipment" className="back-link"><ArrowLeft size={15} />Back to equipment</Link></div>;

  const latest = history.data.pages[0]?.items[0]?.reading;
  const loadedPredictionCount = analytics.anomalyPredictions.length + analytics.failurePredictions.length;
  const coverage = `Based on ${analytics.readings.length} loaded sensor observations and ${loadedPredictionCount} distinct saved prediction records.`;

  return <div className="page-stack equipment-profile-page">
    <Link to="/equipment" className="back-link"><ArrowLeft size={15} />Equipment register</Link>
    <PageHeader eyebrow="EQUIPMENT PROFILE" title={profile.name} description={`Persisted equipment record · ID ${profile.id}`} badge={`TYPE ${profile.equipment_type}`} />
    <Card className="equipment-identity-card"><div className="equipment-identity-heading"><div className="table-title-icon"><Boxes size={17} aria-hidden="true" /></div><div><p className="panel-eyebrow">REGISTERED EQUIPMENT</p><h2>{profile.name}</h2></div></div><dl className="equipment-identity-grid"><div><dt>Equipment ID</dt><dd>{profile.id}</dd></div><div><dt>Equipment type</dt><dd>{profile.equipment_type}</dd></div><div><dt>Location</dt><dd>{profile.location ?? "Not recorded"}</dd></div><div><dt>Created</dt><dd>{formatTimestamp(profile.created_at)}</dd></div></dl></Card>
    {history.isError && history.data && <p className="equipment-inline-warning" role="status">History refresh failed. The previously retrieved readings are shown as stale data.</p>}
    <section className="equipment-analytics-section" aria-labelledby="latest-observation-title"><div className="equipment-section-heading"><div><p className="panel-eyebrow">MOST RECENT PERSISTED SAMPLE</p><h2 id="latest-observation-title">Latest persisted observation</h2></div>{latest && <span className="equipment-section-caption"><Clock3 size={13} aria-hidden="true" /> {formatTimestamp(latest.timestamp)}</span>}</div>
      {!latest ? <Card className="equipment-empty-card"><EmptyState title="No persisted observations" description="This equipment record exists, but the API returned no sensor readings. This is not a live sensor state." /></Card> : <Card className="latest-observation-card"><div className="latest-observation-top"><span className="equipment-type-chip">Type {latest.Type}</span><span className="observation-label"><Gauge size={13} aria-hidden="true" /> Persisted reading #{latest.id}</span></div><div className="history-sensor-grid"><ReadingValue label="Air temperature" value={latest["Air temperature [K]"]} unit="K" /><ReadingValue label="Process temperature" value={latest["Process temperature [K]"]} unit="K" /><ReadingValue label="Rotational speed" value={latest["Rotational speed [rpm]"]} unit="rpm" /><ReadingValue label="Torque" value={latest["Torque [Nm]"]} unit="Nm" /><ReadingValue label="Tool wear" value={latest["Tool wear [min]"]} unit="min" /></div><p className="form-help">Latest persisted observation; it does not represent live sensor telemetry or current machine condition.</p></Card>}
    </section>
    <SensorTrendCharts readings={analytics.readings} />
    <EquipmentPredictionAnalytics anomalyPredictions={analytics.anomalyPredictions} failurePredictions={analytics.failurePredictions} normalCount={analytics.normalCount} anomalyCount={analytics.anomalyCount} anomalyVersions={analytics.anomalyVersions} failureVersions={analytics.failureVersions} />
    <Card className="equipment-coverage-card"><div><p className="panel-eyebrow">ANALYTICS COVERAGE</p><h2>{coverage}</h2><p>{hasMore ? "Partial history: more readings are available to load. All charts and summaries above cover only the loaded pages." : "No further page is currently available from the paginated responses; the API does not provide a lifetime total count."}</p></div>{hasMore && <Button type="button" variant="secondary" disabled={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>{history.isFetchingNextPage ? "Loading readings…" : "Load 50 older observations"}</Button>}</Card>
  </div>;
}

function ReadingValue({ label, value, unit }: { label: string; value: number; unit: string }) {
  return <div className="history-reading-value"><span>{label}</span><strong>{value.toLocaleString(undefined, { maximumFractionDigits: 2 })} {unit}</strong></div>;
}
