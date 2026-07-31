"""Small, explicit contract implemented by every content platform."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from extensions.processing.normalizer import NormalizedContent


class PlatformError(RuntimeError):
    """Base error raised at the adapter boundary."""


@dataclass(frozen=True)
class AuthResult:
    authenticated: bool
    account: str = ""
    detail: str = ""


@dataclass(frozen=True)
class PlatformHealth:
    available: bool
    authenticated: bool = False
    detail: str = ""


@dataclass(frozen=True)
class CreatorCandidate:
    creator_id: str
    name: str
    alias: str = ""
    avatar_url: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Cursor:
    value: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ItemRef:
    source_item_id: str
    creator_id: str
    source_url: str
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Page:
    items: Tuple[ItemRef, ...]
    next_cursor: Optional[Cursor] = None
    total: Optional[int] = None


@dataclass(frozen=True)
class RawItem:
    source_item_id: str
    creator_id: str
    source_url: str
    data: Dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(ABC):
    """Async collection contract; normalization remains local and synchronous."""

    platform_key: str

    @abstractmethod
    async def authenticate(self) -> AuthResult:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> PlatformHealth:
        raise NotImplementedError

    @abstractmethod
    async def search_creator(self, query: str) -> Tuple[CreatorCandidate, ...]:
        raise NotImplementedError

    @abstractmethod
    async def list_creator_items(
        self, creator_id: str, cursor: Optional[Cursor] = None
    ) -> Page:
        raise NotImplementedError

    @abstractmethod
    async def fetch_item(self, item_ref: ItemRef) -> RawItem:
        raise NotImplementedError

    @abstractmethod
    def normalize_item(self, raw_item: RawItem) -> NormalizedContent:
        raise NotImplementedError

    @abstractmethod
    def canonicalize_url(self, url: str) -> str:
        raise NotImplementedError
