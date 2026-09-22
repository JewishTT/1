"""Collection Fabric dispatcher (T110, T132, T133, R-03, R-09).

Two-stage scheduler: intelligence (WHAT — utility/novelty/freshness/gain vs
cost) then resource+capability (WHERE — execution class, region, source limits,
capability intersection). Capability gaps surface explicitly; no silent
misroutes.
"""

from __future__ import annotations

from .scheduler import (
    Dispatcher,
    ScheduleDecision,
    ScopeLimits,
    Verdict,
    host_of,
)

__all__ = ["Dispatcher", "ScheduleDecision", "ScopeLimits", "Verdict", "host_of"]