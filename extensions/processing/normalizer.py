"""Platform-neutral content produced by collection adapters."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class NormalizedContent:
    """The stable boundary between platform collection and later processing."""

    platform: str
    creator_id: str
    creator_name: str
    source_item_id: str
    content_type: str
    title: str
    body_html: str
    body_text: str
    published_at: Optional[datetime]
    source_url: str
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    audio: List[str] = field(default_factory=list)
    transcript: str = ""
    tags: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def identity(self) -> Tuple[str, str]:
        """Return the cross-platform idempotency key."""

        return self.platform, self.source_item_id
