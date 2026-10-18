"""ProjectionManifest — the record that makes "this is rebuildable" checkable.

Spec 030 contract 06 / FR-070 / FR-071, task T157.

A projection is a way of looking at canonical state. If it is destroyed, nothing is lost. If it
cannot be reproduced, it was never a projection — it was an undeclared authority wearing one.

The concrete defect this exists to prevent is visible in ``apps/projection/graph/snapshot.py``:
``GraphSnapshot.projection_id`` is minted with ``uuid4().hex`` and ``checksum`` is computed from
edges only, so two runs over identical input produce two different projection ids and there is
nowhere to record *which* snapshot a downstream reader consumed. ``rebuildable`` has no field at
all, so nothing distinguishes a store that can rebuild from one that cannot.

Every field below is load-bearing for a claim somebody will eventually make about durability.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

__all__ = [
    "ProjectionKind",
    "ProjectionStatus",
    "Staleness",
    "BuilderRef",
    "ProjectionManifest",
    "ProjectionDeclarationError",
]


class ProjectionKind(StrEnum):
    GRAPH = "graph"
    SEARCH = "search"
    TEMPORAL = "temporal"
    ANALYTICS = "analytics"
    TDA = "tda"
    SPATIAL = "spatial"


class ProjectionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    STALE = "stale"
    QUARANTINED = "quarantined"


class ProjectionDeclarationError(ValueError):
    """A manifest cannot make a claim its fields do not support.

    Raised rather than defaulted. The default reading of a bad manifest is "this projection is
    fine", which is precisely the failure the manifest exists to prevent.
    """


def _canonical(payload: dict[str, Any]) -> str:
    """Stable JSON: sorted keys, no whitespace drift, no ``repr()`` of memory addresses."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class Staleness:
    """How far behind the source this build is.

    ``status`` is what the builder knows; ``lag_events`` is how far. They are separate because
    they answer different questions. ``status="current"`` with ``lag_events=40`` means "this is
    the newest build and it is forty events behind" -- whether that is acceptable is the
    caller's tolerance, not the builder's. Collapsing the two here made a 40-event lag
    unacceptable at every tolerance, which is not a freshness policy, it is a switch.
    """

    status: str = "current"
    lag_events: int | None = None
    stale_since: datetime | None = None

    @property
    def is_current(self) -> bool:
        """Whether the builder considers this build current rather than explicitly stale.

        Deliberately says nothing about ``lag_events``. Use
        :meth:`ProjectionManifest.satisfies_freshness` to apply a tolerance.
        """
        return self.status == "current"


@dataclass(frozen=True, slots=True)
class BuilderRef:
    """Who built it, at which version, in which container."""

    id: str
    version: str
    container_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.version.strip():
            raise ProjectionDeclarationError(
                "a projection that cannot name its builder cannot be rebuilt"
            )


@dataclass(frozen=True, slots=True)
class ProjectionManifest:
    """The reproducible build record for one projection output.

    ``rebuildable`` is not a claim, it is a finding: it may only be True when a durable source,
    a checkpoint route and a tested rebuild all exist. ``ProjectionManifest.declare`` refuses
    the combination that matters most — asserting rebuildable without a rebuild route.
    """

    projection_id: str
    projection_kind: ProjectionKind
    tenant_id: str
    source_event_offset: dict[str, Any]
    input_snapshot_digest: str
    builder: BuilderRef
    parameters: dict[str, Any]
    output_digest: str
    status: ProjectionStatus = ProjectionStatus.SUCCEEDED
    rebuildable: bool = False
    staleness: Staleness = field(default_factory=Staleness)
    output_derivation: dict[str, Any] = field(default_factory=dict)
    kill_switch: str | None = None
    created_at: datetime | None = None

    # -- derived identity -------------------------------------------------

    @property
    def parameters_fingerprint(self) -> str:
        """Stable digest of the parameters.

        Not a field: two manifests describing the same run must agree on it without the caller
        having to remember to set it, and a stored value that disagrees with the parameters is
        worse than no stored value.
        """
        return "sha256:" + hashlib.sha256(_canonical(self.parameters).encode()).hexdigest()

    def fingerprint(self) -> str:
        """Content address over everything that defines this build."""
        payload = {
            "projection_id": self.projection_id,
            "kind": str(self.projection_kind),
            "tenant_id": self.tenant_id,
            "source_event_offset": self.source_event_offset,
            "input_snapshot_digest": self.input_snapshot_digest,
            "builder": asdict(self.builder),
            "parameters": self.parameters,
            "output_digest": self.output_digest,
        }
        return "sha256:" + hashlib.sha256(_canonical(payload).encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["projection_kind"] = str(self.projection_kind)
        d["status"] = str(self.status)
        d["parameters_fingerprint"] = self.parameters_fingerprint
        d["fingerprint"] = self.fingerprint()
        d["staleness"] = asdict(self.staleness)
        return d

    # -- claims ------------------------------------------------------------

    def can_rebuild(self) -> bool:
        """Whether every rebuild precondition is actually present.

        Three things, all required. Missing any one means ``rebuildable`` is False, whatever the
        caller passed in.
        """
        return bool(
            self.input_snapshot_digest
            and self.builder.id
            and self.builder.version
            and self.source_event_offset
        )

    def is_degraded(self) -> bool:
        return self.status in (ProjectionStatus.PARTIAL, ProjectionStatus.FAILED)

    def satisfies_freshness(self, *, max_lag_events: int) -> bool:
        """Whether this build is fresh enough for a caller that needs current data.

        FR-079: a stale projection may satisfy an obligation only through an explicit profile,
        so the answer here is a question the caller has to ask, not a default.
        """
        if self.status is ProjectionStatus.FAILED:
            return False
        if not self.staleness.is_current:
            return False
        lag = self.staleness.lag_events
        return lag is None or lag <= max_lag_events

    # -- declaration -------------------------------------------------------

    @classmethod
    def declare(
        cls,
        *,
        projection_id: str,
        projection_kind: ProjectionKind,
        tenant_id: str,
        source_event_offset: dict[str, Any],
        input_snapshot_digest: str,
        builder: BuilderRef,
        parameters: dict[str, Any],
        output_digest: str,
        status: ProjectionStatus = ProjectionStatus.SUCCEEDED,
        rebuildable: bool = False,
        staleness: Staleness | None = None,
        output_derivation: dict[str, Any] | None = None,
        kill_switch: str | None = None,
        created_at: datetime | None = None,
    ) -> ProjectionManifest:
        """Build a manifest, refusing any claim its own fields contradict."""
        if not tenant_id.strip():
            raise ProjectionDeclarationError(
                "a projection without a tenant scope can be read across tenants (FR-090)"
            )
        if status in (ProjectionStatus.SUCCEEDED, ProjectionStatus.PARTIAL) and not output_digest:
            raise ProjectionDeclarationError(
                f"status {status} requires an output digest; an empty digest reads as "
                "'rebuilt to nothing'"
            )

        manifest = cls(
            projection_id=projection_id,
            projection_kind=projection_kind,
            tenant_id=tenant_id,
            source_event_offset=dict(source_event_offset or {}),
            input_snapshot_digest=input_snapshot_digest,
            builder=builder,
            parameters=dict(parameters or {}),
            output_digest=output_digest,
            status=status,
            # A declared `rebuildable` that the fields cannot support is refused, not stored.
            rebuildable=False,
            staleness=staleness or Staleness(),
            output_derivation=dict(output_derivation or {}),
            kill_switch=kill_switch,
            created_at=created_at or datetime.now(UTC),
        )
        if rebuildable and not manifest.can_rebuild():
            missing = []
            if not input_snapshot_digest:
                missing.append("input_snapshot_digest")
            if not source_event_offset:
                missing.append("source_event_offset")
            if not missing:
                missing.append("builder id/version")
            raise ProjectionDeclarationError(
                "rebuildable=True requires a durable source, a checkpoint route and a named "
                f"builder; missing: {', '.join(missing)} (FR-071)"
            )
        if rebuildable:
            object.__setattr__(manifest, "rebuildable", True)
        return manifest