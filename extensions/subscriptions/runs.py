"""Atomic local run history for subscription executions."""

import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from extensions.processing.job_store import DEFAULT_STATE_ROOT

from .models import LiteratureRun, RUN_STATUSES


class LiteratureRunStore:
    def __init__(self, root: Path | None = None):
        configured = os.getenv("CONTENT_HUB_STATE_DIR", "").strip()
        self.root = Path(root or configured or DEFAULT_STATE_ROOT).expanduser().resolve()
        self.runs_root = self.root / "literature-runs"

    def create(self, subscription_id: str) -> LiteratureRun:
        now = _utc_now()
        run = LiteratureRun(
            id=uuid4().hex,
            subscription_id=subscription_id,
            status="discovering",
            started_at=now,
            updated_at=now,
        )
        self._write(run)
        return run

    def get(self, run_id: str) -> LiteratureRun:
        path = self.runs_root / f"{run_id}.json"
        if not path.exists():
            raise KeyError(f"unknown literature run: {run_id}")
        return LiteratureRun(**json.loads(path.read_text("utf-8")))

    def list(self) -> tuple[LiteratureRun, ...]:
        if not self.runs_root.exists():
            return ()
        runs = [self.get(path.stem) for path in self.runs_root.glob("*.json")]
        return tuple(sorted(runs, key=lambda item: item.started_at, reverse=True))

    def update(self, run_id: str, **changes) -> LiteratureRun:
        if "status" in changes and changes["status"] not in RUN_STATUSES:
            raise ValueError(f"unsupported run status: {changes['status']}")
        changes["updated_at"] = _utc_now()
        run = replace(self.get(run_id), **changes)
        self._write(run)
        return run

    def _write(self, run: LiteratureRun) -> None:
        self.runs_root.mkdir(parents=True, exist_ok=True)
        path = self.runs_root / f"{run.id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(run.to_dict(), ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        temporary.replace(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
