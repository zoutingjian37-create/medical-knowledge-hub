"""Atomic JSON persistence kept outside the source repository."""

import json
import os
import re
import unicodedata
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from extensions.processing.job_store import DEFAULT_STATE_ROOT

from .models import AutomationSettings, SUBSCRIPTION_KINDS, Subscription


class SubscriptionStore:
    def __init__(self, root: Path | None = None):
        configured = os.getenv("CONTENT_HUB_STATE_DIR", "").strip()
        self.root = Path(root or configured or DEFAULT_STATE_ROOT).expanduser().resolve()
        self.subscriptions_path = self.root / "subscriptions.json"
        self.automation_path = self.root / "automation.json"

    def create(
        self,
        *,
        kind: str,
        name: str,
        source: str = "",
        query: str = "",
        keywords=(),
        requirement: str = "",
        enabled: bool = True,
        daily_limit: int = 5,
        zotero_collection: str = "",
    ) -> Subscription:
        _validate_kind(kind)
        _validate_limit(daily_limit)
        now = _utc_now()
        subscription = Subscription(
            id=uuid4().hex,
            kind=kind,
            name=_required(name, "name"),
            source=str(source).strip(),
            query=str(query).strip(),
            keywords=_clean_keywords(keywords),
            requirement=str(requirement).strip(),
            enabled=bool(enabled),
            daily_limit=daily_limit,
            zotero_collection=(
                str(zotero_collection).strip() or _required(name, "name")
            ),
            created_at=now,
            updated_at=now,
        )
        values = [*self.list(), subscription]
        self._write_subscriptions(values)
        return subscription

    def list(self) -> tuple[Subscription, ...]:
        payload = _read_json(self.subscriptions_path, [])
        return tuple(_subscription_from_dict(item) for item in payload)

    def get(self, subscription_id: str) -> Subscription:
        for subscription in self.list():
            if subscription.id == subscription_id:
                return subscription
        raise KeyError(f"unknown subscription: {subscription_id}")

    def update(self, subscription_id: str, **changes) -> Subscription:
        current = self.get(subscription_id)
        allowed = {
            "name",
            "source",
            "query",
            "keywords",
            "requirement",
            "enabled",
            "daily_limit",
            "zotero_collection",
            "last_successful_date",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unsupported subscription fields: {sorted(unknown)}")
        if "name" in changes:
            changes["name"] = _required(changes["name"], "name")
        if "daily_limit" in changes:
            _validate_limit(changes["daily_limit"])
        if "keywords" in changes:
            changes["keywords"] = _clean_keywords(changes["keywords"])
        if "last_successful_date" in changes:
            _validate_date(changes["last_successful_date"])
        changes["updated_at"] = _utc_now()
        updated = replace(current, **changes)
        values = [updated if item.id == subscription_id else item for item in self.list()]
        self._write_subscriptions(values)
        return updated

    def delete(self, subscription_id: str) -> None:
        self.get(subscription_id)
        self._write_subscriptions(
            [item for item in self.list() if item.id != subscription_id]
        )

    def sync_wechat_accounts(self, names) -> tuple[Subscription, ...]:
        """Replace the default WeChat account list with one atomic state write."""

        desired = _clean_account_names(names)
        subscriptions = self.list()
        existing = {}
        for item in subscriptions:
            if item.kind == "wechat_account":
                existing.setdefault(_account_key(item.name), item)

        now = _utc_now()
        synced = []
        for name in desired:
            current = existing.get(_account_key(name))
            if current is None:
                current = Subscription(
                    id=uuid4().hex,
                    kind="wechat_account",
                    name=name,
                    source=name,
                    query="",
                    keywords=(),
                    requirement="",
                    enabled=True,
                    daily_limit=5,
                    zotero_collection=name,
                    created_at=now,
                    updated_at=now,
                )
            else:
                collection = current.zotero_collection
                if not collection or collection == current.name:
                    collection = name
                current = replace(
                    current,
                    name=name,
                    source=name,
                    enabled=True,
                    zotero_collection=collection,
                    updated_at=now,
                )
            synced.append(current)

        non_wechat = [
            item for item in subscriptions if item.kind != "wechat_account"
        ]
        self._write_subscriptions([*non_wechat, *synced])
        return tuple(synced)

    def get_automation(self) -> AutomationSettings:
        payload = _read_json(self.automation_path, {})
        return AutomationSettings(**payload) if payload else AutomationSettings()

    def update_automation(self, **changes) -> AutomationSettings:
        allowed = {"enabled", "run_time", "daily_limit", "catch_up", "last_scheduled_date"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unsupported automation fields: {sorted(unknown)}")
        if "run_time" in changes:
            _validate_time(changes["run_time"])
        if "daily_limit" in changes:
            _validate_limit(changes["daily_limit"])
        updated = replace(self.get_automation(), **changes)
        _atomic_json(self.automation_path, updated.to_dict())
        return updated

    def export_config(self) -> dict:
        return {
            "format": "medical-knowledge-hub-subscriptions",
            "version": 1,
            "subscriptions": [item.to_dict() for item in self.list()],
            "automation": self.get_automation().to_dict(),
        }

    def import_config(self, payload: dict) -> None:
        if payload.get("format") != "medical-knowledge-hub-subscriptions":
            raise ValueError("unsupported subscription export")
        subscriptions = [
            _subscription_from_dict(item) for item in payload.get("subscriptions", [])
        ]
        automation = AutomationSettings(**payload.get("automation", {}))
        _validate_time(automation.run_time)
        _validate_limit(automation.daily_limit)
        self._write_subscriptions(subscriptions)
        _atomic_json(self.automation_path, automation.to_dict())

    def _write_subscriptions(self, subscriptions) -> None:
        _atomic_json(
            self.subscriptions_path,
            [subscription.to_dict() for subscription in subscriptions],
        )


def _subscription_from_dict(payload: dict) -> Subscription:
    _validate_kind(payload.get("kind", ""))
    _validate_limit(payload.get("daily_limit", 0))
    values = dict(payload)
    values["keywords"] = _clean_keywords(values.get("keywords", ()))
    values.setdefault("last_successful_date", "")
    _validate_date(values["last_successful_date"])
    return Subscription(**values)


def _atomic_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    temporary.replace(path)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def _required(value, field: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    return cleaned


def _validate_kind(kind: str) -> None:
    if kind not in SUBSCRIPTION_KINDS:
        raise ValueError(f"unsupported subscription kind: {kind}")


def _validate_limit(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
        raise ValueError("daily_limit must be between 1 and 100")


def _validate_time(value: str) -> None:
    match = re.fullmatch(r"(\d{2}):(\d{2})", str(value))
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise ValueError("run_time must use HH:MM")


def _validate_date(value: str) -> None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return
    try:
        date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError("last_successful_date must use YYYY-MM-DD") from exc


def _clean_keywords(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _clean_account_names(values) -> tuple[str, ...]:
    cleaned = []
    seen = set()
    for value in values:
        name = unicodedata.normalize("NFKC", str(value)).strip()
        if not name:
            continue
        if "\n" in name or "\r" in name:
            raise ValueError("each WeChat account must be a single line")
        if len(name) > 200:
            raise ValueError("WeChat account name must be at most 200 characters")
        key = _account_key(name)
        if key not in seen:
            seen.add(key)
            cleaned.append(name)
    if len(cleaned) > 100:
        raise ValueError("at most 100 WeChat accounts are supported")
    return tuple(cleaned)


def _account_key(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
