"""Shared processing models used by every platform adapter."""

from .normalizer import NormalizedContent
from .documents import MarkdownDocument

__all__ = ["MarkdownDocument", "NormalizedContent"]
