"""Platform-neutral Markdown document passed to filtering and archiving."""

from dataclasses import dataclass

from .normalizer import NormalizedContent


@dataclass(frozen=True)
class MarkdownDocument:
    source_url: str
    title: str
    author: str
    published_at: str
    markdown: str


def from_normalized(content: NormalizedContent) -> MarkdownDocument:
    """Convert any installed platform adapter output into the shared queue format."""

    published_at = content.published_at.isoformat() if content.published_at else ""
    metadata = [
        f"> 来源平台: {content.platform}",
        f"> 作者: {content.creator_name or '未识别'}",
        f"> 原文链接: {content.source_url}",
    ]
    if published_at:
        metadata.insert(2, f"> 发布时间: {published_at}")

    sections = [
        f"# {content.title}",
        "\n".join(metadata),
        content.body_text.strip(),
    ]
    transcript = content.transcript.strip()
    if transcript and transcript not in content.body_text:
        sections.extend(("## 字幕", transcript))

    return MarkdownDocument(
        source_url=content.source_url,
        title=content.title,
        author=content.creator_name,
        published_at=published_at,
        markdown="\n\n".join(section for section in sections if section),
    )
