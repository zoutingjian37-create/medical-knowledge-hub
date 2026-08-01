"""Identifier-first literature deduplication."""

from .discovery import LiteratureItem


def unique_items(items) -> tuple[LiteratureItem, ...]:
    unique = []
    seen = set()
    for item in items:
        keys = set(item.identity_keys)
        if keys and keys & seen:
            continue
        unique.append(item)
        seen.update(keys)
    return tuple(unique)
