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

    def __init__(
        self,
        message: str,
        *,
        step: str = "unknown",
        retry_from: str = "account_search",
        progress_kept: bool = False,
    ):
        super().__init__(message)
        self.step = step
        self.retry_from = retry_from
        self.progress_kept = bool(progress_kept)


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

    def entries_for(
        self,
        account: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[tuple[date, str], ...]:
        """Return durable checkpoints for one account inside a date range."""

        expected = str(account).strip()
        entries: list[tuple[date, str]] = []
        seen_urls: set[str] = set()
        for marker in self.markers():
            try:
                marker_account, raw_date, url = marker.rsplit("|", 2)
                published = date.fromisoformat(raw_date)
                canonical = canonicalize_public_article_url(url)
            except (TypeError, ValueError):
                continue
            if marker_account != expected or canonical in seen_urls:
                continue
            if date_from is not None and published < date_from:
                continue
            if date_to is not None and published > date_to:
                continue
            seen_urls.add(canonical)
            entries.append((published, canonical))
        return tuple(sorted(entries, key=lambda item: item[0], reverse=True))

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
    ):
        self.session = session or _default_session()
        self.index = index or WeChatDiscoveryIndex()
        self.now_provider = now_provider or (lambda: datetime.now(SHANGHAI_TZ))

    def collect_links(
        self,
        account: str,
        limit: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        exclude_urls: tuple[str, ...] = (),
    ) -> list[str]:
        account = str(account).strip()
        if not account:
            raise ValueError("account is required")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        excluded = {
            canonicalize_public_article_url(value) for value in exclude_urls
        }

        self.session.open_account_articles(account)
        links: list[str] = []
        handled_rows: set[tuple[str, date]] = set()
        observed_days_per_step: list[float] = []
        previous_tail: date | None = None
        previous_scroll = 0
        batch_ceiling = 8
        # A bounded range must first align to its newest boundary.  Seeking
        # straight to date_from can jump over valid articles near date_to.
        seeking_range_ceiling = date_to is not None
        navigation_states: set[
            tuple[date, int, int, int, tuple[tuple[str, str], ...]]
        ] = set()
        while True:
            now = self.now_provider()
            visible = self.session.list_visible_articles(now)
            # A pinned historical article can be rendered above the live
            # chronology.  The newest recognized date is therefore safer
            # than the geometrically first row for the upper boundary.
            newest_date = max(item.published_date for item in visible)
            tail_date = max(
                visible, key=lambda item: item.click_rect.top
            ).published_date
            if previous_tail is not None and previous_scroll:
                moved_days = (previous_tail - tail_date).days
                if moved_days * previous_scroll > 0:
                    observed_days_per_step.append(
                        abs(moved_days / previous_scroll)
                    )
            if seeking_range_ceiling and date_to is not None:
                if tail_date <= date_to <= newest_date:
                    seeking_range_ceiling = False
                    navigation_states.clear()
                elif newest_date < date_to and previous_scroll == 1:
                    # A one-screen downward move crossed the upper boundary.
                    # The current screen is the first safe collection point;
                    # larger jumps must be reversed and refined first.
                    seeking_range_ceiling = False
                    navigation_states.clear()
                else:
                    direction = 1 if tail_date > date_to else -1
                    if previous_scroll and (
                        (previous_scroll > 0) != (direction > 0)
                    ):
                        batch_ceiling = max(1, abs(previous_scroll) // 2)
                    distance_days = (
                        (tail_date - date_to).days
                        if direction > 0
                        else (date_to - newest_date).days
                    )
                    scroll_steps = direction * _estimate_scroll_batch(
                        max(0, distance_days),
                        tuple(observed_days_per_step[-5:]),
                        ceiling=batch_ceiling,
                    )
                    state = (
                        tail_date,
                        distance_days,
                        batch_ceiling,
                        direction,
                        tuple(
                            (item.title, item.published_date.isoformat())
                            for item in visible
                        ),
                    )
                    if state in navigation_states:
                        raise WeChatDesktopError(
                            "WeChat date navigation repeated before the range ceiling was visible"
                        )
                    navigation_states.add(state)
                    previous_tail = tail_date
                    previous_scroll = scroll_steps
                    if not self.session.scroll_articles(scroll_steps):
                        break
                    continue
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
                raw_url, header_date = self._read_candidate_with_local_recovery(
                    candidate
                )
                canonical = canonicalize_public_article_url(raw_url)
                # The full article header is authoritative. The list date
                # is only used to avoid opening obviously irrelevant rows.
                published = header_date or candidate.published_date
                if date_from is not None and published < date_from:
                    continue
                if date_to is not None and published > date_to:
                    continue
                marker = article_dedup_marker(account, published, canonical)
                self.index.add(marker)
                if canonical in excluded:
                    continue
                links.append(canonical)
                if len(links) >= limit:
                    return links
            # Once the range ceiling is aligned, move exactly one viewport at
            # a time so no article inside the requested interval can be
            # skipped.  The coarse estimator is used only before collection.
            if date_from is not None and tail_date < date_from:
                break
            previous_tail = tail_date
            previous_scroll = 1
            if not self.session.scroll_articles(1):
                break
        return links

    def _read_candidate_with_local_recovery(self, candidate):
        """Read one article without discarding the already-open account list."""

        for attempt in range(2):
            try:
                self.session.open_article(candidate)
                copied = self.session.copy_current_link()
            except RuntimeError:
                recovered = self._recover_article_list()
                if attempt == 0 and recovered:
                    continue
                raise
            try:
                self.session.return_to_articles()
            except RuntimeError:
                if not self._recover_article_list():
                    raise
            return copied
        raise AssertionError("bounded local article retry did not terminate")

    def _recover_article_list(self) -> bool:
        recover = getattr(self.session, "recover_to_article_list", None)
        return bool(callable(recover) and recover())


def _estimate_scroll_batch(
    distance_days: int,
    observed_days_per_step: tuple[float, ...],
    *,
    ceiling: int = 8,
) -> int:
    """Choose a conservative checkpoint distance from observed UI movement."""

    if distance_days <= 0 or not observed_days_per_step:
        return 1
    values = sorted(value for value in observed_days_per_step if value > 0)
    if not values:
        return 1
    midpoint = len(values) // 2
    rate = (
        values[midpoint]
        if len(values) % 2
        else (values[midpoint - 1] + values[midpoint]) / 2
    )
    predicted = int((distance_days / rate) * 0.7)
    return max(1, min(max(1, int(ceiling)), predicted))


def _default_session():
    from .windows_session import WindowsWeChatVisionSession

    return WindowsWeChatVisionSession()
