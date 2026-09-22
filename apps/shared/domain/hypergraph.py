"""Temporal typed hypergraph (feature 009, pure stdlib).

N-ary relations are FIRST-CLASS: an occurrence (transaction, meeting,
publication) is not an entity node but a hyperedge over participant
entities. Pairwise projection is *derived and lossy* (it forgets
co-participation) — so the native form stays primary; clique projections
are explicit, deterministic, and derived-only artifacts for consumers that
cannot read the native form.

Design contract (matches the platform philosophy):
- hyperedge = members + type + temporal validity + provenance (I-12) + tenant
- idempotent upserts by deterministic identity (I-11)
- dynamic-continuant entities own life-streams (domain.dynamics);
  artifact-continuants (document-evidence) anchor hyperedges but carry no
  own dynamics; occurrences ARE hyperedges (never entity nodes)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from domain.dynamics import StreamAppendRejected


def hyperedge_id(
    edge_type: str,
    members: tuple[str, ...],
    *,
    tenant_id: str = "default-tenant",
) -> str:
    """Stable LOGICAL identity of an N-ary relation across all its versions.

    The single dedup key shared by the domain and the graph projection (block
    G): (edge_type, members, tenant). Temporal versions of the *same*
    relation all share this id — that is what consumers dedup against.
    """
    material = json.dumps(
        {
            "edge_type": edge_type,
            "members": sorted(members),
            "tenant_id": tenant_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "HE-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def hyperedge_version_id(
    edge_type: str,
    members: tuple[str, ...],
    *,
    tenant_id: str = "default-tenant",
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    weight: float = 1.0,
    anchor_artifact_id: str = "",
    observation_id: str = "",
    provenance: dict[str, Any] | None = None,
) -> str:
    """Content-addressed id of ONE temporal version (block H).

    Includes valid_until / weight / provenance so distinct content is a
    distinct version; identical content is byte-identical (idempotent dedup,
    I-11). Enables append-only temporal versioning instead of "immutable"
    rejection.
    """
    logical = hyperedge_id(edge_type, members, tenant_id=tenant_id)
    material = json.dumps(
        {
            "logical_id": logical,
            "valid_from": valid_from.isoformat() if valid_from else None,
            "valid_until": valid_until.isoformat() if valid_until else None,
            "weight": weight,
            "anchor_artifact_id": anchor_artifact_id,
            "observation_id": observation_id,
            "provenance": json.dumps(provenance or {}, sort_keys=True, default=str),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "HE-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class HyperEdge:
    """An N-ary, temporal, typed relation over entity members.

    Two identities coexist:
    - ``logical_id``: the stable N-ary relation (type + members + tenant) —
      shared with the graph projection (block G).
    - ``edge_id``: the content-addressed id of THIS temporal version (block
      H) — distinct content (weight/valid window/anchor/provenance) is a
      distinct version of the same logical edge.
    """

    edge_type: str
    members: tuple[str, ...]
    edge_id: str = ""
    logical_id: str = ""
    weight: float = 1.0
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    tenant_id: str = "default-tenant"
    provenance: dict[str, Any] = field(default_factory=dict)
    anchor_artifact_id: str = ""  # e.g. the document-evidence that grounds it
    observation_id: str = ""

    def __post_init__(self) -> None:
        if not self.edge_type:
            raise StreamAppendRejected("hyperedge requires edge_type")
        if len(self.members) < 2:
            raise StreamAppendRejected(
                f"hyperedge requires >= 2 members, got {len(self.members)}"
            )
        if len(set(self.members)) != len(self.members):
            raise StreamAppendRejected("hyperedge members must be distinct")
        if not self.tenant_id:
            raise StreamAppendRejected("hyperedge requires tenant_id (I-12)")
        if (
            self.valid_until is not None
            and self.valid_from is not None
            and self.valid_until < self.valid_from
        ):
            raise StreamAppendRejected("valid_until < valid_from")
        members = tuple(sorted(set(self.members)))
        object.__setattr__(self, "members", members)
        object.__setattr__(
            self,
            "logical_id",
            self.logical_id
            or hyperedge_id(self.edge_type, members, tenant_id=self.tenant_id),
        )
        object.__setattr__(
            self,
            "edge_id",
            self.edge_id
            or hyperedge_version_id(
                self.edge_type,
                members,
                tenant_id=self.tenant_id,
                valid_from=self.valid_from,
                valid_until=self.valid_until,
                weight=self.weight,
                anchor_artifact_id=self.anchor_artifact_id,
                observation_id=self.observation_id,
                provenance=self.provenance,
            ),
        )

    @property
    def content_hash(self) -> str:
        material = json.dumps(
            {
                "edge_id": self.edge_id,
                "edge_type": self.edge_type,
                "members": list(self.members),
                "weight": self.weight,
                "valid_from": self.valid_from.isoformat() if self.valid_from else None,
                "valid_until": self.valid_until.isoformat() if self.valid_until else None,
                "anchor_artifact_id": self.anchor_artifact_id,
                "observation_id": self.observation_id,
                "provenance": json.dumps(self.provenance, sort_keys=True, default=str),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def is_active_at(self, ts: datetime) -> bool:
        start_ok = self.valid_from is None or self.valid_from <= ts
        end_ok = self.valid_until is None or ts < self.valid_until
        return start_ok and end_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "logical_id": self.logical_id,
            "edge_type": self.edge_type,
            "members": list(self.members),
            "weight": self.weight,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "tenant_id": self.tenant_id,
            "provenance": self.provenance,
            "anchor_artifact_id": self.anchor_artifact_id,
            "observation_id": self.observation_id,
            "content_hash": self.content_hash,
        }


@dataclass
class HyperGraph:
    """Idempotent, tenant-scoped hypergraph store (pure, in-memory).

    Store contract mirrors ``GraphStore``: provenance enforced on every
    write (I-12), idempotent on deterministic identity (I-11), rebuildable
    from the ordered event stream by replaying upserts.

    Temporal versioning (block H): identical content is a byte-identical
    ``edge_id`` and bumps to idempotent no-op; content that differs on any
    versionable field (weight, valid_until, anchor, provenance) is a NEW
    temporal version of the same ``logical_id`` — stored alongside, never
    rejected as "immutable".
    """

    provenance_required: bool = True

    def __post_init__(self) -> None:
        self._edges: dict[str, HyperEdge] = {}
        self._versions: dict[str, dict[str, HyperEdge]] = {}  # logical_id -> {edge_id: edge}
        self._version_order: dict[str, list[str]] = {}  # logical_id -> [edge_id] (insertion)

    def upsert(self, edge: HyperEdge, provenance: dict | None = None) -> str:
        if self.provenance_required:
            prov = provenance or edge.provenance
            if not prov or not prov.get("event_id"):
                raise StreamAppendRejected(
                    "hyperedge upsert requires event_id/observation_id provenance (I-12)"
                )
            if not edge.provenance:
                # provenance is part of the version identity — recompute the
                # content-addressed version id once it is attached.
                object.__setattr__(edge, "provenance", dict(prov))
                object.__setattr__(
                    edge,
                    "edge_id",
                    hyperedge_version_id(
                        edge.edge_type,
                        edge.members,
                        tenant_id=edge.tenant_id,
                        valid_from=edge.valid_from,
                        valid_until=edge.valid_until,
                        weight=edge.weight,
                        anchor_artifact_id=edge.anchor_artifact_id,
                        observation_id=edge.observation_id,
                        provenance=edge.provenance,
                    ),
                )
        if edge.edge_id in self._edges:
            return edge.edge_id  # identical content already stored (I-11)
        self._edges[edge.edge_id] = edge
        self._versions.setdefault(edge.logical_id, {})[edge.edge_id] = edge
        self._version_order.setdefault(edge.logical_id, []).append(edge.edge_id)
        return edge.edge_id

    def get(self, edge_id: str) -> HyperEdge | None:
        return self._edges.get(edge_id)

    def versions(self, logical_id: str) -> list[HyperEdge]:
        """Every temporal version of one logical relation, insertion order."""
        ids = self._version_order.get(logical_id, [])
        return [self._edges[eid] for eid in ids if eid in self._edges]

    def edges(
        self,
        *,
        edge_type: str | None = None,
        member: str | None = None,
        tenant_id: str | None = None,
        active_at: datetime | None = None,
    ) -> list[HyperEdge]:
        out: list[HyperEdge] = []
        for e in self._edges.values():
            if edge_type and e.edge_type != edge_type:
                continue
            if member and member not in e.members:
                continue
            if tenant_id and e.tenant_id != tenant_id:
                continue
            if active_at is not None and not e.is_active_at(active_at):
                continue
            out.append(e)
        return sorted(out, key=lambda e: (e.edge_type, e.members))

    def __len__(self) -> int:
        return len(self._edges)

    # -- derived (lossy, pairwise) views ------------------------------------

    def clique_projection(
        self,
        *,
        edge_type: str | None = None,
        tenant_id: str | None = None,
        active_at: datetime | None = None,
    ) -> list[tuple[str, str, str]]:
        """Deterministic pairwise projection (derived, lossy — explicit).

        Every hyperedge becomes a clique over its members. For TDA/network
        consumers that need a plain graph; N-ary structure is forgotten by
        design, so native hyperedges remain the authoritative form.
        """
        triples: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for e in self.edges(edge_type=edge_type, tenant_id=tenant_id, active_at=active_at):
            members = sorted(e.members)
            for i, left in enumerate(members):
                for right in members[i + 1 :]:
                    key = (left, right, e.edge_type)
                    if key not in seen:
                        seen.add(key)
                        triples.append(key)
        return sorted(triples)

    def incidence_complex(self) -> dict[str, Any]:
        """Simplicial-complex-style view for TDA (bounded, deterministic).

        Returns hyperedges as maximal simplices: {simplex_id, nodes, dim}.
        The TDA plane builds clique/Dowker complexes from this without
        importing vendor code (Constitution V) and without losing N-ary
        co-participation (each hyperedge = one maximal simplex).
        """
        return {
            "maximal_simplices": [
                {
                    "simplex_id": e.edge_id,
                    "nodes": list(e.members),
                    "dim": len(e.members) - 1,
                    "edge_type": e.edge_type,
                    "weight": e.weight,
                }
                for e in self.edges()
            ]
        }

    def to_dict(self) -> dict[str, Any]:
        return {"edges": [e.to_dict() for e in self.edges()]}