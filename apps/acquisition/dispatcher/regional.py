"""Region-level backpressure (T113).

The dispatcher decides *where* a task runs. Region backpressure guards that
decision per region: a region whose frontier is stacking READY work or whose
in-flight jobs exceed capacity is throttled, and a region that has blown its
deadline (oldest item past the lag ceiling) is halted until it drains. The
same pure rules drive live dispatch and the chaos/bench harnesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ids import normalize_region


class Verdict(StrEnum):
    GO = "go"
    THROTTLE = "throttle"
    HALT = "halt"


@dataclass(frozen=True)
class RegionPressure:
    """One region's current pressure snapshot."""

    region: str
    ready_depth: int = 0
    in_flight: int = 0
    capacity: int = 0
    oldest_age_s: float = 0.0


@dataclass
class RegionBackpressure:
    """Per-region gate: GO while within capacity, THROTTLE while draining."""

    capacity_per_region: int = 64
    throttle_factor: float = 1.5
    lag_ceiling_s: float = 300.0
    _regions: dict[str, RegionPressure] = field(default_factory=dict)

    def observe(self, pressure: RegionPressure) -> None:
        region = normalize_region(pressure.region)
        self._regions[region] = RegionPressure(
            region=region,
            ready_depth=pressure.ready_depth,
            in_flight=pressure.in_flight,
            capacity=pressure.capacity or self.capacity_per_region,
            oldest_age_s=pressure.oldest_age_s,
        )

    def verdict(self, region: str) -> Verdict:
        """Decide for one region from its last observed pressure."""
        region = normalize_region(region)
        p = self._regions.get(region)
        if p is None:
            return Verdict.GO
        total = p.ready_depth + p.in_flight
        hard_cap = int(p.capacity * self.throttle_factor)
        if p.oldest_age_s > self.lag_ceiling_s or total >= hard_cap:
            return Verdict.HALT
        if total > p.capacity:
            return Verdict.THROTTLE
        return Verdict.GO

    def can_dispatch(self, region: str) -> bool:
        return self.verdict(region) == Verdict.GO

    def report(self) -> dict[str, object]:
        return {
            region: {
                "ready": p.ready_depth,
                "in_flight": p.in_flight,
                "capacity": p.capacity,
                "total": p.ready_depth + p.in_flight,
                "oldest_age_s": round(p.oldest_age_s, 3),
                "verdict": self.verdict(region).value,
            }
            for region, p in sorted(self._regions.items())
        }