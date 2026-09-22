"""Entity/ID mismatch modifier (T094)."""

from __future__ import annotations

from .mismatch import (
    BADGE_MATCH_SPEC,
    EntityLink,
    badge_match,
    dedupe_entity_links,
    modify_urgency,
    normalize_value,
    pick_canonical,
)

__all__ = [
    "BADGE_MATCH_SPEC",
    "EntityLink",
    "badge_match",
    "dedupe_entity_links",
    "modify_urgency",
    "normalize_value",
    "pick_canonical",
]