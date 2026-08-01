"""Small JSON job store that never persists article body text."""

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .documents import MarkdownDocument
from .source_cache import SourceCache


DEFAULT_STATE_ROOT = Path(r"D:\Codex\state\medical-knowledge-hub")
VALID_STATUSES = {
    "pending",
    "needs_reparse",
    "handoff_ready",
    "preview_ready",
    "approved",
    "rejected",
    "trashed",
    "failed",
}
TRASH_STATUSES = {"rejected", "trashed"}
DEFAULT_TRASH_RETENTION_DAYS = 7


@dataclass(frozen=True)
class KnowledgeJob:
    id: str
    status: str
    source_url: str
    title: str
    author: str
    published_at: str
    platform: str
    cache_path: str
    created_at: str
    updated_at: str
    preview_path: str = ""
    wiki_updates: tuple[str, ...] = ()
    error: str = ""
    deleted_at: str = ""
    status_before_trash: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["wiki_updates"] = list(self.wiki_updates)
        return payload


class KnowledgeJobStore:
    def __init__(self, root: Path | None = None):
        configured = os.getenv("CONTENT_HUB_STATE_DIR", "").strip()
        self.root = Path(root or configured or DEFAULT_STATE_ROOT).expanduser().resolve()
        self.jobs_root = self.root / "jobs"

    def create(
        self,
        document: MarkdownDocument,
        cache_path: Path,
        job_id: str | None = None,
        platform: str = "wechat",
    ) -> KnowledgeJob:
        duplicate = self.find_by_source(document.source_url)
        if duplicate is not None:
            if Path(cache_path) != Path(duplicate.cache_path):
                Path(cache_path).unlink(missing_ok=True)
            return duplicate

        identifier = job_id or self.id_for_source(document.source_url)
        now = _utc_now()
        job = KnowledgeJob(
            id=identifier,
            status="pending",
            source_url=document.source_url,
            title=document.title,
            author=document.author,
            published_at=document.published_at,
            platform=platform,
            cache_path=str(Path(cache_path).resolve()),
            created_at=now,
            updated_at=now,
        )
        self._write(job)
        return job

    @staticmethod
    def id_for_source(source_url: str) -> str:
        return hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:16]

    def find_by_source(self, source_url: str) -> KnowledgeJob | None:
        return next(
            (job for job in self.list() if job.source_url == source_url),
            None,
        )

    def get(self, job_id: str) -> KnowledgeJob:
        path = self._path(job_id)
        if not path.exists():
            raise KeyError(f"unknown knowledge job: {job_id}")
        return _from_dict(json.loads(path.read_text("utf-8")))

    def list(self, status: str | None = None) -> tuple[KnowledgeJob, ...]:
        jobs = self._all_jobs()
        if status is None:
            return tuple(job for job in jobs if job.status not in TRASH_STATUSES)
        return tuple(job for job in jobs if job.status == status)

    def list_trash(self) -> tuple[KnowledgeJob, ...]:
        return tuple(
            job for job in self._all_jobs() if job.status in TRASH_STATUSES
        )

    def _all_jobs(self) -> tuple[KnowledgeJob, ...]:
        if not self.jobs_root.exists():
            return ()
        return tuple(
            _from_dict(json.loads(path.read_text("utf-8")))
            for path in sorted(self.jobs_root.glob("*.json"))
        )

    def update(self, job_id: str, **changes) -> KnowledgeJob:
        job = self.get(job_id)
        if "status" in changes and changes["status"] not in VALID_STATUSES:
            raise ValueError(f"unsupported job status: {changes['status']}")
        if "wiki_updates" in changes:
            changes["wiki_updates"] = tuple(changes["wiki_updates"])
        changes["updated_at"] = _utc_now()
        updated = replace(job, **changes)
        self._write(updated)
        return updated

    def delete_metadata(self, job_id: str) -> None:
        path = self._path(job_id)
        if not path.exists():
            raise KeyError(f"unknown knowledge job: {job_id}")
        path.unlink()

    def get_trash_retention_days(self) -> int:
        path = self.root / "trash-settings.json"
        if not path.exists():
            return DEFAULT_TRASH_RETENTION_DAYS
        payload = json.loads(path.read_text("utf-8"))
        value = int(payload.get("retention_days", DEFAULT_TRASH_RETENTION_DAYS))
        return value if 1 <= value <= 30 else DEFAULT_TRASH_RETENTION_DAYS

    def set_trash_retention_days(self, retention_days: int) -> int:
        if not 1 <= retention_days <= 30:
            raise ValueError("trash retention must be between 1 and 30 days")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "trash-settings.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"retention_days": retention_days}, indent=2) + "\n",
            "utf-8",
        )
        temporary.replace(path)
        return retention_days

    def get_auto_distill_enabled(self) -> bool:
        path = self.root / "knowledge-settings.json"
        if not path.exists():
            return True
        payload = json.loads(path.read_text("utf-8"))
        return bool(payload.get("auto_distill", True))

    def set_auto_distill_enabled(self, enabled: bool) -> bool:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "knowledge-settings.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"auto_distill": bool(enabled)}, indent=2) + "\n",
            "utf-8",
        )
        temporary.replace(path)
        return bool(enabled)

    def _path(self, job_id: str) -> Path:
        return self.jobs_root / f"{job_id}.json"

    def _write(self, job: KnowledgeJob) -> None:
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        path = self._path(job.id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(job.to_dict(), ensure_ascii=False, indent=2) + "\n",
            "utf-8",
        )
        temporary.replace(path)


def expire_jobs(
    cache: SourceCache,
    store: KnowledgeJobStore,
    max_age_hours: int = 24,
) -> tuple[str, ...]:
    expired = cache.purge_expired(max_age_hours=max_age_hours)
    for job_id in expired:
        try:
            store.update(job_id, status="needs_reparse", cache_path="")
        except KeyError:
            continue
    return expired


def _from_dict(payload: dict) -> KnowledgeJob:
    payload["wiki_updates"] = tuple(payload.get("wiki_updates") or ())
    return KnowledgeJob(**payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
