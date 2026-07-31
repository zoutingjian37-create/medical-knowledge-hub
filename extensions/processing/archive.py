"""Filtering, URL deduplication, and local Obsidian Markdown archiving."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .documents import MarkdownDocument


_AD_TITLE = re.compile(
    r"(广告|商务合作|课程.{0,6}(报名|优惠)|训练营|招生|团购|立即购买|限时优惠)",
    re.IGNORECASE,
)

_PROMOTIONAL_BLOCK = re.compile(
    r"(公益课.{0,12}(上线|开课)|本课程.{0,80}(公益|免费).{0,80}(视频|开课|参与学习|不是.{0,8}广告)|"
    r"本课程.{0,12}课件|您不妨点击|绝对精品.{0,16}(赠送|领取)|"
    r"发送.{0,12}(报名|关键词).{0,12}公众号|"
    r"加入.{0,12}(微信|学习|课程).{0,4}群|课程.{0,12}(详细介绍|学员评价|训练营|报名)|"
    r"更多.{0,12}(科研|统计).{0,8}课程|一键分析.{0,16}(工具|平台)|"
    r"郑老师.{0,12}(工具|平台|团队).{0,16}(开发|研制|下载|获得)|"
    r"medsta\.cn|关于.{0,12}团队及公众号|全国较大的.{0,12}公众号|"
    r"课程训练营详情|阅读原文|扫码.{0,8}(咨询|报名|添加))",
    re.IGNORECASE | re.DOTALL,
)

_TRAILING_PROMOTION = re.compile(
    r"(本文更多疑问.{0,20}(关键词|公众号)|最后提醒.{0,30}(报名|课程群)|"
    r"关于.{0,12}团队及公众号|课程训练营详情)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class ArchiveResult:
    saved: bool
    reason: str
    path: Path


class ObsidianArchiver:
    def __init__(self, vault_path: Path, folder: str = "微信公众号"):
        self._folder = Path(vault_path).expanduser().resolve() / folder

    def archive(self, document: MarkdownDocument) -> ArchiveResult:
        if is_advertisement_title(document.title):
            return ArchiveResult(False, "advertisement", self._folder)

        self._folder.mkdir(parents=True, exist_ok=True)
        duplicate = self._find_by_source(document.source_url)
        if duplicate is not None:
            return ArchiveResult(False, "duplicate", duplicate)

        path = self._available_path(_safe_filename(document.title))
        frontmatter = (
            "---\n"
            f"title: {json.dumps(document.title, ensure_ascii=False)}\n"
            f"author: {json.dumps(document.author, ensure_ascii=False)}\n"
            f"published: {json.dumps(document.published_at, ensure_ascii=False)}\n"
            f"source: {json.dumps(document.source_url, ensure_ascii=False)}\n"
            "platform: wechat\n"
            "---\n\n"
        )
        cleaned = clean_markdown(document.markdown)
        path.write_text(frontmatter + cleaned + "\n", "utf-8")
        return ArchiveResult(True, "saved", path)

    def _find_by_source(self, source_url: str) -> Path | None:
        marker = f"source: {json.dumps(source_url, ensure_ascii=False)}"
        for candidate in self._folder.glob("*.md"):
            try:
                if marker in candidate.read_text("utf-8"):
                    return candidate
            except (OSError, UnicodeDecodeError):
                continue
        return None

    def _available_path(self, stem: str) -> Path:
        candidate = self._folder / f"{stem}.md"
        number = 2
        while candidate.exists():
            candidate = self._folder / f"{stem} ({number}).md"
            number += 1
        return candidate


def _safe_filename(title: str) -> str:
    value = re.sub(r'[\\/:*?"<>|]', "-", title).strip(" .")
    return value[:80] or "wechat-article"


def is_advertisement_title(title: str) -> bool:
    return bool(_AD_TITLE.search(title))


def clean_markdown(markdown: str) -> str:
    """Remove promotional blocks while preserving the article's useful body."""
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n").strip()
    head, separator, body = normalized.partition("\n---\n")
    if not separator:
        head, body = "", normalized

    blocks = [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]

    leading_promotions = sum(
        bool(_PROMOTIONAL_BLOCK.search(block)) for block in blocks[:12]
    )
    if leading_promotions:
        for index, block in enumerate(blocks):
            if _is_substantive(block) and not _PROMOTIONAL_BLOCK.search(block):
                blocks = blocks[index:]
                break

    trailing_start = next(
        (
            index
            for index, block in enumerate(blocks)
            if index >= len(blocks) * 0.6 and _TRAILING_PROMOTION.search(block)
        ),
        len(blocks),
    )
    blocks = blocks[:trailing_start]
    blocks = [
        block
        for block in blocks
        if not _PROMOTIONAL_BLOCK.search(block) and not _is_layout_artifact(block)
    ]

    cleaned_body = "\n\n".join(blocks).strip()
    if head:
        return f"{head.strip()}\n\n---\n\n{cleaned_body}".strip()
    return cleaned_body


def _is_substantive(block: str) -> bool:
    if block.lstrip().startswith(("![", "[", "<", "#", ">")):
        return False
    plain = re.sub(r"[*_`~#>\[\](){}]", "", block)
    plain = re.sub(r"https?://\S+", "", plain)
    return len(re.sub(r"\s+", "", plain)) >= 45


def _is_layout_artifact(block: str) -> bool:
    compact = re.sub(r"[\s*_]", "", block)
    return not compact or bool(re.fullmatch(r"\d{1,2}", compact))
