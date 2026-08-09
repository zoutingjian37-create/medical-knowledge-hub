"""Independent OpenCLI parser for one public WeChat article link."""

import asyncio
from datetime import datetime, timezone
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional

from bs4 import BeautifulSoup
import httpx
from markdownify import markdownify

from extensions.platforms.opencli.runner import OpenCLIRunner, OpenCLIRunnerError
from extensions.processing.documents import MarkdownDocument

from .public_link import canonicalize_public_article_url
from .vision import SHANGHAI_TZ


DEFAULT_TEMP_ROOT = Path(r"D:\Codex\cache\medical-knowledge-hub\opencli-temp")


class LocalWeChatParser:
    """Parse one public article directly without a browser extension."""

    def __init__(self, client=None, timeout: float = 30):
        self._client = client
        self._timeout = max(5, float(timeout))

    async def parse(self, url: str) -> MarkdownDocument:
        public_url = canonicalize_public_article_url(url)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/138 Safari/537.36"
            ),
            "Referer": "https://mp.weixin.qq.com/",
        }
        if self._client is None:
            async with httpx.AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=self._timeout,
            ) as client:
                response = await client.get(public_url)
        else:
            response = await self._client.get(public_url, headers=headers)
        response.raise_for_status()
        return _document_from_public_html(public_url, response.text)


class OpenCLIWeChatParser:
    def __init__(
        self,
        runner: Optional[OpenCLIRunner] = None,
        temp_root: Optional[Path] = None,
        retry_delay: float = 5,
        max_attempts: int = 2,
    ):
        self._runner = runner or OpenCLIRunner()
        self._temp_root = Path(temp_root or DEFAULT_TEMP_ROOT)
        self._retry_delay = max(0, retry_delay)
        self._max_attempts = max(1, max_attempts)

    async def parse(self, url: str) -> MarkdownDocument:
        public_url = canonicalize_public_article_url(url)
        self._temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._temp_root) as directory:
            output = Path(directory)
            payload = None
            markdown_files = []
            for attempt in range(self._max_attempts):
                try:
                    payload = await self._runner.run_json(
                        "weixin",
                        "download",
                        "--url",
                        public_url,
                        "--output",
                        str(output),
                        "--download-images",
                        "false",
                        timeout=120,
                    )
                except OpenCLIRunnerError as exc:
                    raise RuntimeError(str(exc)) from exc
                markdown_files = sorted(output.rglob("*.md"))
                if markdown_files:
                    break
                status = _payload_status(payload)
                retryable = "verification required" in status.lower()
                if not retryable or attempt + 1 >= self._max_attempts:
                    detail = f": {status}" if status else ""
                    raise RuntimeError(
                        f"OpenCLI did not produce a Markdown article{detail}"
                    )
                await asyncio.sleep(self._retry_delay)
            markdown = markdown_files[0].read_text("utf-8")
            metadata = _first_row(payload)
            return MarkdownDocument(
                source_url=public_url,
                title=str(metadata.get("title") or _heading(markdown)),
                author=str(metadata.get("author") or ""),
                published_at=str(metadata.get("publish_time") or ""),
                markdown=markdown,
            )


def _first_row(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, list):
        return next((row for row in payload if isinstance(row, Mapping)), {})
    if isinstance(payload, Mapping):
        for key in ("data", "items", "results", "rows"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return next(
                    (row for row in rows if isinstance(row, Mapping)), {}
                )
        return payload
    return {}


def _heading(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "WeChat article"


def _payload_status(payload: Any) -> str:
    row = _first_row(payload)
    return str(row.get("status") or row.get("error") or "").strip()


def _document_from_public_html(url: str, html: str) -> MarkdownDocument:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("#js_content")
    if content is None:
        page_text = soup.get_text(" ", strip=True)
        if any(label in page_text for label in ("环境异常", "访问过于频繁", "完成验证")):
            raise RuntimeError("WeChat returned a verification page; retry later")
        raise RuntimeError("WeChat public article body was not found")

    title = _first_text(soup, "#activity-name", "h1.rich_media_title")
    if not title:
        meta = soup.select_one('meta[property="og:title"]')
        title = str(meta.get("content") or "").strip() if meta else ""
    author = _first_text(soup, "#js_name", ".rich_media_meta_nickname")
    published_at = _published_at(soup, html)

    for node in content.select("script, style, noscript, svg"):
        node.decompose()
    _normalize_body_images(content)
    body = markdownify(
        str(content),
        heading_style="ATX",
        bullets="-",
    )
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if not title or not author or len(re.sub(r"\s+", "", body)) < 80:
        raise RuntimeError("WeChat public article metadata or body is incomplete")
    metadata = [
        f"> 公众号: {author}",
        f"> 原文链接: {url}",
    ]
    if published_at:
        metadata.append(f"> 发布日期: {published_at}")
    return MarkdownDocument(
        source_url=url,
        title=title,
        author=author,
        published_at=published_at,
        markdown=f"# {title}\n\n" + "\n".join(metadata) + f"\n\n---\n\n{body}\n",
    )


def _normalize_body_images(content) -> None:
    """Expose WeChat lazy-loaded images as remote Markdown image links."""
    for image in content.select("img"):
        source = next(
            (
                str(image.get(attribute) or "").strip()
                for attribute in ("data-src", "data-original", "src")
                if str(image.get(attribute) or "").strip()
            ),
            "",
        )
        if not source or source.casefold().startswith("data:"):
            image.decompose()
            continue
        if source.startswith("//"):
            source = "https:" + source
        image["src"] = source
        if not str(image.get("alt") or "").strip():
            image["alt"] = str(image.get("title") or "正文图片").strip()
        for attribute in ("data-src", "data-original"):
            image.attrs.pop(attribute, None)


def _first_text(soup: BeautifulSoup, *selectors: str) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            value = node.get_text(" ", strip=True)
            if value:
                return value
    return ""


def _published_at(soup: BeautifulSoup, html: str) -> str:
    visible = _first_text(soup, "#publish_time", ".rich_media_meta_text")
    match = re.search(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", visible)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    timestamp = re.search(r"\bct\s*=\s*[\"']?(\d{10})", html)
    if timestamp:
        return datetime.fromtimestamp(
            int(timestamp.group(1)), timezone.utc
        ).astimezone(SHANGHAI_TZ).date().isoformat()
    return ""
