"""Registry that keeps installed adapters separate from future placeholders."""

from dataclasses import asdict, dataclass
from typing import Dict, Tuple

from .base import PlatformAdapter


class PlatformUnavailableError(LookupError):
    """Raised when a known platform has no installed adapter."""


@dataclass(frozen=True)
class PlatformRegistration:
    key: str
    display_name: str
    installed: bool
    version: str = ""
    reason: str = ""

    def to_dict(self):
        return asdict(self)


class PlatformRegistry:
    def __init__(self):
        self._registrations: Dict[str, PlatformRegistration] = {}
        self._adapters: Dict[str, PlatformAdapter] = {}

    def register(
        self, adapter: PlatformAdapter, display_name: str, version: str = ""
    ) -> None:
        key = adapter.platform_key
        self._ensure_new(key)
        self._adapters[key] = adapter
        self._registrations[key] = PlatformRegistration(
            key=key,
            display_name=display_name,
            installed=True,
            version=version,
        )

    def register_unavailable(
        self,
        key: str,
        display_name: str,
        reason: str = "采集器未安装",
    ) -> None:
        self._ensure_new(key)
        self._registrations[key] = PlatformRegistration(
            key=key,
            display_name=display_name,
            installed=False,
            reason=reason,
        )

    def get_adapter(self, key: str) -> PlatformAdapter:
        if key in self._adapters:
            return self._adapters[key]
        if key in self._registrations:
            raise PlatformUnavailableError(f"平台 {key} 已登记，但采集器未安装")
        raise KeyError(f"未知平台: {key}")

    def list_platforms(self) -> Tuple[PlatformRegistration, ...]:
        return tuple(self._registrations.values())

    def _ensure_new(self, key: str) -> None:
        if not key or key in self._registrations:
            raise ValueError(f"平台键无效或已登记: {key}")


def build_default_registry() -> PlatformRegistry:
    from .opencli.adapter import OPENCLI_ADAPTER_VERSION, OpenCLIAdapter
    from .wechat.adapter import WeChatAdapter

    registry = PlatformRegistry()
    registry.register(WeChatAdapter(), display_name="微信公众号", version="1.0")
    for key, display_name in (
        ("zhihu", "知乎"),
        ("bilibili", "哔哩哔哩"),
        ("xiaohongshu", "小红书"),
        ("douyin", "抖音"),
    ):
        registry.register(
            OpenCLIAdapter(key),
            display_name=display_name,
            version=OPENCLI_ADAPTER_VERSION,
        )
    return registry


platform_registry = build_default_registry()
