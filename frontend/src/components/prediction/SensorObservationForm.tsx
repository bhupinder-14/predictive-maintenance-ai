import { useEffect, useState, type ChangeEvent } from "react";
import { Activity, Cpu, LoaderCircle, ScanSearch } from "lucide-react";
import type { PredictionInput } from "@/api/predictions";
import type { MachineType } from "@/api/equipment";
import { useEquipment } from "@/hooks/useEquipment";
import { useAnomalyPrediction, useFailurePrediction } from "@/hooks/usePredictionMutations";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PredictionResults } from "./PredictionResults";

type SensorKey = "Air temperature [K]" | "Process temperature [K]" | "Rotational speed [rpm]" | "Torque [Nm]" | "Tool wear [min]";
type Draft = Record<SensorKey, string> & { Type: MachineType | "" };
type FieldErrors = Partial<Record<SensorKey | "Type" | "equipment", string>>;
type EquipmentMode = "existing" | "new";

const sensors: Array<{ key: SensorKey; id: string; label: string; min: number; max: number; unit: string }> = [
  { key: "Air temperature [K]", id: "air-temperature", label: "Air temperature", min: 290, max: 310, unit: "K" },
  { key: "Process temperature [K]", id: "process-temperature", label: "Process temperature", min: 300, max: 320, unit: "K" },
  { key: "Rotational speed [rpm]", id: "rotational-speed", label: "Rotational speed", min: 1000, max: 3000, unit: "rpm" },
  { key: "Torque [Nm]", id: "torque", label: "Torque", min: 0, max: 100, unit: "Nm" },
  { key: "Tool wear [min]", id: "tool-wear", label: "Tool wear", min: 0, max: 300, unit: "min" },
];

const emptyDraft: Draft = {
  Type: "",
  "Air temperature [K]": "",
  "Process temperature [K]": "",
  "Rotational speed [rpm]": "",
  "Torque [Nm]": "",
  "Tool wear [min]": "",
};

function machineTypeFromInput(value: string): MachineType | "" {
  return value === "L" || value === "M" || value === "H" ? value : "";
}

export function SensorObservationForm() {
  const equipment = useEquipment();
  const anomaly = useAnomalyPrediction();
  const failure = useFailurePrediction();
  const equipmentRecords = equipment.data?.pages.flat() ?? [];
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [equipmentMode, setEquipmentMode] = useState<EquipmentMode>("existing");
  const [equipmentId, setEquipmentId] = useState("");
  const [equipmentName, setEquipmentName] = useState("");
  const [equipmentLocation, setEquipmentLocation] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [attempted, setAttempted] = useState(false);

  useEffect(() => {
    if (equipment.data && equipment.data.pages.flat().length === 0) setEquipmentMode("new");
  }, [equipment.data]);

  function updateSensor(event: ChangeEvent<HTMLInputElement>) {
    const { name, value } = event.currentTarget;
    if (name === "Type") setDraft((current) => ({ ...current, Type: machineTypeFromInput(value) }));
    else setDraft((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: undefined }));
  }

  function buildInput(): PredictionInput | null {
    const nextErrors: FieldErrors = {};
    if (draft.Type !== "L" && draft.Type !== "M" && draft.Type !== "H") nextErrors.Type = "Choose a machine type.";
    const numericValues = new Map<SensorKey, number>();
    for (const sensor of sensors) {
      const raw = draft[sensor.key].trim();
      const parsed = raw === "" ? Number.NaN : Number(raw);
      if (!Number.isFinite(parsed)) nextErrors[sensor.key] = "Enter a finite numeric value.";
      else if (parsed < sensor.min || parsed > sensor.max) nextErrors[sensor.key] = `Enter a value from ${sensor.min} to ${sensor.max} ${sensor.unit}.`;
      else numericValues.set(sensor.key, parsed);
    }

    let association: Pick<PredictionInput, "equipment_id" | "equipment_name" | "equipment_location"> = {};
    if (equipmentMode === "existing") {
      const id = Number(equipmentId);
      if (!Number.isSafeInteger(id) || id <= 0 || !equipmentRecords.some((item) => item.id === id)) {
        nextErrors.equipment = "Select an equipment record returned by the API.";
      } else association = { equipment_id: id };
    } else {
      const name = equipmentName.trim();
      if (!name) nextErrors.equipment = "Enter a name for the equipment to register with this prediction.";
      else association = { equipment_name: name, ...(equipmentLocation.trim() ? { equipment_location: equipmentLocation.trim() } : {}) };
    }

    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0 || !draft.Type || numericValues.size !== sensors.length) return null;
    return {
      Type: draft.Type,
      "Air temperature [K]": numericValues.get("Air temperature [K]")!,
      "Process temperature [K]": numericValues.get("Process temperature [K]")!,
      "Rotational speed [rpm]": numericValues.get("Rotational speed [rpm]")!,
      "Torque [Nm]": numericValues.get("Torque [Nm]")!,
      "Tool wear [min]": numericValues.get("Tool wear [min]")!,
      ...association,
    };
  }

  function runModel(model: "anomaly" | "failure") {
    setAttempted(true);
    const input = buildInput();
    if (!input) return;
    if (model === "anomaly") anomaly.mutate(input);
    else failure.mutate(input);
  }

  return (
    <div className="prediction-workspace">
      <Card className="prediction-form-card">
        <div className="prediction-section-heading"><div><p className="panel-eyebrow">VALIDATED SENSOR OBSERVATION</p><h2>Observation inputs</h2></div><span className="model-tag">6 MODEL FEATURES</span></div>
        {equipment.isPending && <p className="form-help" role="status">Loading equipment records…</p>}
        {equipment.isError && <ErrorState title="Equipment list unavailable" description="Existing equipment could not be loaded. You can still register a named equipment record with the prediction." onRetry={() => void equipment.refetch()} />}
        <fieldset className="sensor-fieldset">
          <legend>Equipment association</legend>
          <div className="equipment-mode-options" role="group" aria-label="Equipment association type">
            <label><input type="radio" name="equipment-mode" value="existing" checked={equipmentMode === "existing"} onChange={() => { setEquipmentMode("existing"); setErrors((current) => ({ ...current, equipment: undefined })); }} disabled={!equipmentRecords.length} /> Existing equipment</label>
            <label><input type="radio" name="equipment-mode" value="new" checked={equipmentMode === "new"} onChange={() => { setEquipmentMode("new"); setErrors((current) => ({ ...current, equipment: undefined })); }} /> Register by name</label>
          </div>
          {equipmentMode === "existing" ? (
            <label className="field-control" htmlFor="prediction-equipment"><span>Equipment record</span>
              <select id="prediction-equipment" value={equipmentId} onChange={(event) => { setEquipmentId(event.currentTarget.value); setErrors((current) => ({ ...current, equipment: undefined })); }} aria-invalid={Boolean(errors.equipment)} aria-describedby={errors.equipment ? "equipment-error" : "equipment-help"}>
                <option value="">Select equipment</option>
                {equipmentRecords.map((item) => <option key={item.id} value={item.id}>{item.name} · ID {item.id}</option>)}
              </select>
              <small id={errors.equipment ? "equipment-error" : "equipment-help"} className={errors.equipment ? "field-error" : "field-help"}>{errors.equipment ?? "Equipment IDs are loaded from the backend."}</small>
              {equipment.hasNextPage && <Button type="button" variant="ghost" size="default" disabled={equipment.isFetchingNextPage} onClick={() => void equipment.fetchNextPage()}>{equipment.isFetchingNextPage ? "Loading more equipment…" : "Load more equipment"}</Button>}
            </label>
          ) : (
            <div className="equipment-new-grid">
              <label className="field-control" htmlFor="new-equipment-name"><span>Equipment name</span><input id="new-equipment-name" value={equipmentName} maxLength={120} onChange={(event) => { setEquipmentName(event.currentTarget.value); setErrors((current) => ({ ...current, equipment: undefined })); }} aria-invalid={Boolean(errors.equipment)} aria-describedby={errors.equipment ? "equipment-error" : undefined} />{errors.equipment && <small id="equipment-error" className="field-error">{errors.equipment}</small>}</label>
              <label className="field-control" htmlFor="new-equipment-location"><span>Location <small>(optional)</small></span><input id="new-equipment-location" value={equipmentLocation} maxLength={160} onChange={(event) => setEquipmentLocation(event.currentTarget.value)} /></label>
              <p className="form-help">The prediction request will register this named equipment through the existing backend workflow.</p>
            </div>
          )}
        </fieldset>

        <form className="sensor-form" onSubmit={(event) => { event.preventDefault(); runModel("anomaly"); }} noValidate>
          <fieldset className="sensor-fieldset"><legend>Machine characteristics</legend>
            <label className="field-control" htmlFor="sensor-type"><span>Type</span>
              <select id="sensor-type" name="Type" value={draft.Type} onChange={(event) => { const value = event.currentTarget.value; setDraft((current) => ({ ...current, Type: machineTypeFromInput(value) })); setErrors((current) => ({ ...current, Type: undefined })); }} aria-invalid={Boolean(errors.Type)} aria-describedby={errors.Type ? "sensor-type-error" : "sensor-type-help"}>
                <option value="">Select type</option><option value="L">L · Low</option><option value="M">M · Medium</option><option value="H">H · High</option>
              </select>
              <small id={errors.Type ? "sensor-type-error" : "sensor-type-help"} className={errors.Type ? "field-error" : "field-help"}>{errors.Type ?? "AI4I categorical product type."}</small>
            </label>
            <div className="sensor-input-grid">
              {sensors.map((sensor) => (
                <label className="field-control" htmlFor={`sensor-${sensor.id}`} key={sensor.key}>
                  <span>{sensor.label} <small>({sensor.unit})</small></span>
                  <input id={`sensor-${sensor.id}`} name={sensor.key} type="number" inputMode="decimal" step="any" min={sensor.min} max={sensor.max} value={draft[sensor.key]} onChange={updateSensor} aria-invalid={Boolean(errors[sensor.key])} aria-describedby={errors[sensor.key] ? `sensor-${sensor.id}-error` : `sensor-${sensor.id}-range`} />
                  <small id={errors[sensor.key] ? `sensor-${sensor.id}-error` : `sensor-${sensor.id}-range`} className={errors[sensor.key] ? "field-error" : "field-help"}>{errors[sensor.key] ?? `Valid range ${sensor.min}–${sensor.max} ${sensor.unit}.`}</small>
                </label>
              ))}
            </div>
          </fieldset>
          {attempted && Object.keys(errors).length > 0 && <p className="form-validation-summary" role="alert">Correct the highlighted fields before running a model.</p>}
          <div className="prediction-actions" aria-label="Independent prediction actions">
            <Button type="submit" variant="primary" disabled={anomaly.isPending} aria-busy={anomaly.isPending}>
              {anomaly.isPending ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <ScanSearch size={15} aria-hidden="true" />}
              {anomaly.isPending ? "Running anomaly detection…" : "Run anomaly detection"}
            </Button>
            <Button type="button" variant="secondary" disabled={failure.isPending} aria-busy={failure.isPending} onClick={() => runModel("failure")}>
              {failure.isPending ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Cpu size={15} aria-hidden="true" />}
              {failure.isPending ? "Classifying…" : "Predict machine failure"}
            </Button>
          </div>
          <p className="prediction-disclaimer"><Activity size={14} aria-hidden="true" /> Each action runs and persists only its selected model. These row-level outputs are not future forecasts.</p>
        </form>
      </Card>

      <section className="prediction-results" aria-label="Prediction results">
        <PredictionResults anomaly={anomaly} failure={failure} />
        {!anomaly.data && !failure.data && !anomaly.isError && !failure.isError && <EmptyState title="No prediction run yet" description="Submit a valid observation to view a saved model result. Each model can be run independently." />}
      </section>
    </div>
  );
}
