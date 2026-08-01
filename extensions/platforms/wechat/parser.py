"""Independent OpenCLI parser for one public WeChat article link."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional

from extensions.platforms.opencli.runner import OpenCLIRunner, OpenCLIRunnerError
from extensions.processing.documents import MarkdownDocument

from .public_link import canonicalize_public_article_url


DEFAULT_TEMP_ROOT = Path(r"D:\Codex\cache\medical-knowledge-hub\opencli-temp")


class OpenCLIWeChatParser:
    def __init__(
        self,
        runner: Optional[OpenCLIRunner] = None,
        temp_root: Optional[Path] = None,
        retry_delay: float = 5,
        max_attempts: int = 2,
    ):
        self._runner = runner or OpenCLIRunner()
        self._temp_root = Path(temp_root or DEFAULT_TEMP_ROOT)
        self._retry_delay = max(0, retry_delay)
        self._max_attempts = max(1, max_attempts)

    async def parse(self, url: str) -> MarkdownDocument:
        public_url = canonicalize_public_article_url(url)
        self._temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._temp_root) as directory:
            output = Path(directory)
            payload = None
            markdown_files = []
            for attempt in range(self._max_attempts):
                try:
                    payload = await self._runner.run_json(
                        "weixin",
                        "download",
                        "--url",
                        public_url,
                        "--output",
                        str(output),
                        "--download-images",
                        "false",
                        timeout=120,
                    )
                except OpenCLIRunnerError as exc:
                    raise RuntimeError(str(exc)) from exc
                markdown_files = sorted(output.rglob("*.md"))
                if markdown_files:
                    break
                status = _payload_status(payload)
                retryable = "verification required" in status.lower()
                if not retryable or attempt + 1 >= self._max_attempts:
                    detail = f": {status}" if status else ""
                    raise RuntimeError(
                        f"OpenCLI did not produce a Markdown article{detail}"
                    )
                await asyncio.sleep(self._retry_delay)
            markdown = markdown_files[0].read_text("utf-8")
            metadata = _first_row(payload)
            return MarkdownDocument(
                source_url=public_url,
                title=str(metadata.get("title") or _heading(markdown)),
                author=str(metadata.get("author") or ""),
                published_at=str(metadata.get("publish_time") or ""),
                markdown=markdown,
            )


def _first_row(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, list):
        return next((row for row in payload if isinstance(row, Mapping)), {})
    if isinstance(payload, Mapping):
        for key in ("data", "items", "results", "rows"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return next(
                    (row for row in rows if isinstance(row, Mapping)), {}
                )
        return payload
    return {}


def _heading(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "WeChat article"


def _payload_status(payload: Any) -> str:
    row = _first_row(payload)
    return str(row.get("status") or row.get("error") or "").strip()
