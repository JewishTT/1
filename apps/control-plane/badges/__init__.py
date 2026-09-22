"""Capability-annotated engine façade (T095)."""

from __future__ import annotations

from .facade import (
    BADGE_CATALOG,
    ENGINE_ALIASES,
    ENGINE_BADGES,
    BadgeFacade,
    BadgeGap,
    BadgeNotFoundError,
    EngineBadge,
    default_facade,
)

__all__ = [
    "BADGE_CATALOG",
    "ENGINE_ALIASES",
    "ENGINE_BADGES",
    "BadgeFacade",
    "BadgeGap",
    "BadgeNotFoundError",
    "EngineBadge",
    "default_facade",
]