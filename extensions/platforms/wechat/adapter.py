"""Thin adapter over the independent WeChat public-link parser."""

from datetime import datetime
from hashlib import sha256
from typing import Optional
from urllib.parse import parse_qsl, urlsplit

from extensions.processing.normalizer import NormalizedContent
from ..base import (
    AuthResult,
    Cursor,
    ItemRef,
    Page,
    PlatformAdapter,
    PlatformError,
    PlatformHealth,
    RawItem,
)
from .parser import OpenCLIWeChatParser
from .public_link import canonicalize_public_article_url


class WeChatAdapter(PlatformAdapter):
    platform_key = "wechat"
    def __init__(self, parser: Optional[OpenCLIWeChatParser] = None):
        self._parser = parser or OpenCLIWeChatParser()

    async def authenticate(self) -> AuthResult:
        return AuthResult(
            authenticated=True,
            account="local public-link parser",
            detail="No WeChat Official Account backend login is required.",
        )

    async def health(self) -> PlatformHealth:
        return PlatformHealth(
            available=True,
            authenticated=True,
            detail="Paste a public WeChat article link to collect it locally.",
        )

    async def search_creator(self, query: str):
        raise PlatformError(
            "WeChat has retired third-party account discovery; paste an article link instead."
        )

    async def list_creator_items(
        self, creator_id: str, cursor: Optional[Cursor] = None
    ) -> Page:
        raise PlatformError(
            "WeChat has retired batch account history access; paste article links instead."
        )

    def item_ref_from_url(self, url: str) -> ItemRef:
        source_url = self.canonicalize_url(url)
        parsed = urlsplit(source_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=False))
        creator_id = query.get("__biz", "")
        path_id = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        source_item_id = path_id if path_id and path_id != "s" else ""
        if not source_item_id:
            source_item_id = sha256(source_url.encode("utf-8")).hexdigest()[:24]
        return ItemRef(
            source_item_id=source_item_id,
            creator_id=creator_id,
            source_url=source_url,
        )

    async def fetch_item(self, item_ref: ItemRef) -> RawItem:
        source_url = self.canonicalize_url(item_ref.source_url)
        try:
            document = await self._parser.parse(source_url)
        except (RuntimeError, ValueError) as exc:
            raise PlatformError(str(exc)) from exc
        return RawItem(
            source_item_id=item_ref.source_item_id,
            creator_id=item_ref.creator_id,
            source_url=source_url,
            data={
                "title": document.title,
                "author": document.author,
                "published_at": document.published_at,
                "markdown": document.markdown,
                "list_metadata": dict(item_ref.raw_metadata),
            },
        )

    def normalize_item(self, raw_item: RawItem) -> NormalizedContent:
        data = raw_item.data
        published_at = _parse_published_at(data.get("published_at"))
        metadata = dict(data.get("list_metadata") or {})
        metadata.update(
            {key: value for key, value in data.items() if key != "list_metadata"}
        )
        return NormalizedContent(
            platform=self.platform_key,
            creator_id=raw_item.creator_id,
            creator_name=data.get("author") or metadata.get("author", ""),
            source_item_id=raw_item.source_item_id,
            content_type="article",
            title=data.get("title") or metadata.get("title", ""),
            body_html="",
            body_text=data.get("markdown", ""),
            published_at=published_at,
            source_url=raw_item.source_url,
            raw_metadata=metadata,
        )

    def canonicalize_url(self, url: str) -> str:
        try:
            return canonicalize_public_article_url(url)
        except ValueError as exc:
            raise PlatformError(str(exc)) from exc


def _parse_published_at(value) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
