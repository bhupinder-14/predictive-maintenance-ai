"""Explicitly seed the isolated screenshot database through the real local API.

Use scripts/run_screenshot_capture.py to start the backend and invoke this
generator. This script never creates, initializes, truncates, or deletes a DB.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import sqlite3
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from scripts.run_screenshot_capture import (
    exact_python_module_invocation,
    inspect_windows_process,
    normalize_executable_path,
)
from src.config import DRIFT_MINIMUM_SAMPLE_SIZE

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EQUIPMENT_NAME = "DEMO-CAPTURE-01"
EQUIPMENT_LOCATION = "Demo line A"
OBSERVATION_COUNT = 20
_CANONICAL_API_BASE_URL = "http://127.0.0.1:8000"
API_BASE_URL = _CANONICAL_API_BASE_URL
GATE_ENVIRONMENT_KEY = "SCREENSHOT_CAPTURE_GATE"
GATE_ENVIRONMENT_VALUE = "stdin-v1"
GATE_RELEASE_SIGNAL = b"RELEASE_SCREENSHOT_CAPTURE_V1\n"
GATE_READ_TIMEOUT_SECONDS = 120.0
_ALLOWED_API_METHODS = {
    "/ready": frozenset({"GET"}),
    "/predict/anomaly": frozenset({"POST"}),
    "/predict/failure": frozenset({"POST"}),
    "/monitoring/drift": frozenset({"GET", "POST"}),
}


def disposable_database_path() -> Path:
    """Return the one documented, user-temp capture database path."""
    return (Path(os.environ["TEMP"]) / "predictive-maintenance-ai-capture" / "demo.sqlite3").resolve()


def sqlite_url(path: Path) -> str:
    """Build SQLAlchemy's absolute Windows SQLite URL form."""
    return f"sqlite:///{path.resolve().as_posix()}"


def observations() -> list[dict[str, str | float]]:
    """Return 20 deterministic, bounded, non-personal synthetic sensor rows."""
    types = ("L", "M", "H")
    speeds = (1050, 1250, 1450, 1650, 1850, 2100, 2350, 2600, 2850, 3000)
    torques = (15, 25, 35, 45, 55, 65, 75, 85, 95, 10)
    rows: list[dict[str, str | float]] = []
    for index in range(OBSERVATION_COUNT):
        air = 293.0 + (index % 5) * 3.5
        rows.append({
            "Type": types[index % len(types)],
            "Air temperature [K]": air,
            "Process temperature [K]": air + 10.5,
            "Rotational speed [rpm]": speeds[index % len(speeds)],
            "Torque [Nm]": torques[index % len(torques)],
            "Tool wear [min]": float((index * 17) % 300),
        })
    return rows


def protected_files() -> list[Path]:
    """List protected file baselines, including extant processed artifacts."""
    fixed = [
        PROJECT_ROOT / "predictive_maintenance.db",
        *(PROJECT_ROOT / "models" / name for name in (
            "anomaly_v1_estimator.joblib", "anomaly_v1_preprocessor.joblib",
            "anomaly_v1_metadata.json", "failure_v1_estimator.joblib",
            "failure_v1_preprocessor.joblib", "failure_v1_metadata.json",
        )),
        PROJECT_ROOT / "data" / "reference" / "drift_reference_v1.json",
        PROJECT_ROOT / "data" / "raw" / "ai4i2020.csv",
    ]
    processed = PROJECT_ROOT / "data" / "processed"
    if processed.is_dir():
        fixed.extend(path for path in processed.rglob("*") if path.is_file())
    return fixed


def file_fingerprints(paths: list[Path]) -> dict[str, str | None]:
    """Hash files that exist; `None` records a checked but absent path."""
    result: dict[str, str | None] = {}
    for path in paths:
        result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return result


def verify_launcher_parent() -> None:
    """Check the actual immediate parent against the expected Python launcher."""
    if os.name != "nt":
        raise RuntimeError("Demo generation is permitted only under the Windows capture launcher.")
    try:
        expected_pid = int(os.environ["SCREENSHOT_LAUNCHER_PID"])
    except (KeyError, ValueError) as exc:
        raise RuntimeError("Missing trusted launcher process identity.") from exc
    parent_pid = os.getppid()
    if parent_pid != expected_pid:
        raise RuntimeError("Generator parent PID does not match the trusted launcher PID.")
    try:
        identity = inspect_windows_process(parent_pid)
        actual_parent_pid = int(identity["ProcessId"])
        executable = identity["ExecutablePath"]
        command_line = identity["CommandLine"]
    except (KeyError, TypeError, ValueError, RuntimeError, OSError) as exc:
        raise RuntimeError(f"Could not validate generator parent process: {exc}") from exc
    if (actual_parent_pid != parent_pid
            or normalize_executable_path(executable) != normalize_executable_path(sys.executable)
            or not exact_python_module_invocation(command_line, "scripts.run_screenshot_capture")):
        raise RuntimeError("Generator was not launched directly by scripts.run_screenshot_capture.")


def _bounded_gate_read(operation, deadline: float):
    result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def read_operation() -> None:
        try:
            result_queue.put((True, operation()))
        except BaseException as exc:
            result_queue.put((False, exc))

    reader = threading.Thread(target=read_operation, name="screenshot-gate-reader", daemon=True)
    reader.start()
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Timed out waiting for the launcher startup gate.")
    try:
        succeeded, value = result_queue.get(timeout=remaining)
    except queue.Empty as exc:
        raise TimeoutError("Timed out waiting for the launcher startup gate.") from exc
    if not succeeded:
        raise value
    return value


def _make_authorization_controller():
    """Create gate and generation transitions with state held only in a closure."""
    pending, waiting, granted, active, used = (object() for _ in range(5))
    state = pending

    def wait_for_release() -> None:
        nonlocal state
        if state is not pending:
            raise RuntimeError("The launcher startup gate has already been attempted or consumed.")
        state = waiting
        try:
            # Parent identity is checked as part of the one-shot gate transition.
            verify_launcher_parent()
            if os.environ.get(GATE_ENVIRONMENT_KEY) != GATE_ENVIRONMENT_VALUE:
                raise RuntimeError("Missing or invalid launcher-controlled startup gate.")
            source = sys.stdin.buffer
            deadline = time.monotonic() + GATE_READ_TIMEOUT_SECONDS
            signal = _bounded_gate_read(lambda: source.readline(len(GATE_RELEASE_SIGNAL) + 1), deadline)
            if signal != GATE_RELEASE_SIGNAL:
                raise RuntimeError("Startup gate did not receive the exact launcher release signal.")
            trailing = _bounded_gate_read(lambda: source.read(1), deadline)
            if trailing != b"":
                raise RuntimeError("Startup gate received unexpected trailing input; refusing release.")
        except BaseException:
            state = used
            raise
        state = granted

    def require_active() -> None:
        if state is not active:
            raise RuntimeError("HTTP requests require an active one-shot launcher authorization.")

    def generate_once() -> None:
        nonlocal state
        if state is not granted:
            raise RuntimeError("Generator is blocked until the launcher releases its startup gate.")
        state = active

        try:
            _generate_authorized()
        finally:
            state = used

    return wait_for_release, require_active, generate_once


(
    wait_for_launcher_release,
    _require_active_authorization,
    generate,
) = _make_authorization_controller()


def _fingerprint_differences(before: dict[str, str | None]) -> list[str]:
    after = file_fingerprints(protected_files())
    paths = set(before) | set(after)
    return [path for path in sorted(paths) if before.get(path) != after.get(path)]


def _validate_api_request(url: str, payload: dict | None) -> str:
    _require_active_authorization()
    if not isinstance(url, str):
        raise RuntimeError("API target must be a canonical loopback URL.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("Malformed API URL; refusing request.") from exc
    method = "GET" if payload is None else "POST"
    if (parsed.scheme != "http" or parsed.netloc != "127.0.0.1:8000"
            or parsed.hostname != "127.0.0.1" or port != 8000
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in _ALLOWED_API_METHODS
            or method not in _ALLOWED_API_METHODS.get(parsed.path, ())
            or url != f"{_CANONICAL_API_BASE_URL}{parsed.path}"):
        raise RuntimeError("Only approved HTTP endpoints on 127.0.0.1:8000 are permitted.")
    return f"{_CANONICAL_API_BASE_URL}{parsed.path}"


def _request_json(url: str, *, payload: dict | None = None) -> tuple[int, dict]:
    url = _validate_api_request(url, payload)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{request.method} {url} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach local API at {url}: {exc.reason}") from exc


def _bind_request_boundary(request, require_active, validate_request):
    """Capture the authorization and validator closures at module initialization."""
    def authorized_request(url: str, *, payload: dict | None = None) -> tuple[int, dict]:
        require_active()
        safe_url = validate_request(url, payload)
        return request(safe_url, payload=payload)

    return authorized_request


# The boundary retains direct references to the closure-held guard and original
# validator so assigning similarly named module attributes cannot grant access.
_request_json = _bind_request_boundary(
    _request_json,
    _require_active_authorization,
    _validate_api_request,
)


def _database_counts(path: Path) -> dict[str, int]:
    if not path.is_file():
        raise RuntimeError(f"Disposable database does not exist: {path}")
    uri = f"file:{quote(path.as_posix(), safe='/:')}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"equipment", "sensor_readings", "predictions", "monitoring_reports"}
            if not required.issubset(tables):
                raise RuntimeError("Database schema is incomplete; start it only through the screenshot launcher.")
            return {
                table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in sorted(required)
            }
    except sqlite3.Error as exc:
        raise RuntimeError(f"Could not inspect disposable SQLite database: {exc}") from exc


def _verify_demo_records(path: Path) -> None:
    uri = f"file:{quote(path.as_posix(), safe='/:')}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        equipment = connection.execute("SELECT name FROM equipment ORDER BY id").fetchall()
        model_counts = dict(connection.execute(
            "SELECT model_version, COUNT(*) FROM predictions GROUP BY model_version"
        ).fetchall())
        report = connection.execute(
            "SELECT reference_version, report_metadata FROM monitoring_reports ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if equipment != [(EQUIPMENT_NAME,)]:
        raise RuntimeError(f"Disposable database equipment identity was unexpected: {equipment}")
    if model_counts != {"anomaly_v1": 10, "failure_v1": 10}:
        raise RuntimeError(f"Persisted prediction model counts were unexpected: {model_counts}")
    if report is None or report[0] != "drift_reference_v1":
        raise RuntimeError("The expected drift report/reference was not found in the disposable database.")


def preflight() -> tuple[Path, dict[str, str | None]]:
    verify_launcher_parent()
    if not os.environ.get("TEMP"):
        raise RuntimeError("TEMP is not set; refusing to guess a disposable database location.")
    database_path = disposable_database_path()
    expected_url = sqlite_url(database_path)
    configured_url = os.environ.get("DATABASE_URL", "")
    if configured_url != expected_url:
        raise RuntimeError(
            "DATABASE_URL must exactly match the dedicated disposable path. "
            f"Expected: {expected_url}"
        )
    project_database = (PROJECT_ROOT / "predictive_maintenance.db").resolve()
    if database_path == project_database or PROJECT_ROOT in database_path.parents:
        raise RuntimeError("Disposable database path must be outside the project directory.")
    if not database_path.exists():
        raise RuntimeError("The launcher must initialize the empty disposable schema before generation.")
    counts = _database_counts(database_path)
    if any(counts.values()):
        raise RuntimeError(f"Refusing to add or overwrite records in a non-empty database: {counts}")

    minimum = DRIFT_MINIMUM_SAMPLE_SIZE
    if OBSERVATION_COUNT < minimum:
        raise RuntimeError(
            f"Planned drift batch has {OBSERVATION_COUNT} rows, below configured minimum {minimum}; no writes attempted."
        )

    project_database = (PROJECT_ROOT / "predictive_maintenance.db").resolve()
    required = [path for path in protected_files() if path.resolve() != project_database]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Required models, reference, or source data are missing: " + ", ".join(missing))
    # Baseline is taken immediately before calls. Required files are checked
    # above; the root DB and processed files may validly be absent at baseline.
    return database_path, file_fingerprints(protected_files())


def _failure_context(
    original: BaseException,
    successful_predictions: int,
    drift_response_received: bool,
    database_path: Path,
    before: dict[str, str | None],
) -> str:
    try:
        counts = _database_counts(database_path)
        count_text = str(counts)
    except Exception as inspect_error:
        count_text = f"unavailable ({type(inspect_error).__name__}: {inspect_error})"
    try:
        differences = _fingerprint_differences(before)
        difference_text = ", ".join(differences) if differences else "none observed"
    except Exception as fingerprint_error:
        difference_text = f"verification failed ({type(fingerprint_error).__name__}: {fingerprint_error})"
    return (
        f"Original failure: {type(original).__name__}: {original}. "
        f"Successful prediction responses: {successful_predictions}/{OBSERVATION_COUNT}; "
        f"drift response received: {drift_response_received}. "
        f"Disposable database counts (records are not rolled back): {count_text}. "
        f"Protected-file fingerprint differences from the pre-run baseline: {difference_text}. "
        "No records were deleted or rolled back."
    )


def _generate_authorized() -> None:
    _require_active_authorization()
    database_path, before = preflight()
    successful_predictions = 0
    drift_response_received = False
    try:
        status, readiness = _request_json(f"{API_BASE_URL}/ready")
        if status != 200:
            raise RuntimeError(f"Backend readiness returned HTTP {status}; no writes attempted.")
        if (readiness.get("status") != "ready" or readiness.get("database") is not True
                or readiness.get("models") != {"anomaly": True, "failure": True}):
            raise RuntimeError(f"Backend is not fully ready; no writes attempted: {readiness}")

        rows = observations()
        outcomes = {"anomaly": [], "failure": []}
        for index, row in enumerate(rows):
            payload = {**row, "equipment_name": EQUIPMENT_NAME, "equipment_location": EQUIPMENT_LOCATION}
            model = "anomaly" if index % 2 == 0 else "failure"
            _, result = _request_json(f"{API_BASE_URL}/predict/{model}", payload=payload)
            successful_predictions += 1
            if result.get("model_version") != ("anomaly_v1" if model == "anomaly" else "failure_v1"):
                raise RuntimeError(f"Unexpected model version in {model} response: {result}")
            outcomes[model].append(result)

        _, drift = _request_json(
            f"{API_BASE_URL}/monitoring/drift",
            payload={"observations": rows},
        )
        drift_response_received = True
        if drift.get("overall_status") == "insufficient_data":
            raise RuntimeError(
                "Drift report returned insufficient_data despite the configured sample preflight."
            )
        _, saved_drift = _request_json(f"{API_BASE_URL}/monitoring/drift")

        counts = _database_counts(database_path)
        expected_counts = {"equipment": 1, "sensor_readings": OBSERVATION_COUNT,
                           "predictions": OBSERVATION_COUNT, "monitoring_reports": 1}
        if counts != expected_counts:
            raise RuntimeError(f"Disposable database counts did not match expected writes: {counts}")
        _verify_demo_records(database_path)
        if saved_drift.get("report_id") != drift.get("report_id"):
            raise RuntimeError("Latest persisted drift report did not match the generated report.")
    except BaseException as original:
        context = _failure_context(
            original, successful_predictions, drift_response_received, database_path, before
        )
        if isinstance(original, Exception):
            raise RuntimeError(context) from original
        original.add_note(context)
        raise

    differences = _fingerprint_differences(before)
    if differences:
        raise RuntimeError(
            "Protected-file fingerprint differences from the pre-run baseline: "
            + ", ".join(differences)
        )
    anomaly_classes = {str(item.get("classification")) for item in outcomes["anomaly"]}
    failure_classes = {str(item.get("predicted_class")) for item in outcomes["failure"]}
    print(f"Disposable database verified: {database_path}")
    print(f"Records verified: {counts}")
    print(f"Equipment: {EQUIPMENT_NAME}; model API calls: 10 anomaly, 10 failure")
    print(f"Observed anomaly classifications: {sorted(anomaly_classes)}")
    print(f"Observed failure estimator classes: {sorted(failure_classes)}")
    print("Anomaly scores are Isolation Forest scores, not failure probabilities.")
    print("Failure estimator outputs are uncalibrated row-level estimates, not future forecasts.")
    print(f"Drift report: {saved_drift.get('overall_status')} ({saved_drift.get('current_sample_size')} observations)")
    print("Files fingerprinted before/after: project DB path, six model artifacts, reference, raw CSV, and extant processed files.")
    print("The Docker volume is not used or covered by these checks. No database cleanup was performed.")


def main() -> int:
    try:
        # The gate transition performs the parent check before it reads input.
        wait_for_launcher_release()
        generate()
    except Exception as exc:
        print(f"Screenshot demo preparation stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
