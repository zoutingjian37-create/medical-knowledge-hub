"""Opt-in bridge to the single current-user Windows scheduled task."""

import os
from pathlib import Path
import subprocess
import sys


def sync_windows_task(settings) -> dict:
    enabled = os.getenv("CONTENT_HUB_MANAGE_TASK_SCHEDULER", "0").strip().lower()
    if enabled not in {"1", "true", "yes"}:
        return {"managed": False, "detail": "task scheduler management is disabled"}
    root = Path(__file__).resolve().parents[2]
    script = root / "install-automation-task.ps1"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ProjectRoot",
        str(root),
        "-PythonExe",
        sys.executable,
        "-RunTime",
        settings.run_time,
    ]
    if not settings.enabled:
        command.append("-Disable")
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "could not update scheduled task")
    return {"managed": True, "enabled": settings.enabled, "run_time": settings.run_time}
