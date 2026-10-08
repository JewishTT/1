"""Context cells, the scope algebra, and recorded loss under restriction.

Spec 025 §7 calls a ``ContextCell`` *a local section of information*; §7.2 defines
the scope algebra; §8.1 defines ``RestrictionMap`` with a ``loss_profile``; §10.3
defines the obstruction taxonomy; §8.3 forbids comparing all cells with all cells.
None of it existed in code. This module is that substrate.

Three decisions are load-bearing and each one exists because of a specific failure
the flat design would produce.

**Scopes are objects, and intersection is a lattice, not string equality.**
§7.2: "No scope intersection may be inferred from string equality alone." Nine
scope kinds intersect into exactly one of ``EMPTY | PARTIAL | EXACT | UNKNOWN``.
``UNKNOWN`` is what makes this honest rather than merely tidy: a semantic mapping
that was never attempted is not the same as one that failed, and collapsing them is
how an unknown relation type gets discarded -- the thing §0.2 forbids
("unknown relation type != discard relation signal").

**Restriction records what it cost.** A restriction may narrow scope freely
because §8.1 makes it monotonic with respect to observability *and* forces the
``loss_profile`` to say what was dropped. Narrowing without recording the loss is
indistinguishable from narrowing because there was nothing to lose.

**Cells have a parent.** ``ContextCell`` in §7.1 has no ``parent_cell`` and cells
are therefore flat within a revision. Relational depth (who owns whom) is graph
traversal and works regardless. Scope depth -- a sub-question whose context is a
child of a parent context, queryable as "everything under X" -- has nowhere to
live, so a long investigation degrades into a bag of cells that can only be
scanned. ``parent_cell`` is that missing edge. It is a DAG and not a tree on
purpose: joint control, syndication and cross-citation are real, and a tree would
assert an exclusivity the world does not have.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from hashlib import sha256
from typing import Any

# -- §7.2 scope algebra ------------------------------------------------------


class CellKind(enum.StrEnum):
    """The cell kinds enumerated in §7.1."""

    SOURCE = "source"
    DOCUMENT = "document"
    EVENT_WINDOW = "event_window"
    ENTITY_EGO = "entity_ego"
    GEO = "geo"
    ORGANIZATION = "organization"
    MARKET = "market"
    CUSTOM = "custom"


class ScopeKind(enum.StrEnum):
    """The nine scope objects of §7.2."""

    ENTITY = "entity"
    EVENT = "event"
    SOURCE = "source"
    TEMPORAL = "temporal"
    GEOSPATIAL = "geospatial"
    ORGANIZATIONAL = "organizational"
    SEMANTIC = "semantic"
    NETWORK = "network"
    CUSTOM = "custom"


class ScopeIntersection(enum.StrEnum):
    """§7.2: intersection returns exactly one of these four."""

    EMPTY = "empty"
    PARTIAL = "partial"
    EXACT = "exact"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Scope:
    """One explicit scope object. Absence of a member is not the same as ``EMPTY``.

    ``members`` is the set of things in scope. ``unknown`` records that no
    determination was made -- distinct from a determination of none, which is what
    lets §0.2's "unknown relation type != discard relation signal" hold at the
    scope level.
    """

    kind: ScopeKind
    members: frozenset[str] = frozenset()
    #: True when no determination was made, as opposed to a determination of none.
    unknown: bool = False
    #: Free-form qualifier, e.g. a registry name or a projection version.
    qualifier: str = ""

    @classmethod
    def entity(cls, *refs: str) -> Scope:
        return cls(ScopeKind.ENTITY, frozenset(refs))

    @classmethod
    def temporal(cls, start: str = "", end: str = "") -> Scope:
        members = frozenset({start, end} - {""})
        return cls(ScopeKind.TEMPORAL, members, qualifier=f"{start}/{end}")

    @classmethod
    def semantic_unknown(cls) -> Scope:
        return cls(ScopeKind.SEMANTIC, frozenset(), unknown=True)

    def is_empty(self) -> bool:
        """Empty only when a determination was made and found nothing."""
        return not self.unknown and not self.members


def intersect_scopes(left: Scope, right: Scope) -> ScopeIntersection:
    """§7.2 intersection. Never a string comparison.

    The rules, in the order they matter:

    1. An undetermined member forces ``UNKNOWN``. This is the rule that preserves
       observability: an unmapped relation leaves the scope undetermined rather
       than empty.
    2. Disjoint determined members give ``EMPTY``.
    3. Different kinds never reach ``EXACT`` -- two scopes of different kinds are
       not the same scope, they are merely not disjoint.
    4. Containment in either direction gives ``EXACT``.
    5. Otherwise overlap without containment gives ``PARTIAL``.
    """
    if left.unknown or right.unknown:
        return ScopeIntersection.UNKNOWN
    if not left.members or not right.members:
        return ScopeIntersection.EMPTY
    shared = left.members & right.members
    if not shared:
        return ScopeIntersection.EMPTY
    if left.kind != right.kind:
        return ScopeIntersection.PARTIAL
    if shared == left.members or shared == right.members:
        return ScopeIntersection.EXACT
    return ScopeIntersection.PARTIAL


def scopes_disjoint(left: Scope, right: Scope) -> bool:
    """§8.3 blocking key: only non-``EMPTY`` intersections may be compared."""
    return intersect_scopes(left, right) is ScopeIntersection.EMPTY


def _digest(material: Mapping[str, Any]) -> str:
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()[:12]


# -- §7.1 the cell ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContextCell:
    """A local section of information (§7.1), with the ancestry §7.1 omits.

    Every field the spec requires for inspectability is present: scope, temporal
    slice, the observation/entity/relation/state refs it was built from, the
    semantic regime, completeness, trust state, and the operator plus method
    fingerprint that produced it.

    ``parent_cell`` is the addition. Empty means this cell is a root of its
    context. It is deliberately not required to form a tree: cycles are rejected,
    and multiple children of one parent express the DAG shape that joint control
    and syndication actually require.
    """

    context_id: str
    kind: CellKind
    scope: Scope
    cell_id: str = ""
    parent_cell: str = ""
    temporal_slice: tuple[str, str] = ()
    observation_refs: tuple[str, ...] = ()
    entity_refs: tuple[str, ...] = ()
    relation_refs: tuple[str, ...] = ()
    state_refs: tuple[str, ...] = ()
    semantic_regime_ref: str = ""
    completeness: Mapping[str, Any] = field(default_factory=dict)
    trust_state: str = "unknown"
    produced_by: str = ""
    method_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.context_id:
            raise ValueError("a cell must name its context")
        if self.trust_state not in ("verified", "unverified", "contested", "unknown"):
            raise ValueError(f"unknown trust_state {self.trust_state!r}")
        if self.cell_id and self.cell_id != self.address():
            raise ValueError(
                f"declared cell_id {self.cell_id!r} but material addresses to {self.address()}"
            )
        if not self.cell_id:
            object.__setattr__(self, "cell_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "kind": self.kind.value,
            "scope_kind": self.scope.kind.value,
            "scope_members": sorted(self.scope.members),
            "scope_unknown": self.scope.unknown,
            "parent_cell": self.parent_cell,
            "temporal_slice": list(self.temporal_slice),
            "semantic_regime_ref": self.semantic_regime_ref,
        }

    def address(self) -> str:
        return f"CXC-{_digest(self._material())}"

    @property
    def is_root(self) -> bool:
        return not self.parent_cell

    def with_observations(self, refs: Iterable[str]) -> ContextCell:
        merged = tuple(sorted(set(self.observation_refs) | {str(ref) for ref in refs}))
        return replace(self, observation_refs=merged)

    def ancestry(self, cells: Mapping[str, ContextCell]) -> tuple[str, ...]:
        """Cell ids from the root down to this cell.

        Terminates on a cycle rather than looping forever: a corrupt store should
        produce a short answer plus an error, not a hung investigation.
        """
        chain: list[str] = [self.cell_id]
        seen = {self.cell_id}
        current = self
        while current.parent_cell:
            if current.parent_cell in seen:
                raise ValueError(f"cycle in cell ancestry at {current.parent_cell}")
            parent = cells.get(current.parent_cell)
            if parent is None:
                raise KeyError(f"parent cell {current.parent_cell} is not present")
            chain.append(parent.cell_id)
            seen.add(parent.cell_id)
            current = parent
        return tuple(reversed(chain))

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "context_id": self.context_id,
            "kind": self.kind.value,
            "parent_cell": self.parent_cell,
            "scope": {
                "kind": self.scope.kind.value,
                "members": sorted(self.scope.members),
                "unknown": self.scope.unknown,
                "qualifier": self.scope.qualifier,
            },
            "temporal_slice": list(self.temporal_slice),
            "observation_refs": list(self.observation_refs),
            "entity_refs": list(self.entity_refs),
            "relation_refs": list(self.relation_refs),
            "state_refs": list(self.state_refs),
            "semantic_regime_ref": self.semantic_regime_ref,
            "completeness": dict(self.completeness),
            "trust_state": self.trust_state,
            "produced_by": self.produced_by,
            "method_fingerprint": self.method_fingerprint,
        }


# -- §8.1 restriction and its cost -------------------------------------------


class PrecisionLoss(enum.StrEnum):
    NONE = "none"
    COARSENED = "coarsened"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LossProfile:
    """§8.1: what a restriction actually gave up.

    Exists so narrowing scope is a *recorded* decision. A restriction without this
    is indistinguishable from one that had nothing to lose, which is exactly the
    ambiguity that makes an under-covered answer look complete.
    """

    entities_removed: int = 0
    relations_removed: int = 0
    temporal_precision_loss: PrecisionLoss = PrecisionLoss.NONE
    semantic_precision_loss: PrecisionLoss = PrecisionLoss.NONE

    @property
    def is_lossless(self) -> bool:
        return (
            self.entities_removed == 0
            and self.relations_removed == 0
            and self.temporal_precision_loss is PrecisionLoss.NONE
            and self.semantic_precision_loss is PrecisionLoss.NONE
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "entities_removed": self.entities_removed,
            "relations_removed": self.relations_removed,
            "temporal_precision_loss": self.temporal_precision_loss.value,
            "semantic_precision_loss": self.semantic_precision_loss.value,
        }


@dataclass(frozen=True, slots=True)
class RestrictionMap:
    """§8.1: a projection from one cell into a narrower scope, with its loss."""

    from_cell: str
    to_scope: Scope
    loss_profile: LossProfile
    projected_observations: tuple[str, ...] = ()
    projected_entities: tuple[str, ...] = ()
    projected_relations: tuple[str, ...] = ()
    projected_states: tuple[str, ...] = ()
    restriction_id: str = ""
    method_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.from_cell:
            raise ValueError("a restriction must name its source cell")
        if self.restriction_id and self.restriction_id != self.address():
            raise ValueError(
                f"declared restriction_id {self.restriction_id!r} but material "
                f"addresses to {self.address()}"
            )
        if not self.restriction_id:
            object.__setattr__(self, "restriction_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "from_cell": self.from_cell,
            "to_scope_kind": self.to_scope.kind.value,
            "to_scope_members": sorted(self.to_scope.members),
            "loss": self.loss_profile.as_dict(),
        }

    def address(self) -> str:
        return f"RST-{_digest(self._material())}"

    def is_monotonic(self, source: ContextCell) -> bool:
        """§8.1: a restriction may reduce scope and precision, never widen it.

        Returning ``False`` is how a bug that silently reintroduces out-of-scope
        entities gets caught.
        """
        return not scopes_disjoint(source.scope, self.to_scope)

    def as_dict(self) -> dict[str, Any]:
        return {
            "restriction_id": self.restriction_id,
            "from_cell": self.from_cell,
            "to_scope": {
                "kind": self.to_scope.kind.value,
                "members": sorted(self.to_scope.members),
                "unknown": self.to_scope.unknown,
            },
            "loss_profile": self.loss_profile.as_dict(),
            "projected_observations": list(self.projected_observations),
            "projected_entities": list(self.projected_entities),
            "projected_relations": list(self.projected_relations),
            "projected_states": list(self.projected_states),
            "method_fingerprint": self.method_fingerprint,
        }


def measure_loss(
    source: ContextCell,
    *,
    kept_observations: Sequence[str],
    kept_entities: Sequence[str],
    kept_relations: Sequence[str],
    temporal_precision_loss: PrecisionLoss = PrecisionLoss.NONE,
    semantic_precision_loss: PrecisionLoss = PrecisionLoss.NONE,
) -> LossProfile:
    """Derive the loss a projection actually incurred, rather than asserting it."""
    return LossProfile(
        entities_removed=max(0, len(source.entity_refs) - len(kept_entities)),
        relations_removed=max(0, len(source.relation_refs) - len(kept_relations)),
        temporal_precision_loss=temporal_precision_loss,
        semantic_precision_loss=semantic_precision_loss,
    )


# -- §10.3 obstructions -------------------------------------------------------


class ObstructionKind(enum.StrEnum):
    """§10.3, transcribed one for one. ``OBST-`` prefixes the identifier; ``OBS-``
    stays reserved for Observation.

    Member names match the spec identifiers exactly, including the inconsistent
    suffixes it uses -- the first seven end in ``_OBSTRUCTION`` and the last five
    do not. Normalising them would have made a lookup against §10.3 ambiguous
    about which spelling is authoritative.
    """

    TEMPORAL_OBSTRUCTION = "temporal_obstruction"
    SEMANTIC_OBSTRUCTION = "semantic_obstruction"
    IDENTITY_OBSTRUCTION = "identity_obstruction"
    STRUCTURAL_OBSTRUCTION = "structural_obstruction"
    NUMERIC_OBSTRUCTION = "numeric_obstruction"
    PROVENANCE_OBSTRUCTION = "provenance_obstruction"
    SCOPE_OBSTRUCTION = "scope_obstruction"
    MISSING_COVERAGE = "missing_coverage"
    SOURCE_CONFLICT = "source_conflict"
    MODEL_CONFLICT = "model_conflict"
    TRIPLE_INCONSISTENCY = "triple_inconsistency"
    BUCKET_OVERFLOW = "bucket_overflow"


@dataclass(frozen=True, slots=True)
class Obstruction:
    """A recorded reason two cells were not glued, or work was not attempted.

    §8.3 requires overflow and truncation to be recorded rather than applied
    silently; ADR-0031 adds ``BLOCKED != FALSE``. An obstruction is therefore a
    first-class result, never an error to be swallowed.
    """

    kind: ObstructionKind
    detail: str
    obstruction_id: str = ""
    subject_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.detail:
            raise ValueError("an obstruction must say what it is")
        if self.obstruction_id and self.obstruction_id != self.address():
            raise ValueError(
                f"declared obstruction_id {self.obstruction_id!r} but material "
                f"addresses to {self.address()}"
            )
        if not self.obstruction_id:
            object.__setattr__(self, "obstruction_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "detail": self.detail,
            "subject_refs": sorted(self.subject_refs),
        }

    def address(self) -> str:
        return f"OBST-{_digest(self._material())}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "obstruction_id": self.obstruction_id,
            "kind": self.kind.value,
            "detail": self.detail,
            "subject_refs": list(self.subject_refs),
        }


# -- locality queries over the cell DAG --------------------------------------


def children_of(cell_id: str, cells: Sequence[ContextCell]) -> tuple[ContextCell, ...]:
    """Direct children, key-ordered for determinism."""
    return tuple(sorted(
        (cell for cell in cells if cell.parent_cell == cell_id),
        key=lambda cell: cell.cell_id,
    ))


def descendants_of(cell_id: str, cells: Sequence[ContextCell]) -> tuple[ContextCell, ...]:
    """Everything under ``cell_id``, breadth-first, cycle-safe.

    This is the query flat cells cannot answer at all, and the one a long
    investigation depends on: "what did every sub-question of X conclude?".
    """
    index = {cell.cell_id: cell for cell in cells}
    if cell_id not in index:
        raise KeyError(cell_id)
    found: list[ContextCell] = []
    seen = {cell_id}
    frontier = [cell_id]
    while frontier:
        current = frontier.pop(0)
        for child in children_of(current, cells):
            if child.cell_id in seen:
                continue
            seen.add(child.cell_id)
            found.append(child)
            frontier.append(child.cell_id)
    return tuple(found)


def roots_of(cells: Sequence[ContextCell]) -> tuple[ContextCell, ...]:
    return tuple(sorted((cell for cell in cells if cell.is_root), key=lambda cell: cell.cell_id))


def cells_within(scope: Scope, cells: Sequence[ContextCell]) -> tuple[ContextCell, ...]:
    """Every cell whose scope is not disjoint from ``scope``.

    §7.2's lattice decides membership, and an ``UNKNOWN`` intersection counts as
    within: a cell whose compatibility was never determined must stay reachable.
    Dropping it would make undetermined cells invisible, which is the §0.2
    violation in query form.
    """
    return tuple(sorted(
        (
            cell
            for cell in cells
            if not scopes_disjoint(cell.scope, scope)
        ),
        key=lambda cell: cell.cell_id,
    ))
