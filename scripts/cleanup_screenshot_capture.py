"""Manually remove only the dedicated capture SQLite file after confirmation."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from scripts.run_screenshot_capture import HOST, PORT, canonical_database_path, windows_listener_pids


def validate_cleanup_target(candidate: str | Path, temp_root: str | Path | None = None) -> Path:
    expected = canonical_database_path(temp_root)
    supplied = Path(candidate).expanduser().resolve(strict=False)
    capture_dir = expected.parent.resolve(strict=False)
    if os.path.normcase(str(supplied)) != os.path.normcase(str(expected)):
        raise RuntimeError(f"Refusing unexpected cleanup path; expected exactly: {expected}")
    if supplied.parent != capture_dir or supplied.name != "demo.sqlite3":
        raise RuntimeError("Refusing cleanup outside the dedicated capture directory.")
    project_db = (Path(__file__).resolve().parents[1] / "predictive_maintenance.db").resolve()
    if supplied == project_db:
        raise RuntimeError("Refusing to remove the project database.")
    return supplied


def ensure_backend_stopped(owner_probe=windows_listener_pids) -> None:
    inspection = owner_probe(HOST, PORT)
    if not inspection.inspected:
        raise RuntimeError(
            f"Refusing cleanup because listener inspection failed: {inspection.error}"
        )
    if inspection.listeners:
        owners = sorted({listener.owning_pid for listener in inspection.listeners})
        raise RuntimeError(
            f"A process still owns {HOST}:{PORT} (PID(s) {sorted(owners)}); stop the capture backend first."
        )


def cleanup_database(
    candidate: str | Path,
    *,
    temp_root: str | Path | None = None,
    owner_probe=windows_listener_pids,
    confirmation: str,
) -> Path:
    target = validate_cleanup_target(candidate, temp_root)
    ensure_backend_stopped(owner_probe)
    if not target.is_file():
        raise RuntimeError(f"Disposable database file does not exist: {target}")
    if confirmation != "DELETE":
        raise RuntimeError("Cleanup cancelled; exact confirmation 'DELETE' was not entered.")
    target.unlink()
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-path", required=True, help="Exact dedicated demo.sqlite3 path")
    args = parser.parse_args()
    if os.name != "nt":
        print("Cleanup is supported only on Windows, where backend port ownership can be checked.", file=sys.stderr)
        return 1
    try:
        target = validate_cleanup_target(args.database_path)
        ensure_backend_stopped()
        if not target.is_file():
            raise RuntimeError(f"Disposable database file does not exist: {target}")
        print(f"Only this file will be removed: {target}")
        answer = input("Type DELETE to continue: ")
        cleanup_database(target, confirmation=answer)
        print("Disposable database removed. No directory or Docker volume was removed.")
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"Capture database cleanup refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
