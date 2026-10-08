"""Root conftest: pin import resolution so collection order stops deciding meaning.

Seven top-level package names exist twice in this repository:

    contract, evidence, integration, payload, resolution, search, tda

The one that bites hardest is ``tda``: ``apps/projection/tda`` and
``apps/science/tda`` both claim it, and which one a test imports depends purely on
which source directory landed on ``sys.path`` first. ``api/routes/__init__.py``
already resolves this deliberately via ``api.path_shim`` -- ``science_tda.py``
documents that its ``tda`` is the science one -- but a full-suite pytest run builds
``sys.path`` in collection order, not in the order the path shims assume. The visible
symptom is ``ModuleNotFoundError: No module named 'tda.validated'`` from a module
whose file exists and passes on its own.

This does not rename anything and does not change any import. It only makes the
ordering the shims already assume explicit and stable: ``apps/projection`` ahead of
``apps/science``, ``apps/shared`` first so ``domain``/``events``/``storage`` resolve
to the one implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

APPS = Path(__file__).resolve().parent / "apps"

#: Priority order, most specific first. Earlier wins a name collision.
_ORDER = (
    "shared",
    "projection",
    "interpretation",
    "control-plane",
    "acquisition",
    "admission",
    "science",
    "zero",
)

#: Package name -> which app owns it when both claim it. This is the project's own
#: stated preference, taken from ``api/routes/science_tda.py``: the API wants the
#: science TDA, the projection tests want the projection TDA, and each gets it because
#: its own directory is first when it imports.
_OWNERS = {
    "tda": "projection",
    "search": "projection",
    "evidence": "admission",
    "resolution": "admission",
}


def _apply_import_order() -> None:
    for name in reversed(_ORDER):
        path = str(APPS / name)
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


_apply_import_order()


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """Re-assert the order after collection has touched imports.

    Cheap and idempotent. A session that imported the wrong ``tda`` under a different
    working directory would otherwise keep it for the whole run.
    """
    _apply_import_order()