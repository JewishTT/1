"""Context growth: a change batch may open new scopes, not only refine old ones.

Appendix I.7 line 3094 reads ``cells = recompute_cells(invalidated.cells)`` -- a
recompute step with no creation branch. Taken literally, an observation that
reveals a scope no existing cell covers has nowhere to go. §0.2 forbids the three
available workarounds in the same breath:

    unresolved identity  != discard mention
    unknown relation type != discard relation signal
    no evidence observed  != evidence = negative

Dropping it is forbidden. Forcing it into a neighbouring cell manufactures false
precision about what that cell contains. Creating an *unlinked* cell is the
subtler failure: it is neither dropped nor wrong, but it can never be retrieved as
part of anything, so after several iterations the context is a bag of cells and the
investigation has lost its depth.

So this module supplies the branch the pseudocode omits:
``extend_or_recompute_cells``. A new cell is created *anchored* -- ``parent_cell``
is the cell whose material revealed it -- which is what makes "everything under X"
answerable later and what makes §7.1's inspectability question ("what scope produced
this cell?") answerable at all.

Anchoring also has to choose when nothing reveals a new scope. §7.1 requires a
non-root cell to have a parent, so an unanchored observation is refused with a
recorded reason rather than being attached to an arbitrary root. That is the
``NO_ANCHOR`` outcome, and refusing is right: an unattributable scope is a finding
about the evidence, not something to paper over with a plausible-looking parent.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from context.locality import (
    CellKind,
    ContextCell,
    Obstruction,
    ObstructionKind,
    Scope,
    ScopeIntersection,
    intersect_scopes,
)

# -- §35.1 change set ----------------------------------------------------------


class InvalidationClass(enum.StrEnum):
    """§35.3, transcribed."""

    LOCAL_RECOMPUTE = "local_recompute"
    WINDOW_RECOMPUTE = "window_recompute"
    CELL_RECOMPUTE = "cell_recompute"
    HYPOTHESIS_REEVALUATION = "hypothesis_reevaluation"
    FULL_CONTEXT_REBUILD = "full_context_rebuild"


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """§35.1.

    ``removed_refs`` removes from *derived input views* only. §35.1 states that
    plainly -- "Raw observations are never removed from the world" -- so the field
    exists and is named ``removed_refs`` rather than ``deleted_observations`` to
    keep that boundary visible at the call site.
    """

    batch_ref: str
    event_refs: tuple[str, ...] = ()
    added_observations: tuple[str, ...] = ()
    removed_refs: tuple[str, ...] = ()
    changed_entities: tuple[str, ...] = ()
    changed_relations: tuple[str, ...] = ()
    changed_temporal_windows: tuple[str, ...] = ()
    changed_semantics: tuple[str, ...] = ()
    changed_policies: tuple[str, ...] = ()
    analyst_decisions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.batch_ref:
            raise ValueError("a change set must name its batch")

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.event_refs,
                self.added_observations,
                self.removed_refs,
                self.changed_entities,
                self.changed_relations,
                self.changed_temporal_windows,
                self.changed_semantics,
                self.changed_policies,
                self.analyst_decisions,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_ref": self.batch_ref,
            "event_refs": list(self.event_refs),
            "added_observations": list(self.added_observations),
            "removed_refs": list(self.removed_refs),
            "changed_entities": list(self.changed_entities),
            "changed_relations": list(self.changed_relations),
            "changed_temporal_windows": list(self.changed_temporal_windows),
            "changed_semantics": list(self.changed_semantics),
            "changed_policies": list(self.changed_policies),
            "analyst_decisions": list(self.analyst_decisions),
        }


# -- §I.7 the omitted branch ---------------------------------------------------


class PlacementOutcome(enum.StrEnum):
    """Where a new observation went, and why."""

    #: Fits an existing cell; nothing new is created.
    ABSORBED = "absorbed"
    #: Opened a new scope; a new cell was created under an anchor.
    EXTENDED = "extended"
    #: Fits nothing and nothing reveals why. Refused, and recorded.
    NO_ANCHOR = "no_anchor"
    #: The declared scope is undetermined, so no placement can be justified.
    SCOPE_UNDETERMINED = "scope_undetermined"


@dataclass(frozen=True, slots=True)
class Placement:
    """The result of placing one observation's scope."""

    observation_id: str
    outcome: PlacementOutcome
    cell_id: str = ""
    parent_cell: str = ""
    scope: Scope | None = None
    reason: str = ""
    obstruction: Obstruction | None = None

    @property
    def is_placed(self) -> bool:
        """Absorbed or extended. A refused placement is never a placed one."""
        return self.outcome in (PlacementOutcome.ABSORBED, PlacementOutcome.EXTENDED)

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "outcome": self.outcome.value,
            "cell_id": self.cell_id,
            "parent_cell": self.parent_cell,
            "reason": self.reason,
        }


def place_observation(
    observation_id: str,
    scope: Scope,
    cells: Sequence[ContextCell],
    *,
    kind: CellKind = CellKind.DOCUMENT,
    revealed_by: str = "",
    temporal_slice: tuple[str, str] = (),
    semantic_regime_ref: str = "",
    produced_by: str = "",
    method_fingerprint: str = "",
) -> Placement:
    """Place one observation's scope against the current cells.

    The order of decisions is the substance:

    1. **Undetermined scope places nowhere.** §7.2's ``UNKNOWN`` means no
       determination was made, so there is nothing to place against. Forcing it
       somewhere is exactly the §0.2 violation. It is refused and recorded.
    2. **A cell that covers the scope absorbs it.** Only when the observation names
       nothing new -- otherwise a widening observation would be folded into a parent
       and the context would never deepen.
    3. **An overlapping but widening scope extends**, anchored to the overlapping
       cell.
    4. **A disjoint scope extends**, anchored to the cell named by ``revealed_by``.
       If that cell is absent the placement is refused with ``NO_ANCHOR``: there is
       no defensible parent to attach to, and an unattributable scope is a finding
       rather than something to paper over with a plausible-looking parent.
    """
    if scope.unknown:
        return Placement(
            observation_id=observation_id,
            outcome=PlacementOutcome.SCOPE_UNDETERMINED,
            scope=scope,
            reason=(
                "no determination was made for this observation's scope; "
                "placing it would assert a membership nobody established"
            ),
            obstruction=Obstruction(
                kind=ObstructionKind.SCOPE_OBSTRUCTION,
                detail=f"undetermined scope for {observation_id}",
                subject_refs=(observation_id,),
            ),
        )

    by_id = {cell.cell_id: cell for cell in cells}

    # An identical scope is the *same* cell, so this check comes before anything
    # ordered. Without it, two observations naming the same new scope each create
    # an equal cell, and because ordering by cell id may reach the anchor first, the
    # duplicate is never consulted -- the context fills with twins and the second
    # observation is recorded as widening something it does not widen.
    for cell in sorted(cells, key=lambda item: item.cell_id):
        if cell.scope.kind is scope.kind and cell.scope.members == scope.members:
            return Placement(
                observation_id=observation_id,
                outcome=PlacementOutcome.ABSORBED,
                cell_id=cell.cell_id,
                scope=scope,
                reason=f"scope is identical to existing cell {cell.cell_id}",
            )

    # Deterministic order: the first match by cell id, so placement is repeatable.
    for cell in sorted(cells, key=lambda item: item.cell_id):
        intersection = intersect_scopes(cell.scope, scope)
        if intersection is ScopeIntersection.EMPTY:
            continue
        if scope.members.issubset(cell.scope.members):
            # The cell already covers everything this observation names. Absorbing
            # adds the observation without asserting a new membership.
            return Placement(
                observation_id=observation_id,
                outcome=PlacementOutcome.ABSORBED,
                cell_id=cell.cell_id,
                scope=scope,
                reason=(
                    f"scope is covered by {cell.cell_id}; nothing new is introduced"
                ),
            )
        # Overlapping but *widening*: the observation names referents this cell does
        # not have. Absorbing here would silently fold them into the parent, and the
        # context would never deepen. The overlapping cell becomes the anchor.
        return Placement(
            observation_id=observation_id,
            outcome=PlacementOutcome.EXTENDED,
            parent_cell=cell.cell_id,
            scope=scope,
            reason=(
                f"scope widens {cell.cell_id}, which covers only "
                f"{sorted(cell.scope.members)}; anchored there"
            ),
        )

    anchor = by_id.get(revealed_by) if revealed_by else None
    if anchor is None:
        return Placement(
            observation_id=observation_id,
            outcome=PlacementOutcome.NO_ANCHOR,
            scope=scope,
            reason=(
                f"scope is disjoint from every cell and no cell revealed it "
                f"(revealed_by={revealed_by!r}); an unattributable scope cannot be "
                "attached to a plausible-looking parent"
            ),
            obstruction=Obstruction(
                kind=ObstructionKind.SCOPE_OBSTRUCTION,
                detail=(
                    f"no anchor for a new scope from {observation_id}; "
                    "context cannot grow here"
                ),
                subject_refs=(observation_id, revealed_by),
            ),
        )

    return Placement(
        observation_id=observation_id,
        outcome=PlacementOutcome.EXTENDED,
        parent_cell=anchor.cell_id,
        scope=scope,
        reason=(
            f"scope is disjoint from every cell; anchored to {anchor.cell_id} "
            "because that cell revealed it"
        ),
    )


def new_cell_for(
    placement: Placement,
    *,
    context_id: str,
    kind: CellKind = CellKind.DOCUMENT,
    temporal_slice: tuple[str, str] = (),
    semantic_regime_ref: str = "",
    produced_by: str = "",
    method_fingerprint: str = "",
) -> ContextCell | None:
    """Materialise the cell a growth placement implies, or ``None`` if refused."""
    if placement.outcome is not PlacementOutcome.EXTENDED or placement.scope is None:
        return None
    return ContextCell(
        context_id=context_id,
        kind=kind,
        scope=placement.scope,
        parent_cell=placement.parent_cell,
        temporal_slice=temporal_slice,
        observation_refs=(placement.observation_id,),
        semantic_regime_ref=semantic_regime_ref,
        produced_by=produced_by,
        method_fingerprint=method_fingerprint,
    )


@dataclass(frozen=True, slots=True)
class GrowthResult:
    """The outcome of one tick's cell step: what changed, what was refused."""

    cells: tuple[ContextCell, ...]
    created: tuple[ContextCell, ...] = ()
    placements: tuple[Placement, ...] = ()
    obstructions: tuple[Obstruction, ...] = ()

    @property
    def refused(self) -> tuple[Placement, ...]:
        return tuple(
            placement
            for placement in self.placements
            if not placement.is_placed
        )

    def is_complete(self) -> bool:
        """False means at least one observation could not be placed.

        The caller must treat that as a finding, not as a no-op: a refusal means the
        context could not grow to cover the evidence, which changes what the
        investigation is entitled to conclude.
        """
        return not self.refused

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_count": len(self.cells),
            "created": [cell.cell_id for cell in self.created],
            "placements": [placement.as_dict() for placement in self.placements],
            "refused": [placement.as_dict() for placement in self.refused],
            "obstructions": [item.as_dict() for item in self.obstructions],
        }


def extend_or_recompute_cells(
    context_id: str,
    cells: Sequence[ContextCell],
    incoming: Mapping[str, Scope],
    *,
    revealed_by: Mapping[str, str] | None = None,
    invalidated: Iterable[str] = (),
    recompute: bool = True,
    kind: CellKind = CellKind.DOCUMENT,
    temporal_slice: tuple[str, str] = (),
    semantic_regime_ref: str = "",
    produced_by: str = "",
    method_fingerprint: str = "",
    root_scope: Scope | None = None,
) -> GrowthResult:
    """The branch Appendix I.7 omits: recompute invalidated cells, extend the rest.

    ``incoming`` maps an observation id to the scope it declares. Every observation
    is placed -- absorbed into a cell, or creating an anchored new one. Nothing is
    dropped: a refused placement is returned as a refusal with its obstruction, so
    the caller sees that the context could not grow rather than assuming it did.

    ``root_scope`` bootstraps the very first cell. Without it a fresh context refuses
    every placement with ``NO_ANCHOR``, because there is by definition no parent to
    attach to -- correct in isolation, and useless in practice, since a context could
    then never begin. The root is not a fabricated parent: it is the scope the
    investigation *declared*, which is an external warrant rather than an inference
    drawn from the evidence. A root with an ``unknown`` scope is refused, on the same
    reasoning that refuses an undetermined observation.
    """
    anchors = dict(revealed_by or {})
    working = tuple(cells)
    created: list[ContextCell] = []
    placements: list[Placement] = []
    obstructions: list[Obstruction] = []

    root_created: ContextCell | None = None
    if not working and root_scope is not None and not root_scope.unknown:
        root_created = ContextCell(
            context_id=context_id,
            kind=CellKind.CUSTOM,
            scope=root_scope,
            parent_cell="",
            observation_refs=(),
            produced_by=produced_by or "declared_scope",
            method_fingerprint=method_fingerprint,
        )
        working = (root_created,)
        created.append(root_created)

    invalidated_set = set(invalidated)
    for cell in working:
        if not recompute or cell.cell_id not in invalidated_set:
            continue
        # A recompute re-derives derived fields; ancestry and identity stay put.
        refreshed = replace(
            cell,
            observation_refs=tuple(sorted(set(cell.observation_refs))),
        )
        working = tuple(
            refreshed if item.cell_id == cell.cell_id else item for item in working
        )

    for observation_id in sorted(incoming):
        scope = incoming[observation_id]
        placement = place_observation(
            observation_id,
            scope,
            working,
            kind=kind,
            revealed_by=anchors.get(observation_id, ""),
            temporal_slice=temporal_slice,
            semantic_regime_ref=semantic_regime_ref,
            produced_by=produced_by,
            method_fingerprint=method_fingerprint,
        )
        placements.append(placement)
        if placement.obstruction is not None:
            obstructions.append(placement.obstruction)
        if placement.outcome is not PlacementOutcome.EXTENDED:
            continue
        cell = new_cell_for(
            placement,
            context_id=context_id,
            kind=kind,
            temporal_slice=temporal_slice,
            semantic_regime_ref=semantic_regime_ref,
            produced_by=produced_by,
            method_fingerprint=method_fingerprint,
        )
        if cell is not None:
            created.append(cell)
            working = working + (cell,)

    return GrowthResult(
        cells=working,
        created=tuple(created),
        placements=tuple(placements),
        obstructions=tuple(obstructions),
    )


def merge_observing_cells(
    existing: Sequence[ContextCell],
    created: Sequence[ContextCell],
) -> tuple[ContextCell, ...]:
    """Fold absorbed observations back into the cell that took them.

    Without this a placement would be computed and then discarded, which is the same
    defect as never placing at all: the observation would be recorded as absorbed
    while the cell still lacked it.
    """
    absorbed: dict[str, set[str]] = {}
    for cell in created:
        absorbed.setdefault(cell.parent_cell, set()).update(cell.observation_refs)

    merged: list[ContextCell] = []
    for cell in existing:
        extra = absorbed.get(cell.cell_id)
        if extra:
            merged.append(cell.with_observations(sorted(extra)))
        else:
            merged.append(cell)
    return tuple(merged)