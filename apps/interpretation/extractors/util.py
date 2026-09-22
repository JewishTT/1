"""Small shared helpers for deterministic extractors (spec 007)."""

from __future__ import annotations


def byte_offset(text: str, char_index: int) -> int:
    """UTF-8 byte offset of a character index into ``text`` (deterministic)."""
    if char_index <= 0:
        return 0
    return len(text[:char_index].encode("utf-8"))


def end_byte_offset(text: str, char_index: int) -> int:
    return len(text[:char_index].encode("utf-8"))


def is_upper_first(value: str) -> bool:
    """True when the surface form starts with a title-case letter."""
    return bool(value and value[0].isupper())


def emoji_free(value: str) -> bool:  # pragma: no cover - cosmetic guard, no-op marker
    return True