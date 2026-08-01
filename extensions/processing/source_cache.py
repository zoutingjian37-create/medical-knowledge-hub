"""Short-lived article text kept outside the repository and Obsidian."""

import os
import re
import time
from pathlib import Path


DEFAULT_CACHE_ROOT = Path(r"D:\Codex\cache\medical-knowledge-hub")
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9-]+$")


class SourceCache:
    def __init__(self, root: Path | None = None):
        configured = os.getenv("CONTENT_HUB_CACHE_DIR", "").strip()
        self.root = Path(root or configured or DEFAULT_CACHE_ROOT).expanduser().resolve()

    def put(self, job_id: str, text: str) -> Path:
        path = self._path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(text, "utf-8")
        temporary.replace(path)
        return path

    def read(self, job_id: str) -> str:
        return self._path(job_id).read_text("utf-8")

    def delete(self, job_id: str) -> None:
        self._path(job_id).unlink(missing_ok=True)

    def purge_expired(self, max_age_hours: int = 24) -> tuple[str, ...]:
        if max_age_hours < 1:
            raise ValueError("max_age_hours must be at least 1")
        if not self.root.exists():
            return ()
        cutoff = time.time() - max_age_hours * 60 * 60
        expired = []
        for path in self.root.glob("*.md"):
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                expired.append(path.stem)
        return tuple(sorted(expired))

    def _path(self, job_id: str) -> Path:
        if not _SAFE_JOB_ID.fullmatch(job_id):
            raise ValueError("job_id contains unsupported characters")
        return self.root / f"{job_id}.md"
