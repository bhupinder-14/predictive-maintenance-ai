import { expect, test } from "@playwright/test";
import {
  anomalyResponse,
  driftResponse,
  failureResponse,
  historyEntry,
  installApiMocks,
  metricsResponse,
  predictionSummary,
} from "./support/api-mocks";

test("navigates the application routes and redirects unknown paths to Overview", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/");
  await expect(page.locator("h1")).toHaveText("Operations overview");

  for (const [name, route, heading] of [
    ["Equipment", "/equipment", "Equipment"],
    ["Prediction Lab", "/prediction-lab", "Prediction lab"],
    ["Prediction History", "/prediction-history", "Prediction history"],
    ["Drift Monitoring", "/drift", "Drift monitoring"],
    ["System Health", "/system", "System health"],
  ]) {
    await page.getByRole("link", { name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${route.replaceAll("/", "\\/")}$`));
    await expect(page.locator("h1")).toHaveText(heading);
  }

  await page.goto("/not-a-real-route");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator("h1")).toHaveText("Operations overview");
});

test("equipment explorer searches loaded records, paginates, and opens the selected profile", async ({ page }) => {
  const firstPage = Array.from({ length: 100 }, (_, index) => ({
    id: index + 1,
    name: `Press ${index + 1}`,
    equipment_type: index % 2 === 0 ? "M" : "L",
    location: `Line ${index % 5 + 1}`,
    created_at: "2026-10-31T10:00:00Z",
  }));
  const api = await installApiMocks(page, {
    equipmentPage: (offset) => offset === 0 ? firstPage : [{
      id: 101, name: "Press 101", equipment_type: "H", location: "Line 9", created_at: "2026-10-31T11:00:00Z",
    }],
    historyPage: (id) => ({
      equipment: { id, name: "Press 101", equipment_type: "H", location: "Line 9", created_at: "2026-10-31T11:00:00Z" },
      items: [],
    }),
  });

  await page.goto("/equipment");
  await expect(page.getByRole("rowheader", { name: /Press 1/ }).first()).toBeVisible();
  await page.getByRole("searchbox", { name: "Search loaded equipment" }).fill("Press 2");
  await expect(page.getByRole("link", { name: "Open Press 2 profile" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Press 3 profile" })).toHaveCount(0);
  await page.getByRole("searchbox", { name: "Search loaded equipment" }).clear();

  await page.getByRole("button", { name: /Load more equipment/ }).click();
  await expect(page.getByRole("link", { name: "Open Press 101 profile" })).toBeVisible();
  expect(api.equipment).toBe(2);
  await page.getByRole("searchbox", { name: "Search loaded equipment" }).fill("Press 101");
  await page.getByRole("link", { name: "Open Press 101 profile" }).click();
  await expect(page).toHaveURL(/\/equipment\/101$/);
  await expect(page.locator("h1")).toHaveText("Press 101");
});

test("equipment explorer distinguishes empty data from a recoverable API error", async ({ page }) => {
  await installApiMocks(page, { equipmentPage: () => [] });
  await page.goto("/equipment");
  await expect(page.getByText("No equipment records available")).toBeVisible();
});

test("equipment explorer retries a failed first page and shows returned records", async ({ page }) => {
  let calls = 0;
  await installApiMocks(page, {
    equipmentPage: () => ++calls === 1
      ? { status: 503, body: { detail: "Database is unavailable" } }
      : [{ id: 7, name: "Press A", equipment_type: "M", location: "Line 2", created_at: "2026-10-31T10:00:00Z" }],
  });
  await page.goto("/equipment");
  const alert = page.getByRole("alert").filter({ hasText: "Equipment could not be loaded" });
  await expect(alert).toBeVisible();
  await alert.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("link", { name: "Open Press A profile" })).toBeVisible();
});

test("Prediction Lab runs anomaly and failure actions independently and announces returned semantics", async ({ page }) => {
  const api = await installApiMocks(page);
  const expectedRequestBody = {
    Type: "M",
    "Air temperature [K]": 300.2,
    "Process temperature [K]": 310.1,
    "Rotational speed [rpm]": 1450,
    "Torque [Nm]": 38.6,
    "Tool wear [min]": 80,
    equipment_id: 7,
  };
  await page.goto("/prediction-lab");
  await page.getByLabel("Equipment record").selectOption("7");
  await fillValidObservation(page);

  await page.getByRole("button", { name: "Run anomaly detection" }).click();
  const anomalyStatus = page.getByLabel("Anomaly detection result").getByRole("status");
  await expect(anomalyStatus).toContainText("anomalous sensor pattern");
  await expect(anomalyStatus).toContainText("score_samples output: -0.42");
  await expect(anomalyStatus).toContainText("not a failure probability");
  await expect(anomalyStatus).toContainText(`equipment ${anomalyResponse.equipment_id}, reading ${anomalyResponse.reading_id}`);
  expect(api.anomaly).toBe(1);
  expect(api.failure).toBe(0);
  expect(api.predictionRequests).toEqual([
    { path: "/predict/anomaly", method: "POST", body: expectedRequestBody },
  ]);

  await page.getByRole("button", { name: "Predict machine failure" }).click();
  const failureStatus = page.getByLabel("Failure classification result").getByRole("status");
  await expect(failureStatus).toContainText("class 1");
  await expect(failureStatus).toContainText("73%");
  await expect(failureStatus).toContainText("uncalibrated, not a calibrated probability or future-failure forecast");
  await expect(failureStatus).toContainText(`equipment ${failureResponse.equipment_id}, reading ${failureResponse.reading_id}`);
  expect(api.failure).toBe(1);
  expect(api.predictionRequests).toEqual([
    { path: "/predict/anomaly", method: "POST", body: expectedRequestBody },
    { path: "/predict/failure", method: "POST", body: expectedRequestBody },
  ]);
});

test("Prediction Lab presents a backend-shaped field validation 422 separately from model unavailable 503", async ({ page }) => {
  let anomalyCalls = 0;
  await installApiMocks(page, {
    anomaly: () => ++anomalyCalls === 1
      ? { status: 422, body: { detail: [{ type: "less_than_equal", loc: ["body", "Torque [Nm]"], msg: "Input should be less than or equal to 100" }] } }
      : { status: 200, body: anomalyResponse },
    failure: () => ({ status: 503, body: { detail: "Failure model is unavailable" } }),
  });
  await page.goto("/prediction-lab");
  await page.getByLabel("Equipment record").selectOption("7");
  await fillValidObservation(page);
  await page.getByRole("button", { name: "Run anomaly detection" }).click();
  const anomalyError = page.getByRole("alert").filter({ hasText: "Anomaly detection failed" });
  await expect(anomalyError).toContainText("Torque:");
  await expect(anomalyError).not.toContainText("101");
  await page.getByRole("button", { name: "Predict machine failure" }).click();
  const failureError = page.getByRole("alert").filter({ hasText: "Failure classification failed" });
  await expect(failureError).toContainText("Failure model is unavailable");
  await expect(failureError).not.toContainText("Input validation failed");
  await expect(page.getByLabel("Prediction results").getByRole("status")).toHaveCount(0);
});

test("a dispatched prediction network failure is not automatically resubmitted", async ({ page }) => {
  const api = await installApiMocks(page, { anomaly: () => "abort" });
  await page.goto("/prediction-lab");
  await page.getByLabel("Equipment record").selectOption("7");
  await fillValidObservation(page);
  await page.getByRole("button", { name: "Run anomaly detection" }).click();
  const alert = page.getByRole("alert").filter({ hasText: "Anomaly detection failed" });
  await expect(alert).toContainText("API may have saved this prediction");
  await expect(alert).toContainText("selected equipment's Prediction History before retrying");
  await expect(page.getByLabel("Prediction results").getByRole("status")).toHaveCount(0);
  expect(api.anomaly).toBe(1);
  expect(api.failure).toBe(0);
});

test("a browser-level prediction timeout remains an unknown outcome and is not resubmitted", async ({ page }) => {
  const api = await installApiMocks(page, { anomaly: () => "timeout" });
  await page.goto("/prediction-lab");
  await page.getByLabel("Equipment record").selectOption("7");
  await fillValidObservation(page);
  await page.getByRole("button", { name: "Run anomaly detection" }).click();
  const alert = page.getByRole("alert").filter({ hasText: "Anomaly detection failed" });
  await expect(alert).toContainText("API may have saved this prediction");
  await expect(alert).toContainText("selected equipment's Prediction History before retrying");
  expect(api.anomaly).toBe(1);
  expect(api.predictionRequests).toEqual([
    {
      path: "/predict/anomaly",
      method: "POST",
      body: {
        Type: "M",
        "Air temperature [K]": 300.2,
        "Process temperature [K]": 310.1,
        "Rotational speed [rpm]": 1450,
        "Torque [Nm]": 38.6,
        "Tool wear [min]": 80,
        equipment_id: 7,
      },
    },
  ]);
});

test("prediction history paginates, opens a saved record, and isolates changed equipment", async ({ page }) => {
  const api = await installApiMocks(page, {
    historyPage: (equipmentId, offset) => {
      if (equipmentId === 8) return { equipment: { id: 8, name: "Lathe B", equipment_type: "L", location: null, created_at: "2026-10-30T10:00:00Z" }, items: [historyEntry(81, 8)] };
      const items = offset === 0
        ? Array.from({ length: 50 }, (_, index) => {
            const id = 50 - index;
            const entry = historyEntry(id, 7);
            if (id === 41) entry.predictions = [predictionSummary(anomalyResponse.prediction_id, "anomaly_v1", "anomaly", anomalyResponse.prediction_timestamp)];
            if (id === 42) entry.predictions = [predictionSummary(failureResponse.prediction_id, "failure_v1", "failure", failureResponse.prediction_timestamp)];
            return entry;
          })
        : [historyEntry(51, 7)];
      if (offset > 0) items[0]!.reading.timestamp = "2026-10-31T09:00:00Z";
      return { equipment: { id: 7, name: "Press A", equipment_type: "M", location: "Line 2", created_at: "2026-10-31T10:00:00Z" }, items };
    },
  });
  await page.goto("/prediction-history");
  await page.getByLabel("Equipment record").selectOption("7");
  const historyList = page.getByRole("region", { name: "Prediction history for equipment 7" });
  await expect(historyList.getByText("SENSOR READING · #50")).toBeVisible();
  await historyList.getByRole("button", { name: "View saved record" }).first().click();
  await expect(page.getByRole("heading", { name: "Prediction details" })).toBeVisible();
  await expect(page.getByText(failureResponse.prediction_id, { exact: true }).first()).toBeVisible();

  await historyList.getByRole("button", { name: "Load older readings" }).click();
  await expect(historyList.getByText("SENSOR READING · #51")).toBeVisible();
  expect(api.history).toBe(2);
  await page.getByLabel("Equipment record").selectOption("8");
  const otherHistory = page.getByRole("region", { name: "Prediction history for equipment 8" });
  await expect(otherHistory.getByText("SENSOR READING · #81")).toBeVisible();
  await expect(otherHistory).not.toContainText("SENSOR READING · #50");
});

test("prediction history renders an empty state and recovers after a history request error", async ({ page }) => {
  let calls = 0;
  await installApiMocks(page, {
    historyPage: (equipmentId) => ++calls === 1
      ? { status: 503, body: { detail: "Database is unavailable" } }
      : { equipment: { id: equipmentId, name: "Press A", equipment_type: "M", location: "Line 2", created_at: "2026-10-31T10:00:00Z" }, items: [] },
  });
  await page.goto("/prediction-history");
  await page.getByLabel("Equipment record").selectOption("7");
  const alert = page.getByRole("alert").filter({ hasText: "Equipment history unavailable" });
  await expect(alert).toBeVisible();
  await alert.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("No readings or predictions for this equipment")).toBeVisible();
});

test("equipment profile exposes chart data through a keyboard-operable disclosure", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/equipment/7");
  const disclosure = page.getByText("View air temperature observations as a table (2)");
  await expect(disclosure).toBeVisible();
  await disclosure.focus();
  await page.keyboard.press("Enter");
  const table = page.getByRole("table", { name: /Air temperature \(K\).*chronological/ });
  await expect(table).toBeVisible();
  await expect(table).toContainText("300.234 K");
  await expect(table).toContainText("Reading ID");
});

test("Drift Monitoring handles a real-shaped latest report, no-report 404, and service failure", async ({ page }) => {
  await installApiMocks(page, { drift: () => ({ status: 200, body: driftResponse }) });
  await page.goto("/drift");
  await expect(page.getByText("LATEST PERSISTED REPORT", { exact: true })).toBeVisible();
  await expect(page.getByText("Input drift detected")).toBeVisible();
  await expect(page.getByText("Air temperature [K]", { exact: false }).first()).toBeVisible();

  await page.reload();
  // Page routes remain registered across reloads; the same latest report is returned.
  await expect(page.getByText("LATEST PERSISTED REPORT", { exact: true })).toBeVisible();
});

test("Drift Monitoring treats 404 as no report and offers retry after endpoint failure", async ({ page }) => {
  let calls = 0;
  await installApiMocks(page, { drift: () => ++calls === 1
    ? { status: 503, body: { detail: "Database is unavailable" } }
    : { status: 404, body: { detail: "No drift report is available" } },
  });
  await page.goto("/drift");
  const error = page.getByRole("alert").filter({ hasText: "Latest drift report unavailable" });
  await expect(error).toBeVisible();
  await error.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("No drift report has been generated yet.")).toBeVisible();
});

test("System Health shows partial readiness and unavailable metrics without claiming healthy", async ({ page }) => {
  await installApiMocks(page, {
    readiness: { status: 503, body: { status: "not_ready", models: { anomaly: true, failure: false }, database: true } },
    metrics: { status: 503, body: { detail: "Database is unavailable" } },
  });
  await page.goto("/system");
  await expect(page.getByText("Reachable, not ready").first()).toBeVisible();
  await expect(page.getByText("Failure model").first()).toBeVisible();
  await expect(page.getByText("Unavailable").first()).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "Operational metrics unavailable" })).toBeVisible();
});

test("System Health marks retained metrics as stale after a failed refresh", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-10-31T12:00:00Z") });
  const api = await installApiMocks(page, {
    metrics: (call) => call === 1
      ? { status: 200, body: metricsResponse }
      : { status: 503, body: { detail: "Database is unavailable" } },
  });
  await page.goto("/system");
  await expect(page.getByRole("region", { name: "Operational metrics" })).toBeVisible();

  // Metrics poll every 30 seconds. Advance the browser clock to the scheduled
  // refresh so this exercises the real stale-data path without an arbitrary wait.
  await page.clock.fastForward(30_100);

  await expect(page.getByText(/Metrics refresh failed\. Showing the last successful snapshot/)).toBeVisible();
  await expect(page.getByText("Requests recorded")).toBeVisible();
  expect(api.metrics).toBe(2);
});

test("keyboard skip navigation and mobile navigation dialog manage focus", async ({ page }) => {
  await installApiMocks(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await skipLink.focus();
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);

  const trigger = page.getByRole("button", { name: "Open navigation" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Mobile navigation" });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("button", { name: "Close navigation" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();

  await trigger.click();
  const reopenedDialog = page.getByRole("dialog", { name: "Mobile navigation" });
  const equipmentLink = reopenedDialog.getByRole("link", { name: "Equipment" });
  await equipmentLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/equipment$/);
  await expect(page.getByRole("heading", { name: "Equipment", exact: true })).toBeVisible();
});

async function fillValidObservation(page: import("@playwright/test").Page) {
  await page.getByRole("combobox", { name: "Type" }).selectOption("M");
  await page.getByLabel(/Air temperature/).fill("300.2");
  await page.getByLabel(/Process temperature/).fill("310.1");
  await page.getByLabel(/Rotational speed/).fill("1450");
  await page.getByLabel(/Torque/).fill("38.6");
  await page.getByLabel(/Tool wear/).fill("80");
}
