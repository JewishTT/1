"""Deterministic import shim for cross-app shared code.

The workspace venv injects every member source dir onto sys.path in an order
that is NOT guaranteed: control-plane also ships a top-level ``domain`` package,
conflicting with shared's ``domain`` (invariants). This shim moves the shared
source dir to the front of sys.path so ``from domain import …`` resolves to the
shared package everywhere in this app.
"""

from __future__ import annotations

import sys
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parents[2]  # repo root
_SHARED = str(_WORKSPACE / "apps" / "shared")

if _SHARED in sys.path:
    sys.path.remove(_SHARED)
sys.path.insert(0, _SHARED)