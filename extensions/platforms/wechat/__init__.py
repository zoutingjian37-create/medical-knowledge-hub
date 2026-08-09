"""Desktop discovery, public-search compatibility, and link parsing boundaries."""

from .adapter import WeChatAdapter
from .discovery import (
    OpenCLIWeChatDiscoverer,
    WeChatDiscoveryError,
    WeChatUIDiscoverer,
)
from .parser import LocalWeChatParser, OpenCLIWeChatParser
from .pipeline import WeChatPipeline

__all__ = [
    "OpenCLIWeChatParser",
    "LocalWeChatParser",
    "OpenCLIWeChatDiscoverer",
    "WeChatAdapter",
    "WeChatDiscoveryError",
    "WeChatPipeline",
    "WeChatUIDiscoverer",
]
