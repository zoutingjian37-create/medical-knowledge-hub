"""Small serializable records for personal subscriptions and automation."""

from dataclasses import asdict, dataclass


SUBSCRIPTION_KINDS = {
    "wechat_account",
    "journal",
    "feed",
    "literature_query",
}

RUN_STATUSES = {
    "discovering",
    "filtered",
    "saved_zotero",
    "waiting_school_login",
    "distilling",
    "waiting_confirmation",
    "completed",
    "failed",
}


@dataclass(frozen=True)
class Subscription:
    id: str
    kind: str
    name: str
    source: str
    query: str
    keywords: tuple[str, ...]
    requirement: str
    enabled: bool
    daily_limit: int
    zotero_collection: str
    created_at: str
    updated_at: str
    last_successful_date: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["keywords"] = list(self.keywords)
        return payload


@dataclass(frozen=True)
class AutomationSettings:
    enabled: bool = False
    run_time: str = "08:30"
    daily_limit: int = 5
    catch_up: bool = True
    last_scheduled_date: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LiteratureRun:
    id: str
    subscription_id: str
    status: str
    started_at: str
    updated_at: str
    discovered: int = 0
    filtered: int = 0
    saved_zotero: int = 0
    queued: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
