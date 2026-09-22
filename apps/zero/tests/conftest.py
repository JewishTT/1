"""Test bootstrap: make `zero` and `events` importable for hermetic pytest runs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parents[1]  # apps/zero
_APPS_DIR = Path(__file__).resolve().parents[2]  # apps
_SHARED_DIR = _APPS_DIR / "shared"

for _path in (_SRC_DIR, _APPS_DIR, _SHARED_DIR):
    _as_str = str(_path)
    if _as_str not in sys.path:
        sys.path.insert(0, _as_str)

from zero.type_detector import TypeDetector  # noqa: E402


@pytest.fixture
def detector() -> TypeDetector:
    """Deterministic detector with no DNS probe."""
    return TypeDetector()


@pytest.fixture
def dns_true() -> TypeDetector:
    """Detector whose DNS probe always confirms a record (bonus path)."""

    def _dns_exists(_domain: str) -> bool:
        return True

    return TypeDetector(dns_exists=_dns_exists)