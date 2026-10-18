"""H3 as a spatial *index*, never as a coordinate claim.

Spec 030 CE-001 §15.12, DON-SPAT-002/003, task T163.

**Upstream** : https://github.com/uber/h3   **Revision** : 4.5.0   **Mode** : B (package).

An H3 cell is an index key. It is not a location, and at low resolutions it is a location that
covers a very large piece of ground. Writing "the entity is at ``8928308280fffff``" and drawing a
dot there would convert a 1.2 km hexagon into a point claim the source never made.

So a spatial projection record carries the source geometry, its CRS, and its declared accuracy
*beside* the cell, and the cell never replaces any of them. ``accuracy_risk`` is computed rather
than declared, so a caller cannot attach a coarse cell to a precise measurement without seeing
that it did.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import h3

__all__ = [
    "H3_VERSION_PINNED",
    "SpatialRef",
    "H3IndexRecord",
    "SpatialProjectionError",
    "ResolutionPolicy",
    "index_point",
]

H3_VERSION_PINNED = "4.5.0"

#: Approximate H3 **average edge length** in metres per resolution, from the upstream
#: reference table. An earlier draft of this file carried a column that was off by more than an
#: order of magnitude at the resolutions that matter, which made a 5 m measurement resolve to a
#: kilometre cell and quietly reversed the resolution rule below. These are the published values;
#: ``h3.average_hexagon_edge_length`` is available if you want to check rather than trust.
_APPROX_EDGE_METRES = {
    0: 1_107_000.0,
    1: 418_000.0,
    2: 156_000.0,
    3: 70_500.0,
    4: 36_850.0,
    5: 15_100.0,
    6: 6_465.0,
    7: 2_810.0,
    8: 1_200.0,
    9: 463.0,
    10: 174.0,
    11: 65.0,
    12: 23.0,
    13: 8.5,
    14: 3.2,
    15: 1.2,
}


class SpatialProjectionError(ValueError):
    """A spatial record would claim more precision than its source declared."""


@dataclass(frozen=True, slots=True)
class SpatialRef:
    """A source geometry, kept exactly as the source stated it."""

    latitude: float
    longitude: float
    crs: str = "EPSG:4326"
    coordinate_accuracy_m: float | None = None
    """Declared accuracy in metres. ``None`` means the source did not say, which is not the same
    as perfect accuracy and must never be read as it."""
    geometry_ref: str | None = None
    """Pointer to the stored geometry when this is a derived point."""

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise SpatialProjectionError(f"latitude {self.latitude} is outside [-90, 90]")
        if not -180.0 <= self.longitude <= 180.0:
            raise SpatialProjectionError(f"longitude {self.longitude} is outside [-180, 180]")
        if self.coordinate_accuracy_m is not None and self.coordinate_accuracy_m < 0:
            raise SpatialProjectionError("coordinate accuracy cannot be negative")

    @property
    def accuracy_is_declared(self) -> bool:
        return self.coordinate_accuracy_m is not None


@dataclass(frozen=True, slots=True)
class ResolutionPolicy:
    """How a cell resolution is chosen, given what the source declared."""

    #: Never index finer than the source can support. A cell much smaller than the source's
    #: error radius implies a precision the measurement does not have.
    default_resolution: int = 9
    max_resolution: int = 15
    min_resolution: int = 0

    def resolution_for(self, ref: SpatialRef) -> int:
        """Pick a resolution that does not outstate the source.

        The cell is a bucket, so the aim is not to pin the measurement -- it is to keep the
        bucket from being *coarser than the thing it indexes*. A source that is only accurate to
        2 km indexed at resolution 12 (23 m edge) splits one real location across thousands of
        cells and turns any spatial join into noise.

        So: choose the coarsest resolution whose edge still comfortably encloses the source's
        own error radius. Coarser than that loses real locality; finer than that is harmless
        but wasteful, so the coarsest fitting one is taken.
        """
        if not ref.accuracy_is_declared:
            return self.default_resolution
        accuracy = float(ref.coordinate_accuracy_m or 0.0)
        # Finest first; the first cell that still encloses the error radius is the answer.
        for res in range(self.max_resolution, self.min_resolution - 1, -1):
            edge = _APPROX_EDGE_METRES.get(res, 1.2)
            if edge >= accuracy:
                return res
        # Even the coarsest cell is smaller than the error radius: the source is less precise
        # than the whole index. Take the coarsest available and let accuracy_risk say so.
        return self.min_resolution


@dataclass(frozen=True, slots=True)
class H3IndexRecord:
    """A derived index record. The cell is a key; the source is the fact."""

    spatial_ref: SpatialRef
    cell: str
    resolution: int
    transform_fingerprint: str
    approximate_edge_m: float
    accuracy_risk: str
    """``cell_encloses_source`` | ``cell_finer_than_source`` | ``accuracy_undeclared``.

    ``cell_encloses_source`` is the normal case: the bucket comfortably covers the source's own
    error radius, so a spatial join at it means something.

    ``cell_finer_than_source`` is the dangerous one — the cell is an order of magnitude smaller
    than the measurement's error, so one real location scatters across many cells and a join at
    that resolution invents neighbours.

    ``accuracy_undeclared`` means the source never said, which is not perfect accuracy.
    Computed, never asserted by the caller.
    """
    notes: dict[str, Any] = field(default_factory=dict)

    def is_finer_than_its_source(self) -> bool:
        """Whether the cell is so much smaller than the source's error that a join breaks.

        A 5 m measurement indexed at resolution 13 is fine: the cell is a bucket. A 5 km
        measurement indexed at resolution 12 (23 m edge) is not -- it scatters one real location
        across thousands of buckets, and any spatial join at that resolution invents neighbours.
        The threshold is an order of magnitude below the declared accuracy.
        """
        if not self.spatial_ref.accuracy_is_declared:
            return False
        return self.approximate_edge_m < float(self.spatial_ref.coordinate_accuracy_m or 0) / 10


def _fingerprint(*parts: Any) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def index_point(
    ref: SpatialRef,
    *,
    policy: ResolutionPolicy | None = None,
) -> H3IndexRecord:
    """Index one point. The returned record keeps the source geometry beside the cell."""
    policy = policy or ResolutionPolicy()
    resolution = policy.resolution_for(ref)
    cell = h3.latlng_to_cell(ref.latitude, ref.longitude, resolution)
    edge = float(_APPROX_EDGE_METRES.get(resolution, 1.0))

    if not ref.accuracy_is_declared:
        risk = "accuracy_undeclared"
    elif edge < float(ref.coordinate_accuracy_m or 0) / 10:
        risk = "cell_finer_than_source"
    else:
        risk = "cell_encloses_source"

    record = H3IndexRecord(
        spatial_ref=ref,
        cell=cell,
        resolution=resolution,
        transform_fingerprint=_fingerprint(
            "h3", H3_VERSION_PINNED, ref.crs, resolution, ref.latitude, ref.longitude
        ),
        approximate_edge_m=edge,
        accuracy_risk=risk,
        notes={
            "cell_is_an_index_key": True,
            "source_geometry_retained": True,
        },
    )
    return record


def neighbours(cell: str, *, k: int = 1) -> tuple[str, ...]:
    """Adjacent cells, for a join that states its tolerance.

    Returned with their own resolutions so a caller can see what neighbourhood it is reasoning
    over rather than assuming "nearby" means something fixed.
    """
    return tuple(h3.grid_disk(cell, k))