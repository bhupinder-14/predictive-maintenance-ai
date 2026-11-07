"""Isolated safety checks for screenshot capture preparation and cleanup."""

import socket
import sqlite3
import subprocess
import io
import importlib
import json
import shlex
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import cleanup_screenshot_capture as cleanup
from scripts import prepare_screenshot_demo as demo
from scripts import run_screenshot_capture as launcher


def _inspection(*listeners):
    return launcher.ListenerInspection.success(tuple(listeners))


def _listener(address="127.0.0.1", pid=101):
    return launcher.TcpListener(address, pid)


def _schema(path: Path, *, populated: bool = False) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE equipment (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE sensor_readings (id INTEGER PRIMARY KEY);
            CREATE TABLE predictions (id TEXT PRIMARY KEY);
            CREATE TABLE monitoring_reports (id INTEGER PRIMARY KEY);
        """)
        if populated:
            connection.execute("INSERT INTO equipment (name) VALUES ('existing')")


def _demo_env(monkeypatch, temp: Path, *, database_url: str | None = None) -> Path:
    importlib.reload(demo)
    target = (temp / "predictive-maintenance-ai-capture" / "demo.sqlite3").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    _schema(target)
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("SCREENSHOT_LAUNCHER_PID", "test-only-pid")
    monkeypatch.setattr(demo, "verify_launcher_parent", lambda: None)
    monkeypatch.setenv(demo.GATE_ENVIRONMENT_KEY, demo.GATE_ENVIRONMENT_VALUE)
    monkeypatch.setattr(demo.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(demo.GATE_RELEASE_SIGNAL)))
    demo.wait_for_launcher_release()
    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)
    return target


def _fresh_gate(monkeypatch, gate_bytes: bytes, *, gate_value: str | None = "stdin-v1") -> None:
    """Start a fresh module instance and consume authorization through its gate."""
    importlib.reload(demo)
    monkeypatch.setattr(demo, "verify_launcher_parent", lambda: None)
    if gate_value is None:
        monkeypatch.delenv(demo.GATE_ENVIRONMENT_KEY, raising=False)
    else:
        monkeypatch.setenv(demo.GATE_ENVIRONMENT_KEY, gate_value)
    monkeypatch.setattr(demo.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(gate_bytes)))


def _no_real_protected_paths(monkeypatch) -> None:
    monkeypatch.setattr(demo, "protected_files", lambda: [])


def test_demo_observations_are_deterministic_and_within_api_bounds():
    rows = demo.observations()
    assert rows == demo.observations()
    assert len(rows) == demo.OBSERVATION_COUNT == 20
    assert {row["Type"] for row in rows} == {"L", "M", "H"}
    for row in rows:
        assert 290 <= row["Air temperature [K]"] <= 310
        assert 300 <= row["Process temperature [K]"] <= 320
        assert 1000 <= row["Rotational speed [rpm]"] <= 3000
        assert 0 <= row["Torque [Nm]"] <= 100
        assert 0 <= row["Tool wear [min]"] <= 300


def test_sqlite_url_uses_absolute_windows_path_form():
    assert demo.sqlite_url(Path("C:/capture/demo.sqlite3")) == "sqlite:///C:/capture/demo.sqlite3"


@pytest.mark.parametrize("database_url", [None, "sqlite:///wrong.db"])
def test_preflight_rejects_missing_or_incorrect_database_url(monkeypatch, tmp_path, database_url):
    _demo_env(monkeypatch, tmp_path, database_url=database_url)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        demo.preflight()


def test_launcher_refuses_existing_disposable_database(tmp_path):
    target = launcher.canonical_database_path(tmp_path)
    target.parent.mkdir(parents=True)
    target.touch()
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        launcher.build_backend_environment({}, temp_root=tmp_path)


def test_launcher_sets_exact_database_and_project_artifact_paths(tmp_path):
    environment, target = launcher.build_backend_environment(
        {"MODEL_DIR": "wrong-models", "DRIFT_REFERENCE_PATH": "wrong-reference.json"},
        temp_root=tmp_path,
    )
    assert environment["DATABASE_URL"] == demo.sqlite_url(target)
    assert Path(environment["MODEL_DIR"]) == (launcher.PROJECT_ROOT / "models").resolve()
    assert Path(environment["DRIFT_REFERENCE_PATH"]) == (
        launcher.PROJECT_ROOT / "data" / "reference" / "drift_reference_v1.json"
    ).resolve()


def test_generator_refuses_populated_disposable_database(monkeypatch, tmp_path):
    target = (tmp_path / "predictive-maintenance-ai-capture" / "demo.sqlite3").resolve()
    target.parent.mkdir(parents=True)
    _schema(target, populated=True)
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("SCREENSHOT_LAUNCHER_PID", "test-only-pid")
    monkeypatch.setattr(demo, "verify_launcher_parent", lambda: None)
    monkeypatch.setenv("DATABASE_URL", demo.sqlite_url(target))
    with pytest.raises(RuntimeError, match="non-empty"):
        demo.preflight()


def test_generator_requires_launcher_invocation(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.delenv("SCREENSHOT_LAUNCHER_PID", raising=False)
    with pytest.raises(RuntimeError, match="Missing trusted launcher process identity"):
        demo.verify_launcher_parent()


def test_port_already_occupied_is_rejected():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match="not available"):
            launcher.assert_port_available("127.0.0.1", port)


def test_launcher_rejects_backend_child_pid_that_does_not_own_port():
    with pytest.raises(RuntimeError, match="do not exactly match"):
        launcher.verify_port_owner(101, lambda _host, _port: _inspection(_listener(pid=202)))


def test_launcher_refuses_when_port_ownership_cannot_be_inspected():
    with pytest.raises(RuntimeError, match="inspection unavailable"):
        launcher.verify_port_owner(101, lambda *_: launcher.ListenerInspection.failure("inspection unavailable"))


class _FakeProcess:
    pid = 101
    returncode = None

    def poll(self):
        return self.returncode


@pytest.mark.parametrize("status,payload", [
    (503, {"status": "not_ready", "models": {"anomaly": False, "failure": True}, "database": True}),
    (200, {"status": "ready", "models": {"anomaly": False, "failure": True}, "database": True}),
    (200, {"status": "ready", "models": {"anomaly": True, "failure": True}, "database": False}),
])
def test_launcher_refuses_readiness_failure_or_missing_dependency(monkeypatch, status, payload):
    monkeypatch.setattr(launcher, "verify_port_owner", lambda _pid, _probe: None)
    with pytest.raises(RuntimeError, match="readiness|fully ready"):
        launcher.wait_for_backend(
            _FakeProcess(), timeout=1, owner_probe=lambda _host, _port: _inspection(_listener()),
            readiness_probe=lambda: (status, payload),
        )


def test_launcher_fails_if_child_exits_unexpectedly():
    child = _FakeProcess()
    child.returncode = 3
    with pytest.raises(RuntimeError, match="exited during startup"):
        launcher.wait_for_backend(child, owner_probe=lambda *_: _inspection())


def test_drift_minimum_above_batch_fails_before_requests(monkeypatch, tmp_path):
    target = _demo_env(monkeypatch, tmp_path, database_url="placeholder")
    monkeypatch.setenv("DATABASE_URL", demo.sqlite_url(target))
    monkeypatch.setattr(demo, "DRIFT_MINIMUM_SAMPLE_SIZE", demo.OBSERVATION_COUNT + 1)
    _no_real_protected_paths(monkeypatch)
    monkeypatch.setattr(demo, "_request_json", lambda *_args, **_kwargs: pytest.fail("API called before drift preflight"))
    with pytest.raises(RuntimeError, match="below configured minimum"):
        demo.generate()


def test_insufficient_data_drift_report_is_rejected(monkeypatch, tmp_path):
    target = _demo_env(monkeypatch, tmp_path, database_url="placeholder")
    monkeypatch.setenv("DATABASE_URL", demo.sqlite_url(target))
    monkeypatch.setattr(demo, "DRIFT_MINIMUM_SAMPLE_SIZE", demo.OBSERVATION_COUNT)
    _no_real_protected_paths(monkeypatch)
    calls = 0

    def request(_url, *, payload=None):
        nonlocal calls
        calls += 1
        if _url.endswith("/ready"):
            return 200, {"status": "ready", "models": {"anomaly": True, "failure": True}, "database": True}
        if _url.endswith("/monitoring/drift"):
            return 200, {"overall_status": "insufficient_data", "current_sample_size": 20}
        model = "anomaly_v1" if "/anomaly" in _url else "failure_v1"
        return 200, {"model_version": model}

    monkeypatch.setattr(demo, "_request_json", request)
    monkeypatch.setattr(demo, "_fingerprint_differences", lambda _before: [])
    with pytest.raises(RuntimeError, match="insufficient_data"):
        demo.generate()
    assert calls == 22  # readiness + 20 predictions + rejected drift result


def test_partial_prediction_failure_reports_count_and_fingerprint_diff(monkeypatch, tmp_path):
    target = _demo_env(monkeypatch, tmp_path, database_url="placeholder")
    monkeypatch.setenv("DATABASE_URL", demo.sqlite_url(target))
    monkeypatch.setattr(demo, "DRIFT_MINIMUM_SAMPLE_SIZE", demo.OBSERVATION_COUNT)
    protected = tmp_path / "protected-model.json"
    protected.write_text("baseline", encoding="utf-8")
    monkeypatch.setattr(demo, "protected_files", lambda: [protected])
    calls = 0
    diff_calls = []

    def request(url, *, payload=None):
        nonlocal calls
        calls += 1
        if url.endswith("/ready"):
            return 200, {"status": "ready", "models": {"anomaly": True, "failure": True}, "database": True}
        if calls == 5:
            protected.write_text("changed-during-run", encoding="utf-8")
            raise RuntimeError("synthetic API failure")
        model = "anomaly_v1" if "/anomaly" in url else "failure_v1"
        return 200, {"model_version": model}

    monkeypatch.setattr(demo, "_request_json", request)
    real_differences = demo._fingerprint_differences
    monkeypatch.setattr(demo, "_fingerprint_differences", lambda before: diff_calls.append(before) or real_differences(before))
    with pytest.raises(RuntimeError) as error:
        demo.generate()
    message = str(error.value)
    assert "Successful prediction responses: 3/20" in message
    assert "synthetic API failure" in message
    assert str(protected) in message
    assert diff_calls


def test_partial_drift_failure_reports_completed_predictions_and_hash_check(monkeypatch, tmp_path):
    target = _demo_env(monkeypatch, tmp_path, database_url="placeholder")
    monkeypatch.setenv("DATABASE_URL", demo.sqlite_url(target))
    monkeypatch.setattr(demo, "DRIFT_MINIMUM_SAMPLE_SIZE", demo.OBSERVATION_COUNT)
    _no_real_protected_paths(monkeypatch)
    diff_calls = []

    def request(url, *, payload=None):
        if url.endswith("/ready"):
            return 200, {"status": "ready", "models": {"anomaly": True, "failure": True}, "database": True}
        if url.endswith("/monitoring/drift"):
            raise RuntimeError("synthetic drift failure")
        model = "anomaly_v1" if "/anomaly" in url else "failure_v1"
        return 200, {"model_version": model}

    monkeypatch.setattr(demo, "_request_json", request)
    monkeypatch.setattr(demo, "_fingerprint_differences", lambda before: diff_calls.append(before) or ["reference.json"])
    with pytest.raises(RuntimeError) as error:
        demo.generate()
    assert "Successful prediction responses: 20/20" in str(error.value)
    assert "synthetic drift failure" in str(error.value)
    assert "reference.json" in str(error.value)
    assert diff_calls


def test_cleanup_rejects_unexpected_path(tmp_path):
    outside = tmp_path / "other.sqlite3"
    outside.touch()
    with pytest.raises(RuntimeError, match="unexpected cleanup path"):
        cleanup.cleanup_database(
            outside, temp_root=tmp_path, owner_probe=lambda *_: _inspection(), confirmation="DELETE"
        )
    assert outside.exists()


def test_cleanup_refuses_running_backend_and_preserves_file(tmp_path):
    target = launcher.canonical_database_path(tmp_path)
    target.parent.mkdir(parents=True)
    target.touch()
    with pytest.raises(RuntimeError, match="still owns"):
        cleanup.cleanup_database(
            target, temp_root=tmp_path, owner_probe=lambda *_: _inspection(_listener(pid=777)), confirmation="DELETE"
        )
    assert target.exists()


def test_cleanup_requires_explicit_confirmation(tmp_path):
    target = launcher.canonical_database_path(tmp_path)
    target.parent.mkdir(parents=True)
    target.touch()
    with pytest.raises(RuntimeError, match="cancelled"):
        cleanup.cleanup_database(
            target, temp_root=tmp_path, owner_probe=lambda *_: _inspection(), confirmation="no"
        )
    assert target.exists()


def _powershell_result(monkeypatch, stdout, *, code=0, stderr=""):
    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(launcher.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], code, stdout=stdout, stderr=stderr
    ))


def test_listener_inspection_successful_empty_is_distinct(monkeypatch):
    _powershell_result(monkeypatch, "CAPTURE_RESULT:BEGIN\nCAPTURE_RESULT:END\n")
    result = launcher.windows_listener_pids()
    assert result.inspected and result.listeners == ()


def test_listener_inspection_one_expected_listener(monkeypatch):
    _powershell_result(monkeypatch, "CAPTURE_RESULT:BEGIN\nLISTENER\t127.0.0.1\t101\nCAPTURE_RESULT:END\n")
    assert launcher.windows_listener_pids() == _inspection(_listener())


@pytest.mark.parametrize("records", [
    "LISTENER\t127.0.0.1\t101\nLISTENER\t127.0.0.1\t202\n",
    "LISTENER\t0.0.0.0\t101\n",
    "LISTENER\t::1\t101\n",
    "LISTENER\t::\t101\n",
])
def test_listener_inspection_retains_multiple_or_wildcard_listeners(monkeypatch, records):
    _powershell_result(monkeypatch, f"CAPTURE_RESULT:BEGIN\n{records}CAPTURE_RESULT:END\n")
    result = launcher.windows_listener_pids()
    assert result.inspected and len(result.listeners) == records.count("LISTENER")


@pytest.mark.parametrize("stdout,code,stderr", [
    ("CAPTURE_RESULT:BEGIN\nCAPTURE_RESULT:END\n", 1, "failed"),
    ("CAPTURE_RESULT:BEGIN\nCAPTURE_RESULT:END\n", 0, "Get-NetTCPConnection: denied"),
    ("garbage", 0, ""),
    ("CAPTURE_RESULT:BEGIN\nLISTENER\t127.0.0.1\tbad\nCAPTURE_RESULT:END\n", 0, ""),
])
def test_listener_inspection_fails_closed_for_errors_and_malformed_output(monkeypatch, stdout, code, stderr):
    _powershell_result(monkeypatch, stdout, code=code, stderr=stderr)
    result = launcher.windows_listener_pids()
    assert not result.inspected and result.error


def test_listener_inspection_timeout_is_failure(monkeypatch):
    monkeypatch.setattr(launcher.os, "name", "nt")
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("powershell.exe", 8)
    monkeypatch.setattr(launcher.subprocess, "run", timeout)
    result = launcher.windows_listener_pids()
    assert not result.inspected and "Could not inspect" in result.error


@pytest.mark.parametrize("inspection", [
    launcher.ListenerInspection.failure("PowerShell failed"),
    _inspection(_listener(pid=123)),
    _inspection(_listener("0.0.0.0", 123)),
    _inspection(_listener("::1", 123)),
    _inspection(_listener("127.0.0.1", 123), _listener("127.0.0.1", 456)),
])
def test_cleanup_refuses_listener_or_inspection_failure(tmp_path, inspection):
    target = launcher.canonical_database_path(tmp_path)
    target.parent.mkdir(parents=True)
    target.touch()
    with pytest.raises(RuntimeError, match="Refusing cleanup|process still owns"):
        cleanup.cleanup_database(target, temp_root=tmp_path,
                                owner_probe=lambda *_: inspection, confirmation="DELETE")
    assert target.exists()


class _FakeNativeKernel:
    def __init__(self, *, actual_pid=321, assign_result=True, close_result=True):
        self.actual_pid = actual_pid
        self.assign_result = assign_result
        self.close_result = close_result
        self.assigned = None
    def GetProcessId(self, handle):
        return self.actual_pid
    def AssignProcessToJobObject(self, job, handle):
        self.assigned = (job, handle)
        return self.assign_result
    def CloseHandle(self, handle):
        return self.close_result


class _PopenHandle(_FakeProcess):
    def __init__(self, handle=900):
        self.pid = 321
        self._handle = handle
        self.returncode = None


def _job(kernel):
    job = launcher._WindowsKillJob.__new__(launcher._WindowsKillJob)
    job._kernel = kernel
    job.handle = 700
    return job


def test_job_assignment_uses_validated_popen_owned_handle():
    process = _PopenHandle(handle=900)
    kernel = _FakeNativeKernel(actual_pid=process.pid)
    _job(kernel).assign(process)
    assert kernel.assigned == (700, process._handle)


@pytest.mark.parametrize("handle", [None, 0, -1])
def test_job_assignment_rejects_invalid_popen_handle(handle):
    process = _PopenHandle(handle=handle)
    with pytest.raises(RuntimeError, match="valid Windows process handle|invalid Windows"):
        _job(_FakeNativeKernel()).assign(process)


def test_job_assignment_rejects_child_that_exited_before_assignment():
    process = _PopenHandle()
    process.returncode = 0
    with pytest.raises(RuntimeError, match="exited before"):
        _job(_FakeNativeKernel()).assign(process)


def test_job_assignment_failure_raises_without_closing_popen_handle():
    process = _PopenHandle()
    kernel = _FakeNativeKernel(actual_pid=process.pid, assign_result=False)
    with pytest.raises(OSError, match="AssignProcessToJobObject"):
        _job(kernel).assign(process)
    assert process._handle == 900


def test_job_assignment_rejects_handle_for_different_process():
    process = _PopenHandle()
    with pytest.raises(RuntimeError, match="no longer identifies"):
        _job(_FakeNativeKernel(actual_pid=999)).assign(process)


def test_job_close_handle_error_is_reported_and_handle_retained():
    job = _job(_FakeNativeKernel(close_result=False))
    with pytest.raises(OSError, match="CloseHandle"):
        job.close()
    assert job.handle == 700


def test_job_creation_failure_is_reported(monkeypatch):
    kernel = SimpleNamespace(**{name: Mock() for name in (
        "CreateJobObjectW", "SetInformationJobObject", "GetProcessId",
        "AssignProcessToJobObject", "CloseHandle",
    )})
    kernel.CreateJobObjectW.return_value = None
    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(launcher.ctypes, "WinDLL", lambda *_args, **_kwargs: kernel)
    with pytest.raises(OSError, match="CreateJobObjectW"):
        launcher._WindowsKillJob()


def test_launcher_identity_probe_requires_expected_pid_parent_executable_and_module(monkeypatch):
    process = _PopenHandle()
    payload = {
        "ProcessId": process.pid,
        "ParentProcessId": 77,
        "ExecutablePath": launcher.sys.executable,
        "CommandLine": f'"{launcher.sys.executable}" -m {launcher.GENERATOR_MODULE}',
    }
    monkeypatch.setattr(launcher.os, "getpid", lambda: 77)
    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(launcher, "inspect_windows_process", lambda _pid: payload)
    monkeypatch.setattr(launcher, "parse_windows_command_line", lambda _line:
                        [launcher.sys.executable, "-m", launcher.GENERATOR_MODULE])
    launcher.verify_generator_identity(process)
    payload["ParentProcessId"] = 999
    with pytest.raises(RuntimeError, match="identity did not match"):
        launcher.verify_generator_identity(process)


def _mock_windows_argv(monkeypatch, executable: str) -> None:
    def parse(command_line):
        prefix = f'"{executable}"'
        if command_line.startswith(prefix):
            rest = command_line[len(prefix):].strip()
        elif command_line.startswith(executable):
            rest = command_line[len(executable):].strip()
        else:
            return shlex.split(command_line)
        return [executable, *shlex.split(rest)]
    monkeypatch.setattr(launcher, "parse_windows_command_line", parse)


def _valid_generator_parent(monkeypatch, **changes):
    parent_pid = 707
    identity = {
        "ProcessId": parent_pid,
        "ParentProcessId": 12,
        "ExecutablePath": demo.sys.executable,
        "CommandLine": subprocess.list2cmdline([
            demo.sys.executable, "-m", "scripts.run_screenshot_capture"
        ]),
    }
    identity.update(changes)
    monkeypatch.setattr(demo.os, "name", "nt")
    monkeypatch.setattr(demo.os, "getppid", lambda: parent_pid)
    monkeypatch.setenv("SCREENSHOT_LAUNCHER_PID", str(parent_pid))
    monkeypatch.setattr(demo, "inspect_windows_process", lambda _pid: identity)
    _mock_windows_argv(monkeypatch, demo.sys.executable)
    return identity


def test_generator_parent_identity_accepts_exact_launcher(monkeypatch):
    _valid_generator_parent(monkeypatch)
    demo.verify_launcher_parent()


def test_startup_gate_itself_requires_validated_parent(monkeypatch):
    importlib.reload(demo)
    monkeypatch.setenv(demo.GATE_ENVIRONMENT_KEY, demo.GATE_ENVIRONMENT_VALUE)
    class UnreadableGate:
        def readline(self, _limit):
            pytest.fail("Gate was read before parent identity passed")
    monkeypatch.setattr(demo.sys, "stdin", SimpleNamespace(buffer=UnreadableGate()))
    monkeypatch.setattr(demo, "verify_launcher_parent", lambda: (_ for _ in ()).throw(
        RuntimeError("parent rejected")
    ))
    with pytest.raises(RuntimeError, match="parent rejected"):
        demo.wait_for_launcher_release()


def test_generator_rejects_spoofed_substring_command_line(monkeypatch):
    _valid_generator_parent(monkeypatch, CommandLine=(
        f'"{demo.sys.executable}" -c "# -m scripts.run_screenshot_capture"'
    ))
    with pytest.raises(RuntimeError, match="not launched directly"):
        demo.verify_launcher_parent()


def test_generator_rejects_unexpected_launcher_arguments(monkeypatch):
    _valid_generator_parent(monkeypatch, CommandLine=subprocess.list2cmdline([
        demo.sys.executable, "-m", "scripts.run_screenshot_capture", "--extra"
    ]))
    with pytest.raises(RuntimeError, match="not launched directly"):
        demo.verify_launcher_parent()


def test_generator_rejects_wrong_parent_executable(monkeypatch):
    _valid_generator_parent(monkeypatch, ExecutablePath="C:/other/python.exe")
    with pytest.raises(RuntimeError, match="not launched directly"):
        demo.verify_launcher_parent()


def test_generator_rejects_wrong_expected_parent_pid(monkeypatch):
    _valid_generator_parent(monkeypatch)
    monkeypatch.setenv("SCREENSHOT_LAUNCHER_PID", "999")
    with pytest.raises(RuntimeError, match="parent PID"):
        demo.verify_launcher_parent()


def test_generator_rejects_wrong_os_reported_parent_pid(monkeypatch):
    _valid_generator_parent(monkeypatch, ProcessId=999)
    with pytest.raises(RuntimeError, match="not launched directly"):
        demo.verify_launcher_parent()


def test_generator_rejects_parent_process_inspection_failure(monkeypatch):
    _valid_generator_parent(monkeypatch)
    monkeypatch.setattr(demo, "inspect_windows_process", lambda _pid: (_ for _ in ()).throw(
        RuntimeError("inspection failed")
    ))
    with pytest.raises(RuntimeError, match="inspection failed"):
        demo.verify_launcher_parent()


def test_launcher_database_configuration_must_match_canonical_child_url(tmp_path):
    canonical = launcher.canonical_database_path(tmp_path)
    url = demo.sqlite_url(canonical)
    backend_env = {"TEMP": str(tmp_path), "DATABASE_URL": url}
    generator_env = dict(backend_env)
    launcher.verify_capture_database_configuration(backend_env, generator_env, canonical)
    generator_env["DATABASE_URL"] = "sqlite:///wrong.sqlite3"
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        launcher.verify_capture_database_configuration(backend_env, generator_env, canonical)


def test_backend_job_assignment_failure_never_starts_generator(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(launcher, "build_backend_environment", lambda: ({}, tmp_path / "unused.sqlite3"))
    monkeypatch.setattr(launcher, "assert_port_available", lambda: None)
    children = []

    class FailedAssignmentJob:
        def __init__(self):
            self.closed = False
        def assign(self, process):
            raise RuntimeError("assignment refused")
        def close(self):
            self.closed = True

    job = FailedAssignmentJob()
    monkeypatch.setattr(launcher, "_WindowsKillJob", lambda: job)
    def popen(*args, **kwargs):
        child = _PopenHandle()
        children.append((args[0], child))
        return child
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    monkeypatch.setattr(launcher, "_stop_owned_process", lambda _child: None)
    with pytest.raises(RuntimeError, match="assignment refused"):
        launcher.launch()
    assert len(children) == 1
    assert "uvicorn" in children[0][0]
    assert job.closed


def _run_generator_main_at_gate(monkeypatch, gate_bytes, *, gate_value="stdin-v1"):
    _fresh_gate(monkeypatch, gate_bytes, gate_value=gate_value)
    calls = []
    def fake_authorized_body():
        calls.append("generate")
        demo._request_json(f"{demo._CANONICAL_API_BASE_URL}/ready")
    monkeypatch.setattr(demo, "verify_launcher_parent", lambda: None)
    monkeypatch.setattr(demo, "_generate_authorized", fake_authorized_body)
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return b"{}"
    monkeypatch.setattr(demo, "urlopen", lambda *_args, **_kwargs: calls.append("http") or Response())
    return demo.main(), calls


def test_generator_closed_gate_makes_no_http_call(monkeypatch):
    code, calls = _run_generator_main_at_gate(monkeypatch, b"")
    assert code == 1
    assert calls == []


def test_generator_waits_without_http_calls_while_gate_is_closed(monkeypatch):
    importlib.reload(demo)
    entered = threading.Event()
    release = threading.Event()
    calls = []
    results = []
    def fake_authorized_body():
        calls.append("generation-started")
        demo._request_json(f"{demo._CANONICAL_API_BASE_URL}/ready")
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return b"{}"
    monkeypatch.setattr(demo, "urlopen", lambda *_args, **_kwargs: calls.append("http") or Response())
    class ParentControlledStream:
        def readline(self, _limit):
            entered.set()
            if not release.wait(timeout=2):
                raise TimeoutError("test gate remained closed")
            return demo.GATE_RELEASE_SIGNAL
        def read(self, _size=-1):
            return b""
    monkeypatch.setattr(demo, "verify_launcher_parent", lambda: None)
    monkeypatch.setattr(demo, "_generate_authorized", fake_authorized_body)
    monkeypatch.setattr(demo.sys, "stdin", SimpleNamespace(buffer=ParentControlledStream()))
    monkeypatch.setenv(demo.GATE_ENVIRONMENT_KEY, demo.GATE_ENVIRONMENT_VALUE)
    worker = threading.Thread(target=lambda: results.append(demo.main()))
    worker.start()
    assert entered.wait(timeout=1)
    assert calls == []
    release.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert results == [0] and calls == ["generation-started", "http"]


def test_generator_eof_does_not_release_gate(monkeypatch):
    code, calls = _run_generator_main_at_gate(monkeypatch, b"")
    assert code == 1 and calls == []


@pytest.mark.parametrize("signal", [b"release\n", demo.GATE_RELEASE_SIGNAL + b"extra"])
def test_generator_invalid_or_trailing_gate_input_does_not_release(monkeypatch, signal):
    code, calls = _run_generator_main_at_gate(monkeypatch, signal)
    assert code == 1 and calls == []


def test_generator_missing_gate_does_not_release(monkeypatch):
    code, calls = _run_generator_main_at_gate(monkeypatch, demo.GATE_RELEASE_SIGNAL, gate_value=None)
    assert code == 1 and calls == []


def test_partial_release_signal_does_not_authorize(monkeypatch):
    importlib.reload(demo)
    monkeypatch.setattr(demo, "verify_launcher_parent", lambda: None)
    monkeypatch.setenv(demo.GATE_ENVIRONMENT_KEY, demo.GATE_ENVIRONMENT_VALUE)
    monkeypatch.setattr(demo.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(
        demo.GATE_RELEASE_SIGNAL.rstrip(b"\n")
    )))
    with pytest.raises(RuntimeError, match="exact launcher release signal"):
        demo.wait_for_launcher_release()


def test_generator_timeout_or_read_error_does_not_release(monkeypatch):
    importlib.reload(demo)
    class TimedOutReader:
        def readline(self, _limit):
            raise TimeoutError("gate read timeout")
    calls = []
    monkeypatch.setattr(demo, "verify_launcher_parent", lambda: None)
    monkeypatch.setattr(demo, "generate", lambda: calls.append("generate"))
    monkeypatch.setattr(demo.sys, "stdin", SimpleNamespace(buffer=TimedOutReader()))
    monkeypatch.setenv(demo.GATE_ENVIRONMENT_KEY, demo.GATE_ENVIRONMENT_VALUE)
    assert demo.main() == 1
    assert calls == []


def test_generator_gate_timeout_fails_closed(monkeypatch):
    importlib.reload(demo)
    done = threading.Event()
    class SlowReader:
        def readline(self, _limit):
            done.wait(timeout=1)
            return demo.GATE_RELEASE_SIGNAL
    monkeypatch.setattr(demo, "verify_launcher_parent", lambda: None)
    monkeypatch.setenv(demo.GATE_ENVIRONMENT_KEY, demo.GATE_ENVIRONMENT_VALUE)
    monkeypatch.setattr(demo, "GATE_READ_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(demo.sys, "stdin", SimpleNamespace(buffer=SlowReader()))
    with pytest.raises(TimeoutError, match="Timed out waiting"):
        demo.wait_for_launcher_release()
    done.set()


def test_generator_exact_release_and_eof_allows_generation(monkeypatch):
    code, calls = _run_generator_main_at_gate(monkeypatch, demo.GATE_RELEASE_SIGNAL)
    assert code == 0 and calls == ["generate", "http"]


def _release_gate_for_test(monkeypatch):
    _fresh_gate(monkeypatch, demo.GATE_RELEASE_SIGNAL)
    demo.wait_for_launcher_release()


def _request_through_generation(monkeypatch, url: str, payload=None, *, calls=None):
    _release_gate_for_test(monkeypatch)
    calls = [] if calls is None else calls
    results = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return b'{"ok":true}'
    monkeypatch.setattr(demo, "urlopen", lambda request, **kwargs: calls.append(request.full_url) or Response())
    monkeypatch.setattr(
        demo, "_generate_authorized",
        lambda: results.append(demo._request_json(url, payload=payload)),
    )
    demo.generate()
    return calls, results


@pytest.mark.parametrize("payload", [None, {"sensor": 1}])
def test_direct_request_before_release_never_reaches_urlopen(monkeypatch, payload):
    importlib.reload(demo)
    calls = []
    monkeypatch.setattr(demo, "urlopen", lambda *_args, **_kwargs: calls.append("urlopen"))
    endpoint = f"{demo._CANONICAL_API_BASE_URL}/ready" if payload is None else (
        f"{demo._CANONICAL_API_BASE_URL}/predict/anomaly"
    )
    with pytest.raises(RuntimeError, match="active one-shot launcher authorization"):
        demo._request_json(endpoint, payload=payload)
    assert calls == []


@pytest.mark.parametrize("url,payload", [
    ("https://127.0.0.1:8000/ready", None),
    ("http://localhost:8000/ready", None),
    ("http://127.0.0.2:8000/ready", None),
    ("http://192.168.1.10:8000/ready", None),
    ("http://127.0.0.1:8001/ready", None),
    ("http://user:pass@127.0.0.1:8000/ready", None),
    ("http://127.0.0.1:8000/unknown", None),
    ("http://127.0.0.1:8000/ready?x=1", None),
    ("http://127.0.0.1:8000/ready?", None),
    ("http://127.0.0.1:8000/ready#fragment", None),
    ("http://127.0.0.1:8000/ready#", None),
    ("http://127.0.0.1:8000/%72eady", None),
    ("http://127.0.0.1:8000/x/../ready", None),
    ("http://127.0.0.1:bad/ready", None),
    ("http://127.0.0.1:8000/ready", {"unexpected": "POST to GET-only route"}),
    ("http://127.0.0.1:8000/predict/anomaly", None),
])
def test_authorized_request_rejects_noncanonical_targets(monkeypatch, url, payload):
    calls = []
    with pytest.raises(RuntimeError, match="Malformed API URL|Only approved HTTP endpoints"):
        _request_through_generation(monkeypatch, url, payload, calls=calls)
    # Authorization was consumed by the failed one-shot generation; urlopen
    # must not have been reached by the rejecting request.
    assert calls == []


def test_exact_loopback_get_is_accepted_after_release(monkeypatch):
    calls, results = _request_through_generation(monkeypatch, f"{demo._CANONICAL_API_BASE_URL}/ready")
    status, data = results[0]
    assert status == 200 and data == {"ok": True}
    assert calls == [f"{demo._CANONICAL_API_BASE_URL}/ready"]


def test_wait_for_launcher_release_is_one_shot(monkeypatch):
    _release_gate_for_test(monkeypatch)
    with pytest.raises(RuntimeError, match="already been attempted or consumed"):
        demo.wait_for_launcher_release()


def test_generate_authorization_is_consumed_once(monkeypatch):
    _release_gate_for_test(monkeypatch)
    calls = []
    monkeypatch.setattr(demo, "_generate_authorized", lambda: calls.append("body"))
    demo.generate()
    with pytest.raises(RuntimeError, match="blocked until the launcher releases"):
        demo.generate()
    assert calls == ["body"]


def test_generate_cannot_be_called_without_consumable_launcher_release(monkeypatch):
    importlib.reload(demo)
    calls = []
    monkeypatch.setattr(demo, "preflight", lambda: calls.append("preflight"))
    monkeypatch.setattr(demo, "_request_json", lambda *_args, **_kwargs: calls.append("http"))
    with pytest.raises(RuntimeError, match="blocked until the launcher releases"):
        demo.generate()
    assert calls == []


def test_internal_generation_body_cannot_bypass_authorization(monkeypatch):
    importlib.reload(demo)
    monkeypatch.setattr(demo, "preflight", lambda: pytest.fail("preflight bypassed the authorization check"))
    with pytest.raises(RuntimeError, match="active one-shot launcher authorization"):
        demo._generate_authorized()


def test_authorization_is_not_exposed_as_mutable_module_state(monkeypatch):
    importlib.reload(demo)
    hidden_names = {
        "_authorization_state", "_GATE_PENDING", "_GATE_WAITING", "_GATE_GRANTED",
        "_GATE_ACTIVE", "_GATE_USED", "_begin_generation_authorization",
        "_set_authorization_state",
    }
    assert hidden_names.isdisjoint(vars(demo))
    monkeypatch.setattr(demo, "_authorization_state", "active", raising=False)
    monkeypatch.setattr(demo, "_GATE_ACTIVE", "active", raising=False)
    monkeypatch.setattr(demo, "_require_active_authorization", lambda: None, raising=False)
    monkeypatch.setattr(demo, "_validate_api_request", lambda *_args: "http://example.com/", raising=False)
    calls = []
    monkeypatch.setattr(demo, "urlopen", lambda *_args, **_kwargs: calls.append("called"))
    with pytest.raises(RuntimeError, match="active one-shot launcher authorization"):
        demo._request_json(f"{demo._CANONICAL_API_BASE_URL}/ready")
    assert calls == []


def test_authorization_cannot_be_reset_by_module_attribute_assignment(monkeypatch):
    _release_gate_for_test(monkeypatch)
    runs = []
    monkeypatch.setattr(demo, "_generate_authorized", lambda: runs.append("run"))
    demo.generate()
    monkeypatch.setattr(demo, "_authorization_state", "granted", raising=False)
    monkeypatch.setattr(demo, "_GATE_GRANTED", "granted", raising=False)
    with pytest.raises(RuntimeError, match="blocked until the launcher releases"):
        demo.generate()
    assert runs == ["run"]


def test_request_helper_rejects_caller_supplied_method_before_urlopen(monkeypatch):
    importlib.reload(demo)
    calls = []
    monkeypatch.setattr(demo, "urlopen", lambda *_args, **_kwargs: calls.append("called"))
    with pytest.raises(TypeError):
        demo._request_json(f"{demo._CANONICAL_API_BASE_URL}/ready", method="DELETE")
    assert calls == []


class _GatePipe:
    def __init__(self, events=None, *, fail_write=False, fail_flush=False, fail_close=False, on_write=None):
        self.events = events if events is not None else []
        self.closed = False
        self.data = b""
        self.fail_write = fail_write
        self.fail_flush = fail_flush
        self.fail_close = fail_close
        self.on_write = on_write
    def write(self, data):
        self.events.append("gate-write")
        if self.fail_write:
            raise OSError("mock gate pipe failure")
        self.data += data
        if self.on_write is not None:
            self.on_write()
        return len(data)
    def flush(self):
        self.events.append("gate-flush")
        if self.fail_flush:
            raise OSError("mock gate flush failure")
    def close(self):
        self.events.append("gate-close")
        if self.fail_close:
            raise OSError("mock gate close failure")
        self.closed = True


class _LaunchChild:
    def __init__(self, pid, *, stdin=None, events=None):
        self.pid = pid
        self.returncode = None
        self.stdin = stdin
        self.events = events if events is not None else []
    def poll(self):
        return self.returncode


class _LaunchJob:
    def __init__(self, events, *, fail_assignment=None):
        self.events = events
        self.assignments = 0
        self.fail_assignment = fail_assignment
    def assign(self, process):
        self.assignments += 1
        self.events.append(f"assign-{process.pid}")
        if self.assignments == self.fail_assignment:
            raise RuntimeError("mock assignment failure")
    def close(self):
        self.events.append("job-close")


def _patch_launch_harness(monkeypatch, tmp_path, *, fail_assignment=None,
                          fail_identity=False, fail_listener=False, fail_readiness=False,
                          fail_gate_pipe=False):
    events = []
    backend = _LaunchChild(501, events=events)
    generator_pipe = _GatePipe(events, fail_write=fail_gate_pipe)
    generator = _LaunchChild(502, stdin=generator_pipe, events=events)
    job = _LaunchJob(events, fail_assignment=fail_assignment)
    environment = {
        "TEMP": str(tmp_path),
        "DATABASE_URL": demo.sqlite_url(launcher.canonical_database_path(tmp_path)),
        "MODEL_DIR": "models",
        "DRIFT_REFERENCE_PATH": "reference.json",
    }
    database_path = launcher.canonical_database_path(tmp_path)
    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(launcher, "build_backend_environment", lambda: (environment, database_path))
    monkeypatch.setattr(launcher, "assert_port_available", lambda: events.append("port-check"))
    monkeypatch.setattr(launcher, "_WindowsKillJob", lambda: job)
    children = []
    def fake_popen(command, **kwargs):
        if "uvicorn" in command:
            child = backend
            events.append("start-backend")
        else:
            assert kwargs.get("stdin") == subprocess.PIPE
            assert kwargs["env"][launcher.GENERATOR_GATE_ENVIRONMENT_KEY] == launcher.GENERATOR_GATE_ENVIRONMENT_VALUE
            child = generator
            events.append("start-generator")
        children.append(child)
        return child
    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    readiness_calls = 0
    def readiness(*_args, **_kwargs):
        nonlocal readiness_calls
        readiness_calls += 1
        if fail_readiness and readiness_calls == 2:
            events.append("readiness-failed")
            raise RuntimeError("readiness failed")
        events.append(f"readiness-ready-{readiness_calls}")
    monkeypatch.setattr(launcher, "wait_for_backend", readiness)
    def identity(_process):
        if fail_identity:
            events.append("identity-failed")
            raise RuntimeError("identity failed")
        events.append("identity-ok")
    monkeypatch.setattr(launcher, "verify_generator_identity", identity)
    ownership_calls = 0
    def ownership(_pid):
        nonlocal ownership_calls
        ownership_calls += 1
        events.append(f"ownership-{ownership_calls}")
        if fail_listener and ownership_calls == 2:
            raise RuntimeError("listener changed")
    monkeypatch.setattr(launcher, "verify_port_owner", ownership)
    monkeypatch.setattr(launcher, "verify_capture_database_configuration",
                        lambda *_args: events.append("database-config-ok"))
    monkeypatch.setattr(launcher, "_run_generator_with_backend_guard", lambda *_args: 0)
    monkeypatch.setattr(launcher, "_monitor_child", lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt()))
    stopped = []
    monkeypatch.setattr(launcher, "_stop_owned_process", lambda child: stopped.append(child))
    return events, backend, generator, generator_pipe, job, children, stopped


def test_generator_assignment_failure_keeps_gate_closed_and_stops_both(monkeypatch, tmp_path):
    events, backend, generator, pipe, _job_obj, children, stopped = _patch_launch_harness(
        monkeypatch, tmp_path, fail_assignment=2
    )
    with pytest.raises(RuntimeError, match="mock assignment failure"):
        launcher.launch()
    assert len(children) == 2 and pipe.data == b"" and pipe.closed
    assert stopped == [generator, backend]
    assert "gate-write" not in events


@pytest.mark.parametrize("failure", ["identity", "listener", "readiness"])
def test_generator_pre_release_verification_failure_keeps_gate_closed_and_stops_both(
    monkeypatch, tmp_path, failure
):
    options = {
        "fail_identity": failure == "identity",
        "fail_listener": failure == "listener",
        "fail_readiness": failure == "readiness",
    }
    events, backend, generator, pipe, _job_obj, _children, stopped = _patch_launch_harness(
        monkeypatch, tmp_path, **options
    )
    expected = {"identity": "identity failed", "listener": "listener changed", "readiness": "readiness failed"}[failure]
    with pytest.raises(RuntimeError, match=expected):
        launcher.launch()
    assert pipe.data == b"" and pipe.closed
    assert stopped == [generator, backend]
    assert "gate-write" not in events


def test_launcher_releases_only_after_all_preconditions(monkeypatch, tmp_path):
    events, _backend, _generator, pipe, _job_obj, _children, _stopped = _patch_launch_harness(monkeypatch, tmp_path)
    assert launcher.launch() == 130
    assert pipe.data == launcher.GENERATOR_GATE_RELEASE_SIGNAL
    required = ["assign-501", "assign-502", "identity-ok", "ownership-2",
                "readiness-ready-2", "database-config-ok", "gate-write", "gate-flush", "gate-close"]
    positions = [events.index(event) for event in required]
    assert positions == sorted(positions)


def test_gate_pipe_failure_closes_gate_and_stops_both_children(monkeypatch, tmp_path):
    events, backend, generator, pipe, _job_obj, _children, stopped = _patch_launch_harness(
        monkeypatch, tmp_path, fail_gate_pipe=True
    )
    with pytest.raises(OSError, match="mock gate pipe failure"):
        launcher.launch()
    assert pipe.data == b"" and pipe.closed
    assert stopped == [generator, backend]
    assert "gate-write" in events and "gate-flush" not in events


@pytest.mark.parametrize("failure", ["flush", "close"])
def test_gate_flush_or_close_failure_preserves_error_and_stops_both(monkeypatch, tmp_path, failure):
    events, backend, generator, pipe, _job_obj, _children, stopped = _patch_launch_harness(monkeypatch, tmp_path)
    pipe.fail_flush = failure == "flush"
    pipe.fail_close = failure == "close"
    expected = f"mock gate {failure} failure"
    with pytest.raises(OSError, match=expected):
        launcher.launch()
    assert stopped == [generator, backend]
    assert pipe.data == launcher.GENERATOR_GATE_RELEASE_SIGNAL
    assert "gate-write" in events and "gate-flush" in events and "gate-close" in events


def test_generator_exit_during_release_prevents_valid_signal(monkeypatch):
    events = []
    generator = _LaunchChild(502, events=events)
    pipe = _GatePipe(events, on_write=lambda: setattr(generator, "returncode", 4))
    generator.stdin = pipe
    with pytest.raises(RuntimeError, match="exited while gate release was being written"):
        launcher.release_generator_gate(generator)
    assert pipe.data == launcher.GENERATOR_GATE_RELEASE_SIGNAL
    assert pipe.closed
    assert "gate-flush" not in events
