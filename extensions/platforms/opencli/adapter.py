"""One configurable adapter for Zhihu, Bilibili, Xiaohongshu, and Douyin."""

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from extensions.platforms.base import (
    AuthResult,
    CreatorCandidate,
    Cursor,
    ItemRef,
    Page,
    PlatformAdapter,
    PlatformError,
    PlatformHealth,
    RawItem,
)
from extensions.processing.normalizer import NormalizedContent

from .runner import OpenCLIRunner, OpenCLIRunnerError


OPENCLI_ADAPTER_VERSION = "opencli-1.8.6"

_PROFILES: Dict[str, Dict[str, Any]] = {
    "zhihu": {
        "hosts": ("zhihu.com", "www.zhihu.com", "zhuanlan.zhihu.com"),
        "content_type": "article",
    },
    "bilibili": {
        "hosts": ("bilibili.com", "www.bilibili.com", "space.bilibili.com"),
        "content_type": "video",
    },
    "xiaohongshu": {
        "hosts": ("xiaohongshu.com", "www.xiaohongshu.com"),
        "content_type": "note",
    },
    "douyin": {
        "hosts": ("douyin.com", "www.douyin.com"),
        "content_type": "video",
    },
}


class OpenCLIAdapter(PlatformAdapter):
    """Translate OpenCLI JSON/text into the local platform contract."""

    def __init__(self, platform_key: str, runner: Optional[OpenCLIRunner] = None):
        if platform_key not in _PROFILES:
            raise ValueError(f"Unsupported OpenCLI platform: {platform_key}")
        self.platform_key = platform_key
        self.profile = _PROFILES[platform_key]
        self.runner = runner or OpenCLIRunner()

    async def authenticate(self) -> AuthResult:
        status = await self.runner.status()
        if not status.bridge_connected:
            return AuthResult(authenticated=False, detail=status.detail)
        try:
            payload = await self.runner.run_json(
                "auth",
                "status",
                "--site",
                self.platform_key,
                "--timeout",
                "8",
            )
        except OpenCLIRunnerError as exc:
            return AuthResult(authenticated=False, detail=str(exc))

        row = _first_row(payload)
        state = str(
            row.get("status", row.get("logged_in", row.get("logged-in", "")))
        ).lower()
        authenticated = state in {"true", "logged-in", "logged_in", "yes"}
        account = str(
            row.get("name", row.get("username", row.get("user_name", "")))
        )
        return AuthResult(
            authenticated=authenticated,
            account=account,
            detail="authenticated" if authenticated else "login required",
        )

    async def health(self) -> PlatformHealth:
        status = await self.runner.status()
        return PlatformHealth(
            available=status.installed and status.bridge_connected,
            authenticated=False,
            detail=status.detail,
        )

    async def search_creator(self, query: str) -> Tuple[CreatorCandidate, ...]:
        if self.platform_key != "bilibili":
            raise PlatformError(
                f"{self.platform_key} does not expose reliable creator search in OpenCLI"
            )
        payload = await self._run_json(
            "bilibili",
            "search",
            query,
            "--type",
            "user",
            "--limit",
            "20",
        )
        candidates: List[CreatorCandidate] = []
        seen = set()
        for row in _rows(payload):
            url = str(row.get("url", ""))
            match = re.search(r"space\.bilibili\.com/(\d+)", url)
            if not match or match.group(1) in seen:
                continue
            creator_id = match.group(1)
            seen.add(creator_id)
            name = _pick(row, "name", "title", "author") or creator_id
            candidates.append(
                CreatorCandidate(
                    creator_id=creator_id,
                    name=name,
                    avatar_url=_pick(row, "avatar", "avatar_url"),
                    raw_metadata=dict(row),
                )
            )
        return tuple(candidates)

    async def list_creator_items(
        self, creator_id: str, cursor: Optional[Cursor] = None
    ) -> Page:
        limit = 20
        if self.platform_key == "bilibili":
            page_number = int((cursor.value if cursor else {}).get("page", 1))
            payload = await self._run_json(
                "bilibili",
                "user-videos",
                creator_id,
                "--page",
                str(page_number),
                "--limit",
                str(limit),
            )
            next_cursor = Cursor({"page": page_number + 1})
        elif self.platform_key == "zhihu":
            answers = await self._run_json(
                "zhihu", "user-answers", creator_id, "--limit", str(limit)
            )
            articles = await self._run_json(
                "zhihu", "user-articles", creator_id, "--limit", str(limit)
            )
            payload = [*_rows(answers), *_rows(articles)]
            next_cursor = None
        elif self.platform_key == "xiaohongshu":
            payload = await self._run_json(
                "xiaohongshu", "user", creator_id, "--limit", str(limit)
            )
            next_cursor = None
        else:
            payload = await self._run_json(
                "douyin", "user-videos", creator_id, "--limit", str(limit)
            )
            next_cursor = None

        items: List[ItemRef] = []
        for row in _rows(payload):
            url = _pick(row, "url", "source_url", "share_url")
            if not url:
                continue
            try:
                reference = self.item_ref_from_url(url, creator_id=creator_id)
            except ValueError:
                continue
            items.append(
                ItemRef(
                    source_item_id=reference.source_item_id,
                    creator_id=creator_id,
                    source_url=reference.source_url,
                    raw_metadata=dict(row),
                )
            )
        if len(items) < limit:
            next_cursor = None if self.platform_key != "bilibili" else next_cursor
        return Page(items=tuple(items), next_cursor=next_cursor, total=None)

    async def fetch_item(self, item_ref: ItemRef) -> RawItem:
        try:
            if self.platform_key == "bilibili":
                payload = await self.runner.run_json(
                    "bilibili", "video", item_ref.source_item_id
                )
                data = {"payload": payload}
            elif self.platform_key == "xiaohongshu":
                payload = await self.runner.run_json(
                    "xiaohongshu", "note", item_ref.source_url
                )
                data = {"payload": payload}
            elif self.platform_key == "zhihu" and item_ref.source_item_id.startswith(
                "answer:"
            ):
                answer_id = item_ref.source_item_id.split(":", 1)[1]
                payload = await self.runner.run_json(
                    "zhihu", "answer-detail", answer_id
                )
                data = {"payload": payload}
            else:
                markdown = await self.runner.run_text(
                    "web",
                    "read",
                    "--url",
                    item_ref.source_url,
                    "--stdout",
                    "true",
                    "--download-images",
                    "false",
                )
                data = {"markdown": markdown}
        except OpenCLIRunnerError as exc:
            raise PlatformError(str(exc)) from exc

        return RawItem(
            source_item_id=item_ref.source_item_id,
            creator_id=item_ref.creator_id,
            source_url=item_ref.source_url,
            data={**data, "list_metadata": dict(item_ref.raw_metadata)},
        )

    def normalize_item(self, raw_item: RawItem) -> NormalizedContent:
        payload = raw_item.data.get("payload")
        details = _field_map(payload)
        if not details:
            details = dict(_first_row(payload))
        list_metadata = raw_item.data.get("list_metadata") or {}
        combined = {**dict(list_metadata), **details}
        markdown = str(raw_item.data.get("markdown", "")).strip()
        if self.platform_key == "douyin" and markdown:
            markdown, douyin_metadata = _compact_douyin_markdown(markdown)
            combined.update(douyin_metadata)

        title = _pick(
            combined, "title", "question_title", "desc", "description", "标题"
        )
        if not title and markdown:
            heading = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
            title = heading.group(1).strip() if heading else ""
        title = title or raw_item.source_item_id

        creator_name = _pick(
            combined,
            "author",
            "owner",
            "nickname",
            "name",
            "user",
            "作者",
            "UP主",
        )
        content = _pick(
            combined,
            "content",
            "description",
            "desc",
            "text",
            "正文",
            "简介",
        )
        if self.platform_key == "xiaohongshu" and _is_xiaohongshu_shell_title(title):
            if not creator_name and _looks_like_login_or_verification(content):
                raise PlatformError("小红书返回了登录或验证页面，未保存为正文")
            title = (
                _pick(list_metadata, "title")
                or _title_from_content(content)
                or raw_item.source_item_id
            )
        if markdown:
            body_html = ""
            body_text = markdown
        elif content.lstrip().startswith("<"):
            body_html = content
            body_text = BeautifulSoup(content, "html.parser").get_text("\n", strip=True)
        else:
            body_html = ""
            body_text = content

        content_type = self.profile["content_type"]
        if self.platform_key == "zhihu":
            content_type = raw_item.source_item_id.split(":", 1)[0]

        return NormalizedContent(
            platform=self.platform_key,
            creator_id=raw_item.creator_id,
            creator_name=creator_name,
            source_item_id=raw_item.source_item_id,
            content_type=content_type,
            title=title,
            body_html=body_html,
            body_text=body_text,
            published_at=_parse_datetime(
                _value(combined, "published_at", "publish_time", "created_at", "date")
            ),
            source_url=raw_item.source_url,
            images=_media_urls(
                combined, ("images", "image_urls", "image", "cover", "pic", "thumbnail")
            ),
            videos=_media_urls(
                combined, ("videos", "video_urls", "video", "play_url")
            ),
            transcript=_pick(combined, "transcript", "subtitle", "字幕"),
            metrics={
                key: combined[key]
                for key in (
                    "plays",
                    "play_count",
                    "likes",
                    "comments",
                    "shares",
                    "votes",
                    "collects",
                )
                if key in combined
            },
            raw_metadata={"opencli": payload, "list": list_metadata},
        )

    def canonicalize_url(self, url: str) -> str:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or host not in self.profile["hosts"]:
            raise ValueError(f"URL does not belong to {self.platform_key}")

        path = parsed.path.rstrip("/") or "/"
        query = ""
        if self.platform_key == "xiaohongshu":
            allowed = {"xsec_token", "xsec_source"}
            query = urlencode(
                [(key, value) for key, value in parse_qsl(parsed.query) if key in allowed]
            )
        return urlunsplit(("https", host, path, query, ""))

    def item_ref_from_url(self, url: str, creator_id: str = "") -> ItemRef:
        canonical = self.canonicalize_url(url)
        path = urlsplit(canonical).path
        source_id = self._source_id(path)
        if not source_id:
            raise ValueError(f"Unsupported {self.platform_key} content URL")
        return ItemRef(
            source_item_id=source_id,
            creator_id=creator_id,
            source_url=canonical,
        )

    async def _run_json(self, *arguments: str) -> Any:
        try:
            return await self.runner.run_json(*arguments)
        except OpenCLIRunnerError as exc:
            raise PlatformError(str(exc)) from exc

    def _source_id(self, path: str) -> str:
        if self.platform_key == "zhihu":
            for kind, pattern in (
                ("answer", r"/answer/(\d+)"),
                ("article", r"/p/(\d+)"),
                ("question", r"/question/(\d+)"),
            ):
                match = re.search(pattern, path)
                if match:
                    return f"{kind}:{match.group(1)}"
        elif self.platform_key == "bilibili":
            match = re.search(r"/video/((?:BV|av)[0-9A-Za-z]+)", path, re.I)
            if match:
                value = match.group(1)
                return "BV" + value[2:] if value.lower().startswith("bv") else value
        elif self.platform_key == "xiaohongshu":
            match = re.search(r"/(?:explore|discovery/item)/([0-9A-Za-z]+)", path)
            if match:
                return match.group(1)
        else:
            match = re.search(r"/(?:video|note)/(\d+)", path)
            if match:
                return match.group(1)
        return ""


def _rows(payload: Any) -> List[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "items", "results", "rows"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, Mapping)]
        return [payload]
    return []


def _first_row(payload: Any) -> Mapping[str, Any]:
    rows = _rows(payload)
    return rows[0] if rows else {}


def _field_map(payload: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for row in _rows(payload):
        if "field" not in row or "value" not in row:
            return {}
        result[str(row["field"])] = row["value"]
    return result


def _value(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _pick(mapping: Mapping[str, Any], *keys: str) -> str:
    value = _value(mapping, *keys)
    return str(value).strip() if value is not None else ""


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _media_urls(mapping: Mapping[str, Any], keys: Iterable[str]) -> List[str]:
    found: List[str] = []
    for key in keys:
        value = mapping.get(key)
        values: Sequence[Any]
        if isinstance(value, (list, tuple)):
            values = value
        elif value:
            values = re.split(r"[\s,]+", str(value))
        else:
            continue
        for candidate in values:
            text = str(candidate).strip()
            if text.startswith(("https://", "http://")) and text not in found:
                found.append(text)
    return found


def _is_xiaohongshu_shell_title(title: str) -> bool:
    normalized = re.sub(r"\s+", "", title)
    return normalized in {
        "温馨提示",
        "手机号登录",
        "登录",
        "安全验证",
        "验证",
    }


def _looks_like_login_or_verification(content: str) -> bool:
    compact = re.sub(r"\s+", "", content)
    return any(
        marker in compact
        for marker in ("登录后", "手机号登录", "安全验证", "完成验证", "访问异常")
    )


def _title_from_content(content: str) -> str:
    text = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    before_tags = re.split(r"(?=#)", text, maxsplit=1)[0].strip(" -—:：")
    candidate = before_tags or text
    return candidate[:80].strip()


def _compact_douyin_markdown(markdown: str) -> Tuple[str, Dict[str, str]]:
    metadata: Dict[str, str] = {}
    author_match = re.search(
        r"\[!\[([^\]]+)\]\([^)]+\)\]"
        r"\(https://(?:www\.)?douyin\.com/user/[^)]+\)",
        markdown,
    )
    if author_match:
        metadata["author"] = author_match.group(1).strip()

    published_match = re.search(r"发布时间[：:]\s*([^\n]+)", markdown)
    if published_match:
        metadata["published_at"] = published_match.group(1).strip()

    article_head = markdown.split("\n---\n", 1)[0].strip()
    return article_head or markdown, metadata
