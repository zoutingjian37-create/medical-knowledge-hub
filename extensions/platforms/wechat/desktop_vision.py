"""Code-driven desktop WeChat article discovery.

The workflow observes only rendered pixels and public links.  It does not read
WeChat databases, account tokens, Cookies, chat messages, or school credentials.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
from typing import Callable

from .public_link import canonicalize_public_article_url
from .vision import (
    SHANGHAI_TZ,
    ArticleCandidate,
    article_dedup_marker,
    select_articles,
)


DEFAULT_STATE_ROOT = Path(r"D:\Codex\state\medical-knowledge-hub")


class WeChatDesktopError(RuntimeError):
    """The visible WeChat workflow could not be completed safely."""


class WeChatDiscoveryIndex:
    """Atomic local index whose marker visibly contains the concrete date."""

    def __init__(self, path: Path | None = None):
        configured = os.getenv("CONTENT_HUB_STATE_DIR", "").strip()
        root = Path(configured).expanduser().resolve() if configured else DEFAULT_STATE_ROOT
        self.path = Path(path or root / "wechat-discovery-index.json")

    def markers(self) -> tuple[str, ...]:
        if not self.path.exists():
            return ()
        payload = json.loads(self.path.read_text("utf-8"))
        return tuple(str(value) for value in payload.get("markers", ()))

    def contains(self, marker: str) -> bool:
        return marker in set(self.markers())

    def add(self, marker: str) -> None:
        values = list(self.markers())
        if marker in values:
            return
        values.append(marker)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "markers": values}, ensure_ascii=False, indent=2)
            + "\n",
            "utf-8",
        )
        temporary.replace(self.path)


class WeChatVisualLinkBackend:
    """Orchestrate a visual session and emit canonical public article links."""

    def __init__(
        self,
        *,
        session=None,
        index: WeChatDiscoveryIndex | None = None,
        now_provider: Callable[[], datetime] | None = None,
        max_pages: int = 30,
    ):
        self.session = session or _default_session()
        self.index = index or WeChatDiscoveryIndex()
        self.now_provider = now_provider or (lambda: datetime.now(SHANGHAI_TZ))
        self.max_pages = max(1, int(max_pages))

    def collect_links(
        self,
        account: str,
        limit: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[str]:
        account = str(account).strip()
        if not account:
            raise ValueError("account is required")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from must not be after date_to")

        self.session.open_account_articles(account)
        links: list[str] = []
        handled_rows: set[tuple[str, date]] = set()
        for _ in range(self.max_pages):
            now = self.now_provider()
            visible = self.session.list_visible_articles(now)
            eligible = select_articles(
                visible,
                date_from=date_from,
                date_to=date_to,
                limit=max(1, len(visible)),
            )
            for candidate in eligible:
                row_identity = (candidate.title, candidate.published_date)
                if row_identity in handled_rows:
                    continue
                handled_rows.add(row_identity)
                self.session.open_article(candidate)
                try:
                    raw_url, header_date = self.session.copy_current_link()
                    canonical = canonicalize_public_article_url(raw_url)
                    if header_date and header_date != candidate.published_date:
                        raise WeChatDesktopError(
                            "WeChat article date mismatch: "
                            f"list={candidate.published_date.isoformat()}, "
                            f"article={header_date.isoformat()}"
                        )
                    published = header_date or candidate.published_date
                    marker = article_dedup_marker(account, published, canonical)
                    if self.index.contains(marker):
                        continue
                    self.index.add(marker)
                    links.append(canonical)
                    if len(links) >= limit:
                        return links
                finally:
                    self.session.return_to_articles()
            if not self.session.scroll_articles():
                break
        return links


def _default_session():
    from .windows_session import WindowsWeChatVisionSession

    return WindowsWeChatVisionSession()
