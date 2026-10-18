"""Deterministic import shim for cross-app shared code.

The workspace venv injects every member *source dir* onto sys.path in an order
that is NOT guaranteed, and two member dirs collide on first-party names:

``tda``
    ``apps/science/tda`` (VR persistence, Takens series, PHoDMS) and
    ``apps/projection/tda`` (diagram/feature materializers) are both top-level
    ``tda`` packages. ``apps/projection`` currently wins the .pth ordering, so a
    bare ``from scitda.persistence import …`` resolves to the projection package
    and dies with ``ModuleNotFoundError: No module named 'scitda.persistence'``.
    The science package is the only TDA surface the control plane imports by
    name; the projection half stays reachable by file path
    (``api/routes/network.py`` loads ``tda/features.py`` that way).

``acquisition``
    ``apps/acquisition`` ships no ``__init__.py``; its members import each other
    as ``acquisition.<module>`` and are resolved as a namespace package, which
    requires the *parent* ``apps/`` dir on sys.path. Without it ``api.routes.
    entities`` cannot import and the app does not boot at all.

``specops``
    ``apps/specops`` is a plain source directory that is NOT a uv workspace
    member, so nothing installs a ``specops`` distribution and no ``.pth`` claims
    it. It resolves through the ``apps/`` entry below (the package directory
    *is* ``apps/specops``, so it is its PARENT that belongs on the path). Every
    ``api/routes/specops_*.py`` guards its donor import with ``except Exception``
    and degrades to a 503, so if that entry ever went missing the department
    would not fail loudly -- it would turn into six 503s that read as "the donor
    is down" rather than "the package is not importable".

This shim therefore re-orders sys.path deterministically, front to back:
``apps/`` (namespace packages + ``specops``), ``apps/science`` (beats
``apps/projection`` for ``tda``), ``apps/shared`` (``domain`` invariants).
Importing it before the cross-app imports is what makes those imports resolve
the same way under a bare interpreter, under pytest and under uvicorn.

It lives inside the ``api`` package, not at the app root, on purpose: a
top-level ``path_shim`` module would collide with ``apps/projection/path_shim``
(whichever app root happens to precede on sys.path would silently win), and a
root-level module is not in this app's wheel ``packages`` list, so it would be
missing from a non-editable install. ``api.path_shim`` is unambiguous and ships.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APPS = Path(__file__).resolve().parents[2]  # apps/ (parents: api -> control-plane -> apps)
# Inserted last-to-first: each is pushed to the front, so the list reads as the
# intended precedence once applied.
_SOURCES = ("shared", "science", "")

for _name in _SOURCES:
    _DIR = str(_APPS / _name) if _name else str(_APPS)
    while _DIR in sys.path:
        sys.path.remove(_DIR)
    sys.path.insert(0, _DIR)
