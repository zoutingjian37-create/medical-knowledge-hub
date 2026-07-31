"""Safe subprocess boundary for the locally installed OpenCLI runtime."""

import asyncio
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple


DEFAULT_RUNTIME_DIR = Path(r"D:\Codex\tools\opencli-runtime")
DEFAULT_BUNDLED_NODE = Path(
    r"C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime"
    r"\dependencies\node\bin\node.exe"
)


class OpenCLIRunnerError(RuntimeError):
    """OpenCLI is missing, unavailable, or returned an invalid response."""


@dataclass(frozen=True)
class OpenCLIStatus:
    installed: bool
    bridge_connected: bool
    version: str = ""
    detail: str = ""


class OpenCLIRunner:
    """Run OpenCLI without a shell and only expose structured output."""

    def __init__(
        self,
        runtime_dir: Optional[Path] = None,
        executable: Optional[str] = None,
        node_executable: Optional[str] = None,
    ) -> None:
        configured_runtime = os.getenv("OPENCLI_RUNTIME_DIR") or os.getenv(
            "CONTENT_HUB_OPENCLI_RUNTIME"
        )
        self.runtime_dir = Path(
            runtime_dir or configured_runtime or DEFAULT_RUNTIME_DIR
        )
        self._explicit_executable = executable or os.getenv("CONTENT_HUB_OPENCLI")
        self._explicit_node = node_executable or os.getenv("CONTENT_HUB_NODE")

    def command_prefix(self) -> Optional[Tuple[str, ...]]:
        cli_js = (
            self.runtime_dir
            / "node_modules"
            / "@jackwener"
            / "opencli"
            / "dist"
            / "src"
            / "main.js"
        )
        node = self._find_node()
        if cli_js.is_file() and node:
            return str(node), str(cli_js)

        candidates = [
            self._explicit_executable,
            str(self.runtime_dir / "node_modules" / ".bin" / "opencli.cmd"),
            shutil.which("opencli"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return (str(candidate),)
        return None

    async def status(self) -> OpenCLIStatus:
        prefix = self.command_prefix()
        if not prefix:
            return OpenCLIStatus(
                installed=False,
                bridge_connected=False,
                detail="OpenCLI runtime is not installed",
            )

        try:
            completed = await asyncio.to_thread(
                self._run_process, (*prefix, "daemon", "status"), 8
            )
        except OpenCLIRunnerError as exc:
            return OpenCLIStatus(
                installed=True,
                bridge_connected=False,
                detail=str(exc),
            )

        output = completed.stdout
        version_match = re.search(r"^Version:\s*v?([^\s]+)", output, re.MULTILINE)
        extension_match = re.search(r"^Extension:\s*(.+)$", output, re.MULTILINE)
        extension = extension_match.group(1).strip() if extension_match else "unknown"
        connected = extension.startswith("connected")
        detail = "ready" if connected else f"browser bridge {extension}"
        return OpenCLIStatus(
            installed=True,
            bridge_connected=connected,
            version=version_match.group(1) if version_match else "",
            detail=detail,
        )

    async def run_json(self, *arguments: str, timeout: int = 60) -> Any:
        completed = await self._run((*arguments, "-f", "json"), timeout)
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise OpenCLIRunnerError("OpenCLI returned invalid JSON") from exc

    async def run_text(self, *arguments: str, timeout: int = 60) -> str:
        completed = await self._run(arguments, timeout)
        return completed.stdout.strip()

    async def _run(
        self, arguments: Sequence[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        prefix = self.command_prefix()
        if not prefix:
            raise OpenCLIRunnerError("OpenCLI runtime is not installed")
        return await asyncio.to_thread(
            self._run_process, (*prefix, *arguments), timeout
        )

    def _run_process(
        self, command: Sequence[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                list(command),
                cwd=str(self.runtime_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
                env=self._safe_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenCLIRunnerError("OpenCLI request timed out") from exc
        except OSError as exc:
            raise OpenCLIRunnerError("OpenCLI could not be started") from exc

        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise OpenCLIRunnerError(self._redact(message) or "OpenCLI request failed")
        return completed

    def _find_node(self) -> Optional[Path]:
        candidates = [
            self._explicit_node,
            shutil.which("node"),
            str(DEFAULT_BUNDLED_NODE),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return Path(candidate)
        return None

    @staticmethod
    def _safe_environment() -> dict:
        environment = os.environ.copy()
        environment.setdefault("NO_COLOR", "1")
        environment.setdefault("OPENCLI_VERBOSE", "false")
        return environment

    @staticmethod
    def _redact(message: str) -> str:
        safe = re.sub(
            r"(?i)(cookie|token|authorization|password)(\s*[:=]\s*)[^\s,;]+",
            r"\1\2[REDACTED]",
            message,
        )
        return safe[:1000]
