"""Configuration for the engagement fabric (Feature 032).

Separate from the GhostLine config because these are different concerns: GhostLine's
are *provider credentials*, and every one of them is a secret. Nothing here is a secret.
The fabric's only setting is where its log lives, because that location is also the
retention question — a compliance regime wants the event log somewhere with a lifecycle
attached, and a config knob is how you get there without a code change.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from specops.ghostline.loader import REPO_ROOT

__all__ = ("clear_engagement_config_cache", "engagement_dir", "events_path")

_DEFAULT_DIR = REPO_ROOT / "logs" / "engagement"


@lru_cache(maxsize=1)
def engagement_dir() -> Path:
    """Where the engagement log lives.

    ``GHOSTLINE_ENGAGEMENT_DIR`` overrides it, which matters because the retention
    window is a property of the *directory*, not of this module — point it at a volume
    with a lifecycle policy and the compliance question answers itself.
    """
    import os

    return Path(os.environ.get("GHOSTLINE_ENGAGEMENT_DIR", str(_DEFAULT_DIR)))


def events_path() -> Path:
    """The JSONL event log."""
    return engagement_dir() / "events.jsonl"


def clear_engagement_config_cache() -> None:
    """Drop the cached directory so the next read sees the current environment."""
    engagement_dir.cache_clear()
