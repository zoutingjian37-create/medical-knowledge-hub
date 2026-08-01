"""Pure date and layout rules for the desktop WeChat visual collector.

This module deliberately contains no mouse or OCR dependencies.  Keeping the
rules pure makes the fragile UI edge independently testable when WeChat changes
its rendering implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
import unicodedata

from .public_link import canonicalize_public_article_url


SHANGHAI_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def union(self, other: "Rect") -> "Rect":
        return Rect(
            min(self.left, other.left),
            min(self.top, other.top),
            max(self.right, other.right),
            max(self.bottom, other.bottom),
        )


@dataclass(frozen=True)
class OCRToken:
    text: str
    rect: Rect
    confidence: float = 1.0


@dataclass(frozen=True)
class VisionSnapshot:
    bounds: Rect
    tokens: tuple[OCRToken, ...]


@dataclass(frozen=True)
class ArticleCandidate:
    title: str
    published_date: date
    click_rect: Rect
    raw_date: str


_WEEKDAYS = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}

_NON_TITLE_PATTERNS = (
    re.compile(r"^(?:阅读|赞|分享|评论)"),
    re.compile(r"^\d+$"),
    re.compile(r"^(?:全部|贴图|文章|接收喜报|统计知识|高分文章解读)$"),
)


def parse_wechat_date(text: str, now: datetime | None = None) -> date | None:
    """Turn a WeChat list label into an unambiguous Beijing calendar date.

    WeChat shows a weekday only for recent content.  Therefore a weekday means
    the most recent *previous* occurrence (one to six days ago); seeing today's
    weekday is inconsistent because WeChat would display ``今天`` instead.
    """

    current = _beijing_now(now)
    today = current.date()
    value = _date_label_prefix(_compact(text))
    if not value:
        return None
    if value == "咋天":  # Common OCR substitution observed in WeChat metadata.
        value = "昨天"
    if value == "今天":
        return today
    if value == "昨天":
        return today - timedelta(days=1)

    match = re.fullmatch(r"(?:星期|周|礼拜)([一二三四五六日天])", value)
    if match:
        target = _WEEKDAYS[match.group(1)]
        days_ago = (today.weekday() - target) % 7
        if days_ago == 0:
            return None
        return today - timedelta(days=days_ago)

    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
    if match:
        return _safe_date(*map(int, match.groups()))

    match = re.fullmatch(r"(\d{1,2})月(\d{1,2})日", value)
    if match:
        month, day = map(int, match.groups())
        candidate = _safe_date(today.year, month, day)
        if candidate is None:
            return None
        if candidate > today:
            candidate = _safe_date(today.year - 1, month, day)
        return candidate

    match = re.fullmatch(r"(\d+)小时前", value)
    if match:
        return (current - timedelta(hours=int(match.group(1)))).date()

    match = re.fullmatch(r"(\d+)分钟前", value)
    if match:
        return (current - timedelta(minutes=int(match.group(1)))).date()

    return None


def extract_article_candidates(
    tokens: tuple[OCRToken, ...] | list[OCRToken],
    now: datetime | None = None,
) -> tuple[ArticleCandidate, ...]:
    """Associate OCR title rows with the date label immediately above them."""

    ordered = sorted(tokens, key=lambda item: (item.rect.top, item.rect.left))
    anchors = [
        (index, token, parsed)
        for index, token in enumerate(ordered)
        if (parsed := parse_wechat_date(token.text, now)) is not None
    ]
    candidates: list[ArticleCandidate] = []
    for anchor_index, (token_index, date_token, published) in enumerate(anchors):
        previous_index = anchors[anchor_index - 1][0] if anchor_index else -1
        row_tokens = [
            token
            for token in ordered[previous_index + 1 : token_index]
            if _is_title_token(token.text)
            and abs(token.rect.left - date_token.rect.left) <= 90
        ]
        if not row_tokens:
            continue
        # WeChat renders each article as title line(s) followed by one metadata
        # line containing the date.  Walk backwards from that date so category
        # labels above the first article are not mistaken for its title.
        reversed_title: list[OCRToken] = []
        next_top = date_token.rect.top
        for token in reversed(row_tokens):
            vertical_gap = next_top - token.rect.bottom
            if vertical_gap < -4:
                continue
            if reversed_title and vertical_gap > 24:
                break
            if not reversed_title and vertical_gap > 32:
                continue
            reversed_title.append(token)
            next_top = token.rect.top
        title_tokens = list(reversed(reversed_title))
        if not title_tokens:
            continue
        title = "".join(_clean_text(token.text) for token in title_tokens).strip()
        click_rect = title_tokens[0].rect
        for token in title_tokens[1:]:
            click_rect = click_rect.union(token.rect)
        candidates.append(
            ArticleCandidate(title, published, click_rect, _clean_text(date_token.text))
        )
    return tuple(candidates)


def select_articles(
    candidates: tuple[ArticleCandidate, ...] | list[ArticleCandidate],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 10,
) -> tuple[ArticleCandidate, ...]:
    """Filter by concrete dates before applying a newest-first limit."""

    if limit < 1:
        raise ValueError("limit must be at least 1")
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from must not be after date_to")
    eligible = [
        item
        for item in candidates
        if (date_from is None or item.published_date >= date_from)
        and (date_to is None or item.published_date <= date_to)
    ]
    eligible.sort(key=lambda item: (item.published_date, -item.click_rect.top), reverse=True)
    return tuple(eligible[:limit])


def locate_exact_account(snapshot: VisionSnapshot, account: str) -> Rect:
    """Locate the exact account card while ignoring the query and side rail."""

    wanted = _match_key(account)
    if not wanted:
        raise ValueError("account is required")
    top_cutoff = snapshot.bounds.top + int(snapshot.bounds.height * 0.18)
    bottom_cutoff = snapshot.bounds.top + int(snapshot.bounds.height * 0.72)
    right_cutoff = snapshot.bounds.left + int(snapshot.bounds.width * 0.75)
    candidates = [
        token
        for token in snapshot.tokens
        if _match_key(token.text) == wanted
        and top_cutoff <= token.rect.top <= bottom_cutoff
        and token.rect.left < right_cutoff
    ]
    if not candidates:
        raise LookupError(f"Exact official account not found: {account}")

    def score(token: OCRToken) -> tuple[int, float, int]:
        has_type_label = any(
            "公众号" in _compact(other.text)
            and 0 <= other.rect.top - token.rect.bottom <= 70
            and abs(other.rect.left - token.rect.left) <= 100
            for other in snapshot.tokens
        )
        return (int(has_type_label), token.confidence, token.rect.top)

    return max(candidates, key=score).rect


def locate_network_search(snapshot: VisionSnapshot, account: str) -> Rect:
    """Locate WeChat's 搜索网络结果/搜一搜 row below local matches."""

    wanted = _match_key(account)
    anchors = [
        token
        for token in snapshot.tokens
        if "搜索网络结果" in _compact(token.text) or "搜一搜" in _compact(token.text)
    ]
    for anchor in sorted(anchors, key=lambda token: token.rect.top, reverse=True):
        candidates = [
            token
            for token in snapshot.tokens
            if wanted in _match_key(token.text)
            and 0 <= token.rect.top - anchor.rect.bottom <= 120
        ]
        if candidates:
            return min(candidates, key=lambda token: token.rect.top).rect
    raise LookupError("WeChat network-search row was not found")


def locate_copy_link(snapshot: VisionSnapshot) -> Rect:
    for token in snapshot.tokens:
        if _match_key(token.text) == _match_key("复制链接"):
            return token.rect
    raise LookupError("Copy-link menu item is not visible")


def extract_article_header_date(text: str) -> date | None:
    """Read the full publication date embedded in a WeChat author line."""

    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", _compact(text))
    return _safe_date(*map(int, match.groups())) if match else None


def article_dedup_marker(account: str, published_date: date, url: str) -> str:
    """Return the explicit account/date/URL identity stored by the collector."""

    account_key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(account)))
    if not account_key:
        raise ValueError("account is required")
    if not isinstance(published_date, date):
        raise TypeError("published_date must be a date")
    canonical = canonicalize_public_article_url(url)
    return f"{account_key.casefold()}|{published_date.isoformat()}|{canonical}"


def _beijing_now(value: datetime | None) -> datetime:
    current = value or datetime.now(SHANGHAI_TZ)
    if current.tzinfo is None:
        return current.replace(tzinfo=SHANGHAI_TZ)
    return current.astimezone(SHANGHAI_TZ)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", _clean_text(value))


def _date_label_prefix(value: str) -> str:
    match = re.match(
        r"^(今天|昨天|咋天|(?:星期|周|礼拜)[一二三四五六日天]|"
        r"\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日|"
        r"\d+小时前|\d+分钟前)(?=$|阅读|赞|评论|分享)",
        value,
    )
    return match.group(1) if match else ""


def _clean_text(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _is_title_token(value: str) -> bool:
    cleaned = _clean_text(value)
    return bool(cleaned) and not any(pattern.search(cleaned) for pattern in _NON_TITLE_PATTERNS)


def _match_key(value: str) -> str:
    return re.sub(r"[\s\-—_·|]+", "", _clean_text(value)).casefold()
