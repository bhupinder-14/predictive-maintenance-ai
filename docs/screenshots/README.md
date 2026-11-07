# Genuine application screenshot capture

No application screenshots are included yet. Capture only the real frontend connected to the real local FastAPI backend. Do not use Playwright API fixtures, mocked responses, fabricated UI data, generated images, or edited values as portfolio evidence.

## Safety and scope

- Start and seed the backend only with `python -m scripts.run_screenshot_capture`. Do not launch Uvicorn separately, run the generator directly, use Docker Compose, or use its named volume.
- Use the dedicated disposable SQLite file `%TEMP%\predictive-maintenance-ai-capture\demo.sqlite3`. Set `DATABASE_URL` in the backend process environment before Python starts. The API reads process environment variables; do not change `.env` or other project configuration.
- The launcher refuses an existing database before starting. It sets `DATABASE_URL`, `MODEL_DIR`, and `DRIFT_REFERENCE_PATH` explicitly in the Uvicorn child environment. API startup creates the empty schema. The generator then refuses to proceed if any application rows are present; it never truncates, overwrites, or deletes a database.
- Use the accepted model bundles and drift reference already in the project. No training or artifact generation is part of this procedure.
- The generator uses only the real `/ready`, `/predict/anomaly`, `/predict/failure`, `/monitoring/drift`, and read-only `/monitoring/drift` API endpoints. It submits deterministic, bounded, non-personal synthetic sensor features for `DEMO-CAPTURE-01`.
- The anomaly model returns an Isolation Forest score, not a failure probability. Failure output is an uncalibrated row-level estimator result, not a future forecast. A drift report describes input distribution differences; it does not establish model degradation.

The launcher is now the only approved start-and-seed workflow because a standalone generator cannot establish which environment an already-running Uvicorn process received. It sets the disposable SQLite URL in the child environment, tracks the child PID, rejects port 8000 if occupied, and uses Windows `Get-NetTCPConnection` process ownership data to require that the sole listener is exactly `127.0.0.1` owned by the launched Uvicorn PID. Inspection includes loopback and wildcard IPv4/IPv6 addresses. PowerShell nonzero exits, error output, timeouts, and malformed/incomplete output are inspection failures; they are never interpreted as an empty/free port. Ownership is checked again before generation and while generation runs. `/ready` is checked only after that OS-level ownership check; readiness alone does not prove database identity. The launcher places its Uvicorn and generator children in a Windows job object configured to terminate assigned children if the launcher exits. For assignment it validates and passes the native process handle held by each `subprocess.Popen` instance, rather than reopening a numeric PID. These Windows API behaviors still require native Windows execution validation; unit tests mock the native calls.

The generator is started with a parent-controlled stdin gate and cannot call `/ready` or begin generation while the gate is closed. It first validates the actual OS-reported parent PID, queries the parent's executable and command line, normalizes the executable path against the running project's Python executable, and requires the exact parsed invocation `python -m scripts.run_screenshot_capture`. This check reduces accidental direct invocation; it is not cryptographic authentication or protection against a determined same-user process that deliberately imitates the launcher. The generator then requires exactly `RELEASE_SCREENSHOT_CAPTURE_V1` followed by EOF; missing gate configuration, EOF before the signal, partial or unexpected input, read errors, and timeout all fail closed. The authorization is one-shot, and calling the generator function without consuming it is refused. The launcher assigns the actual generator `Popen` handle to the Job Object, independently verifies the generator's live PID, parent PID, executable and exact parsed command line, then rechecks backend listener ownership, database/model readiness and both child environments' canonical disposable `DATABASE_URL`. It sends the release signal and closes the pipe only after every check passes. Assignment or pre-release verification failure closes the gate and stops the launcher-owned children. Separately launching Uvicorn or the generator is not approved because it bypasses this ordering and handshake.

Authorization state and its transitions are held in a private closure rather than mutable module-level tokens or a setter. The startup handshake is mandatory and one-shot; generation is one-shot as well. Every generator HTTP request is authorized at `_request_json`, not only by the top-level generation flow. Requests are blocked unless the one-shot gate has been consumed and authorized generation is active. The request helper accepts only the canonical `http://127.0.0.1:8000` API base, the approved readiness, prediction and drift paths, and their expected GET/POST methods; alternate hosts, addresses, ports, URL credentials, schemes, query strings, fragments and noncanonical/encoded paths are rejected before `urlopen`.

The parent executable/PID/command-line check reduces accidental direct invocation mistakes; it is not authentication. Python introspection can inspect closure state, and a determined same-user process can imitate ordinary process details. This workflow is not a security boundary against that threat or a local administrator.

Before writes, the generator verifies its immediate parent PID against the launcher PID and confirms through Windows process inspection that the parent's command line is the launcher script. It then checks its inherited URL, requires all four app tables to be empty, and verifies the active `DRIFT_MINIMUM_SAMPLE_SIZE` does not exceed the 20-row batch. It checks both models and the database are ready before prediction calls, rejects an `insufficient_data` drift response, and verifies final table counts. Its immediate pre-run SHA-256 baseline includes the project DB path (including an absent-file state), six model artifacts, drift reference, raw source CSV, and any existing files under `data/processed`. Required model/reference/source files are separately checked for presence. These checks can detect changes during this run; they do not attest to a historical baseline. The workflow never accesses or claims protection of the Docker volume.

## Exact procedure

Open two PowerShell terminals. Use the project's existing Python environment and installed frontend dependencies; do not install or update packages as part of capture.

### 1. Confirm the dedicated path is unused

```powershell
$demoDb = Join-Path $env:TEMP 'predictive-maintenance-ai-capture\demo.sqlite3'
if (Test-Path -LiteralPath $demoDb) { throw "Refusing existing database: $demoDb" }
```

This is a pre-start check. Do not remove an existing file to make the check pass; choose a separately reviewed disposable location only after updating the capture procedure and generator together.

### 2. Start and seed through the trusted launcher

In terminal 1, from the project root with the project's Python environment activated. The launcher owns the complete backend startup, ownership check, readiness check, and generator invocation:

```powershell
python -m scripts.run_screenshot_capture
```

Keep this terminal open. Backend stdout/stderr remain visible. After generating and verifying records, the launcher keeps Uvicorn alive for browser capture. Do not separately run `python -m uvicorn` or `scripts.prepare_screenshot_demo`; the generator verifies its launcher parent PID and process command line and receives the same explicit database URL. If startup/readiness, PID ownership, or job setup fails, the launcher stops its own child and does not make prediction or drift calls.

### 3. Start the real frontend

In terminal 2, from the repository root:

```powershell
Set-Location .\frontend
$env:API_PROXY_TARGET = 'http://127.0.0.1:8000'
npm run dev
```

Open `http://127.0.0.1:5173`. Browser calls use same-origin `/api`; Vite strips `/api` and proxies to the backend.

The launcher’s child generator makes 10 anomaly and 10 failure calls for the same named equipment, producing 20 persisted readings/predictions, then submits a 20-row controlled drift batch and reads back its persisted report. It prints the actual classifications/status returned by the models. Those outputs are data-dependent; the script does not promise that a specific sensor row will be labelled anomalous or a failure.

The generator refuses an already populated database. If a request fails partway through, the generator reports successful prediction responses, current disposable table counts, and protected-file fingerprint differences from the pre-run baseline. It preserves the original request error, does not roll back prior successful API requests, and does not clean up automatically. The launcher then shuts down only its tracked children. Inspect the emitted partial counts before deciding what to do; do not rerun against a non-empty file. A startup failure after Uvicorn begins can leave an empty initialized SQLite file; the launcher never removes it, so use the separate cleanup tool after confirming port 8000 is no longer listening.

### 5. Verify persisted records and untouched project files

The generator performs read-only SQLite checks and SHA-256 comparisons after successful generation and also reports file changes on request failure. Expected final counts:

| Table | Expected rows |
| --- | ---: |
| `equipment` | 1 |
| `sensor_readings` | 20 |
| `predictions` | 20 |
| `monitoring_reports` | 1 |

Also verify live responses in a browser or PowerShell without sending writes:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/equipment
Invoke-RestMethod http://127.0.0.1:8000/equipment/1/history
Invoke-RestMethod http://127.0.0.1:8000/monitoring/drift
Invoke-RestMethod http://127.0.0.1:8000/monitoring/metrics
```

The generated equipment ID is normally 1 in a fresh database; use the ID returned by `GET /equipment` if it differs. All browser pages must show live backend data through Vite. Do not use the mocked Playwright suite as screenshot evidence.

### 6. Capture the eight genuine screens

Recommended desktop viewport is **1440 × 1000 CSS pixels** for the first seven captures. Use **390 × 844 CSS pixels** for the mobile capture. Record the actual dimensions and local capture date with the resulting image. Keep errors, empty states, loading states, and data limitations truthful; do not edit the resulting screenshot.

| Filename | Frontend route | Required live data and UI state | Viewport |
| --- | --- | --- | --- |
| `overview.png` | `/` | Backend readiness, live process-local metrics, and saved latest drift report. The global activity-feed panel is honestly empty because the API has no global feed. Caption that metrics reset on process restart and identify the rolling window. | 1440 × 1000 |
| `equipment-explorer.png` | `/equipment` | `GET /equipment` returns `DEMO-CAPTURE-01`; show its metadata. Note search covers currently loaded records and API has no total count. | 1440 × 1000 |
| `equipment-profile.png` | `/equipment/1` (or returned ID) | `GET /equipment/{id}/history` has persisted readings; show latest reading, trends and loaded coverage. State these are persisted observations, not continuous telemetry. | 1440 × 1000 |
| `prediction-lab.png` | `/prediction-lab` | Use the form to submit one actual anomaly action and one separate actual failure action for the demo equipment. Keep Isolation Forest score and uncalibrated failure estimator labels visible. | 1440 × 1000 |
| `prediction-history.png` | `/prediction-history` | Select `DEMO-CAPTURE-01`; show its persisted readings and model outputs, optionally open a saved record, and retain equipment-scoped/pagination context. | 1440 × 1000 |
| `drift-monitoring.png` | `/drift` | Show the latest report generated from the 20-row controlled batch, including feature-level results and thresholds. State that only the latest report is shown and drift does not prove reduced model accuracy. | 1440 × 1000 |
| `system-health.png` | `/system` | Actual `/health`, `/ready`, and metrics response. Label metrics process-local and avoid implying lifetime factory totals. | 1440 × 1000 |
| `mobile-navigation.png` | `/` | Actual responsive frontend with navigation dialog open; show keyboard/focus only if intentionally arranged and verified. Screenshot alone does not establish keyboard or screen-reader accessibility. | 390 × 844 |

The 20 records are deterministic synthetic inputs, not factory telemetry. The drift request evaluates the same controlled feature batch; it does not create readings. The lab screenshot should use actual live form submissions and actual returned model results, not copied generator output.

### 7. Stop services and optional manual cleanup

Stop the frontend with **Ctrl+C** in terminal 2. Stop backend and launcher with **Ctrl+C** in terminal 1. The launcher terminates only its tracked child PID; the Windows job object also covers launcher termination. The generator never deletes the database. Keep it until review/capture is complete.

If cleanup is approved later, run this separate command after stopping the launcher. The cleanup utility normalizes the supplied path and requires exact equality with the canonical `demo.sqlite3` under the dedicated capture directory. It refuses cleanup if any IPv4/IPv6 loopback or wildcard listener is found, or if Windows listener inspection fails or is ambiguous. It checks that the target is a file in that directory and not the project DB, and requires typing `DELETE`. It unlinks only the file; it does not recurse, remove the containing directory, or interact with a Docker volume:

```powershell
$demoDb = Join-Path $env:TEMP 'predictive-maintenance-ai-capture\demo.sqlite3'
python -m scripts.cleanup_screenshot_capture --database-path $demoDb
```

Never substitute a project path, wildcard, recursive delete, or Docker volume command.

## Capture record

When adding approved images to this directory, record capture date, viewport, use of the disposable database, live backend source, any loading/stale/partial state, and interpretation limitations. A screenshot demonstrates rendered UI behavior; it does not prove persistence, model quality, production operation, or accessibility conformance.
