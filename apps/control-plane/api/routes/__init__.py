"""HTTP route modules for the control plane.

Importing this package applies ``api.path_shim`` FIRST, so every route module's
cross-app imports (``tda.*``, ``acquisition.*``, ``domain.*``) resolve to the
same modules under a bare interpreter, under pytest and under uvicorn. The
shim is applied here — at the package boundary — rather than in each route
module because a route module's own import block is sorted, and ``tda`` /
``acquisition`` have to be re-pointed at their owning app before any of those
statements run.
"""

from __future__ import annotations

from api import path_shim  # noqa: F401 - must precede every cross-app import below
from api.routes import investigation_context  # noqa: E402,F401
