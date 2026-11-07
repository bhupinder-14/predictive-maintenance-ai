import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { PredictionSummaryRecord, SensorReadingRecord } from "@/api/equipment";
import { EquipmentPredictionAnalytics } from "./EquipmentPredictionAnalytics";
import { SensorTrendCharts } from "./SensorTrendCharts";

function reading(id: number, timestamp: string, air: number): SensorReadingRecord {
  return {
    id, equipment_id: 4, timestamp, Type: "M", "Air temperature [K]": air,
    "Process temperature [K]": 310.1, "Rotational speed [rpm]": 1450,
    "Torque [Nm]": 38.6, "Tool wear [min]": 80, source: "api",
  };
}

const anomaly: PredictionSummaryRecord = {
  id: "anomaly-2", model_version: "anomaly_v2", anomaly_score: -0.62,
  is_anomaly: true, failure_probability: null, latency_ms: 2,
  created_at: "2026-10-31T11:00:00Z",
};
const earlierAnomaly: PredictionSummaryRecord = {
  ...anomaly, id: "anomaly-1", model_version: "anomaly_v1", anomaly_score: -0.21,
  is_anomaly: false, created_at: "2026-10-31T10:00:00Z",
};
const failure: PredictionSummaryRecord = {
  id: "failure-1", model_version: "failure_v1", anomaly_score: null,
  is_anomaly: null, failure_probability: 0.73, latency_ms: 3,
  created_at: "2026-10-31T10:30:00Z",
};

describe("accessible chart data equivalents", () => {
  afterEach(() => cleanup());

  it("provides sensor units, timestamps, values, and chronological rows without a tooltip", () => {
    const { rerender } = render(<SensorTrendCharts readings={[
      reading(2, "2026-10-31T11:00:00Z", 303.4),
      reading(1, "2026-10-31T10:00:00Z", 299.8),
    ]} />);

    expect(screen.getByRole("img", { name: "Air temperature in K across 2 loaded persisted observations" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("View air temperature observations as a table (2)"));
    const table = screen.getByRole("table", { name: /Air temperature \(K\) by sensor-reading timestamp, chronological/ });
    expect(within(table).getByRole("columnheader", { name: "Air temperature (K)" })).toBeInTheDocument();
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("2026-10-31T10:00:00.000Z");
    expect(rows[1]).toHaveTextContent("299.8 K");
    expect(rows[2]).toHaveTextContent("2026-10-31T11:00:00.000Z");
    expect(rows[2]).toHaveTextContent("303.4 K");

    rerender(<SensorTrendCharts readings={[reading(3, "2026-10-31T12:00:00Z", 307.2)]} />);
    expect(screen.getByRole("img", { name: "Air temperature in K across 1 loaded persisted observations" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("View air temperature observations as a table (1)"));
    const updatedTable = screen.getByRole("table", { name: /Air temperature \(K\) by sensor-reading timestamp/ });
    expect(updatedTable).toHaveTextContent("307.2 K");
    expect(updatedTable).not.toHaveTextContent("299.8 K");
  });

  it("exposes exact round-trippable sensor numbers without rounding or added decimals", () => {
    const values = [300.234, 42, 0, -12.75, 0.30000000000000004];
    const { container } = render(<SensorTrendCharts readings={values.map((value, index) =>
      reading(index + 1, `2026-10-31T${String(index + 1).padStart(2, "0")}:00:00Z`, value),
    )} />);

    fireEvent.click(screen.getByText("View air temperature observations as a table (5)"));
    const table = screen.getByRole("table", { name: /Air temperature \(K\).*chronological/ });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[1].textContent)).toEqual(
      values.map((value) => `${String(value)} K`),
    );
    for (const [index, value] of values.entries()) {
      const displayed = within(rows[index]).getAllByRole("cell")[1].textContent?.replace(/ K$/, "");
      expect(Number(displayed)).toBe(value);
    }
    expect(container.querySelector(".chart-data-table caption")).toHaveTextContent("Only loaded persisted observations are included");
  });

  it("exposes distinct anomaly and failure outputs with IDs, versions, timestamps, and metric context", () => {
    render(<EquipmentPredictionAnalytics
      anomalyPredictions={[anomaly, earlierAnomaly]}
      failurePredictions={[failure]}
      normalCount={1}
      anomalyCount={1}
      anomalyVersions={{ anomaly_v1: 1, anomaly_v2: 1 }}
      failureVersions={{ failure_v1: 1 }}
    />);

    expect(screen.getByRole("img", { name: "Anomaly score for 2 saved prediction records" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Uncalibrated class-1 estimator output for 1 saved prediction records" })).toBeInTheDocument();

    fireEvent.click(screen.getByText("View isolation forest anomaly prediction data as a table (2)"));
    const anomalyTable = screen.getByRole("table", { name: /Isolation Forest anomaly prediction: Anomaly score by prediction creation timestamp/ });
    const anomalyRows = within(anomalyTable).getAllByRole("row");
    expect(anomalyRows[1]).toHaveTextContent("anomaly-1");
    expect(anomalyRows[1]).toHaveTextContent("-0.21");
    expect(anomalyRows[1]).toHaveTextContent("anomaly_v1");
    expect(anomalyRows[2]).toHaveTextContent("anomaly-2");
    expect(anomalyRows[2]).toHaveTextContent("-0.62");
    expect(within(anomalyTable).getByRole("columnheader", { name: "Prediction created" })).toBeInTheDocument();

    fireEvent.click(screen.getByText("View random forest failure classification prediction data as a table (1)"));
    const failureTable = screen.getByRole("table", { name: /Random Forest failure classification prediction: Uncalibrated class-1 estimator output/ });
    expect(failureTable).toHaveTextContent("failure-1");
    expect(failureTable).toHaveTextContent("0.73");
    expect(failureTable).toHaveTextContent("failure_v1");
    expect(screen.getByText(/not a calibrated probability or forecast/)).toBeInTheDocument();
  });

  it("exposes exact round-trippable anomaly and failure values without precision limits", () => {
    const precise = 0.12345678901234568;
    const anomalyValues = [-precise, 0, 7];
    const failureValues = [precise, 0, 1];
    const anomalies = anomalyValues.map((value, index) => ({
      ...anomaly,
      id: `anomaly-precision-${index}`,
      anomaly_score: value,
      created_at: `2026-10-31T1${index}:00:00Z`,
    }));
    const failures = failureValues.map((value, index) => ({
      ...failure,
      id: `failure-precision-${index}`,
      failure_probability: value,
      created_at: `2026-10-31T2${index}:00:00Z`,
    }));
    render(<EquipmentPredictionAnalytics
      anomalyPredictions={anomalies}
      failurePredictions={failures}
      normalCount={1}
      anomalyCount={2}
      anomalyVersions={{ anomaly_v2: 3 }}
      failureVersions={{ failure_v1: 3 }}
    />);

    fireEvent.click(screen.getByText("View isolation forest anomaly prediction data as a table (3)"));
    const anomalyTable = screen.getByRole("table", { name: /Isolation Forest anomaly prediction/ });
    const displayedAnomalyValues = within(anomalyTable).getAllByRole("row").slice(1).map((row) =>
      within(row).getAllByRole("cell")[1].textContent ?? "",
    );
    expect(displayedAnomalyValues).toEqual(anomalyValues.map(String));
    anomalyValues.forEach((value, index) => expect(Number(displayedAnomalyValues[index])).toBe(value));

    fireEvent.click(screen.getByText("View random forest failure classification prediction data as a table (3)"));
    const failureTable = screen.getByRole("table", { name: /Random Forest failure classification prediction/ });
    const displayedFailureValues = within(failureTable).getAllByRole("row").slice(1).map((row) =>
      within(row).getAllByRole("cell")[1].textContent ?? "",
    );
    expect(displayedFailureValues).toEqual(failureValues.map(String));
    failureValues.forEach((value, index) => expect(Number(displayedFailureValues[index])).toBe(value));
  });

  it("keeps empty chart states honest and labels loaded prediction coverage as partial", () => {
    const { rerender } = render(<SensorTrendCharts readings={[]} />);
    expect(screen.getByText("No sensor observations to chart")).toBeInTheDocument();
    expect(document.querySelector(".chart-data-table")).toBeNull();

    rerender(<EquipmentPredictionAnalytics anomalyPredictions={[]} failurePredictions={[]} normalCount={0} anomalyCount={0} anomalyVersions={{}} failureVersions={{}} />);
    expect(screen.getAllByText("No saved outputs in loaded history")).toHaveLength(2);
    expect(document.querySelector(".chart-data-table")).toBeNull();
  });
});
