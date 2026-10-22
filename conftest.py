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

ROOT = Path(__file__).resolve().parent
APPS = ROOT / "apps"

#: Priority order, most specific first. Earlier wins a name collision.
#:
#: `specops` is deliberately NOT here. `apps/specops` is the package directory, so it is
#: its PARENT (`apps/`, added separately below) that makes `import specops` resolve --
#: adding `apps/specops` itself does nothing for that and actively breaks something else:
#: it puts a `ghostline/` directory on `sys.path`, so `import ghostline` resolves to
#: `apps/specops/ghostline` as a namespace package and silently shadows the vendored
#: donor at `donors/ghostline/src/ghostline`. Every donor module then fails to import
#: with `No module named 'ghostline.taxonomy'`, which reads as a broken donor rather
#: than as a path-ordering bug.
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

#: ``bench`` is a workspace member whose importable package is ``bench/bench/``, but
#: the repo root also holds a plain ``bench/`` directory. With only the root on
#: ``sys.path``, ``import bench`` resolves to the *directory* as a namespace package and
#: ``from bench import harness`` fails -- the real module is one level deeper. This was
#: a collection error at the repo root for every run until WP-0 T007.
#
#: Regular packages beat namespace packages during the path scan regardless of order, so
#: merely putting ``bench/`` on the path is enough; it does not have to precede the root.
_BENCH = ROOT / "bench"

#: Package name -> which app owns it when both claim it. This is the project's own
#: stated preference, taken from ``api/routes/science_tda.py``: the API wants the
#: science TDA, the projection tests want the projection TDA, and each gets it because
#: its own directory is first when it imports.
_OWNERS = {
    "tda": "projection",
    "search": "projection",
    "evidence": "interpretation",
    "resolution": "admission",
}


def _apply_import_order() -> None:
    if str(_BENCH) not in sys.path:
        sys.path.insert(0, str(_BENCH))
    for name in reversed(_ORDER):
        path = str(APPS / name)
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
    # `apps/` resolves `specops` (package dir apps/specops), `acquisition`
    # (namespace dir apps/acquisition) and `bulk-ingestion`. It goes to the BACK,
    # not the front: it is the broadest entry and any specific source dir above must
    # win a name collision against it.
    apps_root = str(APPS)
    if apps_root in sys.path:
        sys.path.remove(apps_root)
    sys.path.append(apps_root)


_apply_import_order()


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """Re-assert the order after collection has touched imports.

    Cheap and idempotent. A session that imported the wrong ``tda`` under a different
    working directory would otherwise keep it for the whole run.
    """
    _apply_import_order()