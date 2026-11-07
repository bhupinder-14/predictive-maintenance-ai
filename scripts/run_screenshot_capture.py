"""Own and verify the Windows backend process before seeding capture data."""

from __future__ import annotations

import ctypes
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from ctypes import wintypes
from enum import Enum
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 8000
API_BASE_URL = f"http://{HOST}:{PORT}"
READY_TIMEOUT_SECONDS = 90.0
GENERATOR_MODULE = "scripts.prepare_screenshot_demo"
GENERATOR_GATE_ENVIRONMENT_KEY = "SCREENSHOT_CAPTURE_GATE"
GENERATOR_GATE_ENVIRONMENT_VALUE = "stdin-v1"
GENERATOR_GATE_RELEASE_SIGNAL = b"RELEASE_SCREENSHOT_CAPTURE_V1\n"
LISTENER_ADDRESSES = frozenset({
    "127.0.0.1", "0.0.0.0", "::1", "::", "::ffff:127.0.0.1", "::ffff:0.0.0.0",
})


@dataclass(frozen=True)
class TcpListener:
    local_address: str
    owning_pid: int


class ListenerInspectionState(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class ListenerInspection:
    state: ListenerInspectionState
    listeners: tuple[TcpListener, ...] = ()
    error: str | None = None

    @classmethod
    def success(cls, listeners: tuple[TcpListener, ...] = ()) -> "ListenerInspection":
        return cls(ListenerInspectionState.SUCCESS, listeners)

    @classmethod
    def failure(cls, error: str) -> "ListenerInspection":
        return cls(ListenerInspectionState.FAILURE, (), error)

    @property
    def inspected(self) -> bool:
        return self.state is ListenerInspectionState.SUCCESS


def canonical_database_path(temp_root: str | Path | None = None) -> Path:
    root = Path(temp_root if temp_root is not None else os.environ["TEMP"])
    return (root / "predictive-maintenance-ai-capture" / "demo.sqlite3").resolve()


def build_backend_environment(
    source: dict[str, str] | None = None,
    *,
    temp_root: str | Path | None = None,
) -> tuple[dict[str, str], Path]:
    base = dict(os.environ if source is None else source)
    if temp_root is None and not base.get("TEMP"):
        raise RuntimeError("TEMP is not set; refusing to guess the disposable database path.")
    path = canonical_database_path(temp_root if temp_root is not None else base["TEMP"])
    project_db = (PROJECT_ROOT / "predictive_maintenance.db").resolve()
    if path == project_db or PROJECT_ROOT in path.parents:
        raise RuntimeError("Capture database must be outside the project directory.")
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite existing disposable database: {path}")
    base["DATABASE_URL"] = f"sqlite:///{path.as_posix()}"
    # Do not inherit user overrides that could select alternate/unreviewed artifacts.
    base["MODEL_DIR"] = str((PROJECT_ROOT / "models").resolve())
    base["DRIFT_REFERENCE_PATH"] = str(
        (PROJECT_ROOT / "data" / "reference" / "drift_reference_v1.json").resolve()
    )
    return base, path


def assert_port_available(host: str = HOST, port: int = PORT) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError as exc:
            raise RuntimeError(f"Port {host}:{port} is not available; no process was started.") from exc


def windows_listener_pids(host: str = HOST, port: int = PORT) -> ListenerInspection:
    """Inspect every IPv4/IPv6 loopback or wildcard listener, or return failure."""
    if os.name != "nt":
        return ListenerInspection.failure("Windows listener inspection is only available on Windows.")
    if host != HOST or port != PORT:
        return ListenerInspection.failure("Only the approved 127.0.0.1:8000 capture endpoint may be inspected.")
    command = (
        "$ErrorActionPreference='Stop'; "
        "$addresses = @('127.0.0.1','0.0.0.0','::1','::','::ffff:127.0.0.1','::ffff:0.0.0.0'); "
        "try { "
        f"$items = @(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction Stop "
        "| Where-Object { $addresses -contains $_.LocalAddress }); "
        "[Console]::Out.WriteLine('CAPTURE_RESULT:BEGIN'); "
        "foreach ($item in $items) { "
        "if ($null -eq $item.OwningProcess -or $null -eq $item.LocalAddress) { throw 'Incomplete listener record' }; "
        "[Console]::Out.WriteLine(('LISTENER' + [char]9 + $item.LocalAddress + [char]9 + $item.OwningProcess)) "
        "}; [Console]::Out.WriteLine('CAPTURE_RESULT:END'); exit 0 "
        "} catch { [Console]::Error.WriteLine('CAPTURE_ERROR:' + $_.Exception.Message); exit 17 }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ListenerInspection.failure(f"Could not inspect Windows port ownership: {exc}")
    if result.returncode != 0:
        return ListenerInspection.failure(
            f"Windows port ownership inspection exited {result.returncode}: {result.stderr.strip()}"
        )
    if result.stderr.strip():
        return ListenerInspection.failure(
            f"Windows port ownership inspection emitted an error record: {result.stderr.strip()}"
        )
    lines = result.stdout.splitlines()
    if (len(lines) < 2 or lines[0] != "CAPTURE_RESULT:BEGIN"
            or lines[-1] != "CAPTURE_RESULT:END"):
        return ListenerInspection.failure("Windows port ownership inspection returned incomplete output.")
    listeners: list[TcpListener] = []
    for line in lines[1:-1]:
        fields = line.split("\t")
        if len(fields) != 3 or fields[0] != "LISTENER" or fields[1] not in LISTENER_ADDRESSES:
            return ListenerInspection.failure(f"Malformed listener inspection record: {line!r}")
        try:
            pid = int(fields[2])
            if pid <= 0:
                raise ValueError("PID must be positive")
        except ValueError as exc:
            return ListenerInspection.failure(f"Malformed listener PID in inspection output: {fields[2]!r}")
        listeners.append(TcpListener(fields[1], pid))
    return ListenerInspection.success(tuple(listeners))


def verify_port_owner(expected_pid: int, owner_probe=windows_listener_pids) -> None:
    inspection = owner_probe(HOST, PORT)
    if not inspection.inspected:
        raise RuntimeError(f"Refusing API use because listener inspection failed: {inspection.error}")
    expected = (TcpListener(HOST, expected_pid),)
    if inspection.listeners != expected:
        raise RuntimeError(
            f"Refusing API use: listeners {inspection.listeners!r} do not exactly match "
            f"the sole {HOST}:{PORT} listener owned by launched Uvicorn PID {expected_pid}."
        )


def verify_generator_identity(process, *, launcher_pid: int | None = None) -> None:
    """Independently verify the blocked generator child before releasing it."""
    if process.poll() is not None:
        raise RuntimeError(f"Generator child PID {process.pid} exited before identity verification.")
    expected_launcher_pid = os.getpid() if launcher_pid is None else launcher_pid
    identity = inspect_windows_process(process.pid)
    command_line = identity.get("CommandLine")
    executable = identity.get("ExecutablePath")
    expected_executable = normalize_executable_path(sys.executable)
    if (identity.get("ProcessId") != process.pid
            or identity.get("ParentProcessId") != expected_launcher_pid
            or not isinstance(executable, str)
            or normalize_executable_path(executable) != expected_executable
            or not isinstance(command_line, str)
            or not exact_python_module_invocation(command_line, GENERATOR_MODULE)
            or process.poll() is not None):
        raise RuntimeError(f"Generator child identity did not match the launched module: {identity!r}")


def inspect_windows_process(process_id: int) -> dict:
    """Return a structured Windows process identity or fail closed."""
    if os.name != "nt":
        raise RuntimeError("Windows process inspection is unavailable on this platform.")
    command = (
        "$ErrorActionPreference='Stop'; "
        f"try {{ $item = Get-CimInstance -ClassName Win32_Process -Filter 'ProcessId = {process_id}' -ErrorAction Stop; "
        "if ($null -eq $item) { throw 'Process not found' }; "
        "$identity = [ordered]@{ ProcessId=[int]$item.ProcessId; ParentProcessId=[int]$item.ParentProcessId; "
        "ExecutablePath=$item.ExecutablePath; CommandLine=$item.CommandLine }; "
        "[Console]::Out.WriteLine(($identity | ConvertTo-Json -Compress -Depth 2)) "
        "} catch { [Console]::Error.WriteLine('CAPTURE_ERROR:' + $_.Exception.Message); exit 17 }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            check=False, capture_output=True, text=True, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Could not inspect Windows process {process_id}: {exc}") from exc
    if result.returncode != 0 or result.stderr.strip():
        raise RuntimeError(
            f"Windows process inspection failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    try:
        identity = json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Windows process inspection returned malformed JSON.") from exc
    required = {"ProcessId", "ParentProcessId", "ExecutablePath", "CommandLine"}
    if (not isinstance(identity, dict) or set(identity) != required
            or identity.get("ProcessId") != process_id
            or not isinstance(identity.get("ParentProcessId"), int)
            or not isinstance(identity.get("ExecutablePath"), str)
            or not isinstance(identity.get("CommandLine"), str)):
        raise RuntimeError("Windows process inspection returned incomplete or ambiguous identity data.")
    return identity


def normalize_executable_path(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def parse_windows_command_line(command_line: str) -> list[str]:
    """Parse a Windows process command line; shlex is only a non-Windows test fallback."""
    if os.name != "nt":
        return shlex.split(command_line, posix=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    argc = ctypes.c_int()
    shell32.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    argv = shell32.CommandLineToArgvW(command_line, ctypes.byref(argc))
    if not argv:
        raise OSError(ctypes.get_last_error(), "CommandLineToArgvW failed")
    try:
        return [argv[index] for index in range(argc.value)]
    finally:
        if kernel32.LocalFree(ctypes.cast(argv, wintypes.HLOCAL)):
            raise OSError(ctypes.get_last_error(), "LocalFree for parsed process arguments failed")


def exact_python_module_invocation(command_line: str, module: str) -> bool:
    try:
        arguments = parse_windows_command_line(command_line)
    except (OSError, ValueError, RuntimeError):
        return False
    return (
        len(arguments) == 3
        and normalize_executable_path(arguments[0]) == normalize_executable_path(sys.executable)
        and arguments[1:] == ["-m", module]
    )


def verify_capture_database_configuration(
    backend_environment: dict[str, str],
    generator_environment: dict[str, str],
    database_path: Path,
) -> None:
    """Revalidate the canonical SQLite target immediately before gate release."""
    try:
        temp_root = backend_environment["TEMP"]
        generator_temp = generator_environment["TEMP"]
    except KeyError as exc:
        raise RuntimeError("Capture child environment lost TEMP before generator release.") from exc
    expected_path = canonical_database_path(temp_root)
    if expected_path != database_path.resolve() or canonical_database_path(generator_temp) != expected_path:
        raise RuntimeError("Capture database path is no longer the canonical disposable path.")
    expected_url = f"sqlite:///{expected_path.as_posix()}"
    if (backend_environment.get("DATABASE_URL") != expected_url
            or generator_environment.get("DATABASE_URL") != expected_url):
        raise RuntimeError("Backend and generator DATABASE_URL values do not match the canonical capture path.")


def release_generator_gate(generator) -> None:
    """Send the exact release signal and close the pipe to complete the handshake."""
    gate = getattr(generator, "stdin", None)
    if gate is None or getattr(gate, "closed", False):
        raise RuntimeError("Generator startup gate is unavailable or already closed.")
    try:
        if generator.poll() is not None:
            raise RuntimeError(f"Generator PID {generator.pid} exited before gate release.")
        written = gate.write(GENERATOR_GATE_RELEASE_SIGNAL)
        if written != len(GENERATOR_GATE_RELEASE_SIGNAL):
            raise RuntimeError("Generator startup gate accepted only a partial release signal.")
        if generator.poll() is not None:
            raise RuntimeError(f"Generator PID {generator.pid} exited while gate release was being written.")
        gate.flush()
        if generator.poll() is not None:
            raise RuntimeError(f"Generator PID {generator.pid} exited while gate release was being flushed.")
        # The child requires EOF after the exact signal. Without successful
        # close, it remains blocked and cannot mistake partial input for release.
        gate.close()
    except BaseException as original:
        try:
            if not getattr(gate, "closed", False):
                gate.close()
        except Exception as close_error:
            original.add_note(f"Additionally, closing the failed generator gate raised: {close_error}")
        raise


def close_generator_gate(generator) -> None:
    """Close the parent pipe on failure so a waiting child sees EOF and refuses."""
    gate = getattr(generator, "stdin", None) if generator is not None else None
    if gate is not None and not getattr(gate, "closed", False):
        gate.close()


def _readiness_response() -> tuple[int | None, dict | None]:
    try:
        with urlopen(f"{API_BASE_URL}/ready", timeout=2) as response:
            import json
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        import json
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = None
        return exc.code, payload
    except (URLError, OSError, TimeoutError):
        return None, None


def wait_for_backend(
    child,
    *,
    timeout: float = READY_TIMEOUT_SECONDS,
    poll_interval: float = 0.25,
    owner_probe=windows_listener_pids,
    readiness_probe=_readiness_response,
    monotonic=time.monotonic,
    sleep=time.sleep,
) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        exit_code = child.poll()
        if exit_code is not None:
            raise RuntimeError(f"Uvicorn child PID {child.pid} exited during startup with code {exit_code}.")
        inspection = owner_probe(HOST, PORT)
        if not inspection.inspected:
            raise RuntimeError(f"Listener inspection failed during startup: {inspection.error}")
        if inspection.listeners and inspection.listeners != (TcpListener(HOST, child.pid),):
            raise RuntimeError(
                f"Port ownership mismatch during startup: {inspection.listeners!r}; "
                f"expected only child PID {child.pid} on {HOST}."
            )
        if inspection.listeners == (TcpListener(HOST, child.pid),):
            status, payload = readiness_probe()
            if status == 200:
                if (not isinstance(payload, dict) or payload.get("status") != "ready"
                        or payload.get("database") is not True
                        or payload.get("models") != {"anomaly": True, "failure": True}):
                    raise RuntimeError(f"Uvicorn child is not fully ready: {payload}")
                # Recheck PID ownership immediately before any client calls.
                verify_port_owner(child.pid, owner_probe)
                return
            if status is not None and status != 503:
                raise RuntimeError(f"Unexpected readiness HTTP status {status}: {payload}")
            if status == 503:
                raise RuntimeError(f"Uvicorn started but readiness failed: {payload}")
        sleep(poll_interval)
    raise TimeoutError(f"Uvicorn child did not become ready within {timeout:.0f} seconds.")


class _JobIoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _JobBasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JobExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimit),
        ("IoInfo", _JobIoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WindowsKillJob:
    """Kill the assigned backend child if this launcher process is terminated."""

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows job ownership is unavailable on this platform.")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel = kernel
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.GetProcessId.argtypes = [wintypes.HANDLE]
        kernel.GetProcessId.restype = wintypes.DWORD
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL

        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        try:
            info = _JobExtendedLimit()
            info.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(
                self.handle, self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info), ctypes.sizeof(info),
            ):
                raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        except Exception as original:
            try:
                self.close()
            except Exception as close_error:
                original.add_note(f"Additionally, closing failed Job Object handle failed: {close_error}")
            raise

    def _popen_process_handle(self, process):
        """Return the borrowed Popen-owned HANDLE, validated against its PID.

        On Windows subprocess.Popen exposes the native process HANDLE as the
        private ``_handle`` attribute. Using it avoids reopening a potentially
        reused numeric PID. This is isolated here because it is a CPython
        implementation detail; the handle remains owned and closed by Popen.
        """
        if process.poll() is not None:
            raise RuntimeError(f"Child PID {process.pid} exited before Job Object assignment.")
        handle = getattr(process, "_handle", None)
        try:
            numeric_handle = int(handle)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("Popen did not expose a valid Windows process handle.") from exc
        invalid_handle = ctypes.c_void_p(-1).value
        if numeric_handle in (0, -1, invalid_handle):
            raise RuntimeError("Popen exposed an invalid Windows process handle.")
        actual_pid = int(self._kernel.GetProcessId(handle))
        if not actual_pid:
            raise OSError(ctypes.get_last_error(), "GetProcessId failed for Popen process handle")
        if actual_pid != process.pid or process.poll() is not None:
            raise RuntimeError("Popen process handle no longer identifies the live expected child.")
        return handle

    def assign(self, process) -> None:
        handle = self._popen_process_handle(process)
        if not self._kernel.AssignProcessToJobObject(self.handle, handle):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        if process.poll() is not None:
            raise RuntimeError(f"Child PID {process.pid} exited during Job Object assignment.")

    def close(self) -> None:
        if getattr(self, "handle", None):
            if not self._kernel.CloseHandle(self.handle):
                raise OSError(ctypes.get_last_error(), "CloseHandle for Job Object failed")
            self.handle = None


def _stop_owned_process(process, *, timeout: float = 8.0) -> None:
    """Terminate only a Popen handle created by this launcher."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def _monitor_child(child, owner_probe=windows_listener_pids) -> None:
    while child.poll() is None:
        verify_port_owner(child.pid, owner_probe)
        try:
            child.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            continue
    raise RuntimeError(f"Uvicorn child exited unexpectedly with code {child.returncode}.")


def _run_generator_with_backend_guard(generator, backend, owner_probe=windows_listener_pids) -> int:
    while True:
        if backend.poll() is not None:
            _stop_owned_process(generator)
            raise RuntimeError(f"Uvicorn child exited during generation with code {backend.returncode}.")
        verify_port_owner(backend.pid, owner_probe)
        try:
            return generator.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            continue


def launch() -> int:
    if os.name != "nt":
        raise RuntimeError("This trusted launcher requires Windows process/port inspection.")
    environment, database_path = build_backend_environment()
    assert_port_available()
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    backend = None
    generator = None
    job = None
    try:
        # Create the kill-on-close guard before creating either child.
        job = _WindowsKillJob()
        command = [sys.executable, "-m", "uvicorn", "src.api.main:app",
                   "--host", HOST, "--port", str(PORT)]
        backend = subprocess.Popen(
            command, cwd=PROJECT_ROOT, env=environment,
            creationflags=creationflags,
        )
        # The kernel job also terminates only the children created below if the
        # launcher is abruptly terminated; assignment failure is fail-closed.
        job.assign(backend)
        print(f"Started Uvicorn child PID {backend.pid} for {HOST}:{PORT}.", flush=True)
        wait_for_backend(backend)
        verify_port_owner(backend.pid)
        generator_environment = {
            **environment,
            "SCREENSHOT_LAUNCHER_PID": str(os.getpid()),
            GENERATOR_GATE_ENVIRONMENT_KEY: GENERATOR_GATE_ENVIRONMENT_VALUE,
        }
        generator = subprocess.Popen(
            [sys.executable, "-m", GENERATOR_MODULE],
            cwd=PROJECT_ROOT,
            env=generator_environment,
            stdin=subprocess.PIPE,
            bufsize=0,
            creationflags=creationflags,
        )
        job.assign(generator)
        # The child performs its own parent check, then blocks at stdin before
        # calling generate(). Verify its live OS identity before authorizing it.
        verify_generator_identity(generator)
        verify_port_owner(backend.pid)
        wait_for_backend(backend)
        verify_port_owner(backend.pid)
        verify_capture_database_configuration(environment, generator_environment, database_path)
        release_generator_gate(generator)
        generator_code = _run_generator_with_backend_guard(generator, backend)
        if generator_code != 0:
            raise RuntimeError(f"Demo generator exited with code {generator_code}.")
        verify_port_owner(backend.pid)
        print(f"Capture backend remains available at {API_BASE_URL}.", flush=True)
        print(f"Disposable SQLite path: {database_path}", flush=True)
        print("Press Ctrl+C to stop the launcher and its Uvicorn child.", flush=True)
        _monitor_child(backend)
        return 0
    except KeyboardInterrupt:
        print("Stopping screenshot capture services.", flush=True)
        return 130
    finally:
        cleanup_errors = []
        try:
            close_generator_gate(generator)
        except Exception as exc:
            cleanup_errors.append(f"closing generator startup gate: {exc}")
        for owned_child in (generator, backend):
            try:
                _stop_owned_process(owned_child)
            except Exception as exc:
                cleanup_errors.append(f"stopping child {getattr(owned_child, 'pid', '?')}: {exc}")
        if job is not None:
            try:
                job.close()
            except Exception as exc:
                cleanup_errors.append(f"closing Windows Job Object: {exc}")
        if cleanup_errors:
            active_error = sys.exception()
            message = "Launcher cleanup was incomplete: " + "; ".join(cleanup_errors)
            if active_error is not None:
                active_error.add_note(message)
                print(message, file=sys.stderr, flush=True)
            else:
                raise RuntimeError(message)


def main() -> int:
    try:
        return launch()
    except Exception as exc:
        print(f"Screenshot capture launcher stopped safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
