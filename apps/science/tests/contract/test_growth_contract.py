"""Contract: context growth -- the branch Appendix I.7 omits (spec 025 §35, §I.7).

Appendix I.7 line 3094 is ``cells = recompute_cells(invalidated.cells)`` -- a
recompute with no creation branch. An observation that reveals a scope no existing
cell covers therefore has nowhere to go, and §0.2 forbids each workaround in the
same breath: dropping it is forbidden, forcing it into a neighbouring cell
manufactures false precision, and an unlinked cell cannot be retrieved as part of
anything -- so after several iterations the context is a bag of cells.

These tests pin the replacement branch and, just as importantly, pin that a
placement which *cannot* be made is returned as a refusal rather than dropped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.growth import (
    ChangeSet,
    InvalidationClass,
    PlacementOutcome,
    extend_or_recompute_cells,
    merge_observing_cells,
    new_cell_for,
    place_observation,
)
from context.locality import (
    CellKind,
    ContextCell,
    ObstructionKind,
    Scope,
    descendants_of,
)

pytestmark = pytest.mark.contract

CTX = "CXI-test"


def _cell(members: list[str], parent: str = "", kind: CellKind = CellKind.ORGANIZATION):
    return ContextCell(
        context_id=CTX,
        kind=kind,
        scope=Scope.entity(*members),
        parent_cell=parent,
        produced_by="operator.x@1.0",
        method_fingerprint="mf-1",
    )


class TestChangeSet:
    def test_a_change_set_names_its_batch(self) -> None:
        with pytest.raises(ValueError):
            ChangeSet(batch_ref="")

    def test_an_empty_batch_is_detected(self) -> None:
        assert ChangeSet(batch_ref="B-1").is_empty is True
        assert ChangeSet(batch_ref="B-1", added_observations=("O1",)).is_empty is False

    def test_removed_refs_exists_and_is_named_for_derived_views(self) -> None:
        """§35.1: 'Raw observations are never removed from the world'."""
        batch = ChangeSet(batch_ref="B-1", removed_refs=("derived-view-1",))
        assert batch.removed_refs == ("derived-view-1",)

    def test_five_invalidation_classes_exist(self) -> None:
        assert len(list(InvalidationClass)) == 5


class TestPlacementOutcomes:
    def test_a_covered_scope_is_absorbed(self) -> None:
        cell = _cell(["ORG-1", "ORG-2"])
        placement = place_observation("OBS-1", Scope.entity("ORG-1"), (cell,))
        assert placement.outcome is PlacementOutcome.ABSORBED
        assert placement.cell_id == cell.cell_id

    def test_an_identical_scope_is_absorbed_rather_than_duplicated(self) -> None:
        """Regression: five identical observations created five equal cells."""
        cell = _cell(["ORG-1"])
        placement = place_observation(
            "OBS-1", Scope.entity("ORG-1", "ORG-9"), (cell,)
        )
        assert placement.outcome is PlacementOutcome.EXTENDED
        created = new_cell_for(placement, context_id=CTX)
        assert created is not None
        second = place_observation("OBS-2", Scope.entity("ORG-1", "ORG-9"), (cell, created))
        assert second.outcome is PlacementOutcome.ABSORBED

    def test_a_widening_scope_extends_and_anchors_to_the_overlapping_cell(self) -> None:
        cell = _cell(["ORG-1"])
        placement = place_observation(
            "OBS-1", Scope.entity("ORG-1", "ORG-9"), (cell,), revealed_by=cell.cell_id
        )
        assert placement.outcome is PlacementOutcome.EXTENDED
        assert placement.parent_cell == cell.cell_id

    def test_a_disjoint_scope_extends_to_the_revealing_cell(self) -> None:
        cell = _cell(["ORG-1"])
        placement = place_observation(
            "OBS-1", Scope.entity("ORG-9"), (cell,), revealed_by=cell.cell_id
        )
        assert placement.outcome is PlacementOutcome.EXTENDED
        assert placement.parent_cell == cell.cell_id

    def test_an_undetermined_scope_places_nowhere(self) -> None:
        """§0.2: an unmade determination may not be turned into a membership."""
        cell = _cell(["ORG-1"])
        placement = place_observation("OBS-1", Scope.semantic_unknown(), (cell,))
        assert placement.outcome is PlacementOutcome.SCOPE_UNDETERMINED
        assert placement.is_placed is False
        assert placement.obstruction is not None
        assert placement.obstruction.kind is ObstructionKind.SCOPE_OBSTRUCTION

    def test_a_disjoint_scope_with_no_anchor_is_refused(self) -> None:
        cell = _cell(["ORG-1"])
        placement = place_observation("OBS-1", Scope.entity("ORG-9"), (cell,))
        assert placement.outcome is PlacementOutcome.NO_ANCHOR
        assert placement.is_placed is False
        assert placement.obstruction is not None

    def test_an_unknown_anchor_is_refused(self) -> None:
        cell = _cell(["ORG-1"])
        placement = place_observation(
            "OBS-1", Scope.entity("ORG-9"), (cell,), revealed_by="CXC-ghost"
        )
        assert placement.outcome is PlacementOutcome.NO_ANCHOR

    def test_a_refusal_always_explains_itself(self) -> None:
        cell = _cell(["ORG-1"])
        for scope, anchor in ((Scope.semantic_unknown(), ""), (Scope.entity("Z"), "")):
            placement = place_observation("OBS-1", scope, (cell,), revealed_by=anchor)
            assert placement.reason

    def test_placement_is_deterministic(self) -> None:
        cells = (_cell(["ORG-1"]), _cell(["ORG-1", "ORG-2"]))
        scope = Scope.entity("ORG-1", "ORG-3")
        first = place_observation("OBS", scope, cells)
        second = place_observation("OBS", scope, tuple(reversed(cells)))
        assert first.cell_id == second.cell_id
        assert first.outcome is second.outcome


class TestGrowth:
    def test_identical_observations_create_one_cell(self) -> None:
        cell = _cell(["ORG-1"])
        incoming = {f"OBS-{index}": Scope.entity("ORG-1", "ORG-9") for index in range(5)}
        result = extend_or_recompute_cells(
            CTX, (cell,), incoming, revealed_by={key: cell.cell_id for key in incoming}
        )
        assert len(result.created) == 1

    def test_depth_grows_across_iterations(self) -> None:
        """The property flat cells cannot provide."""
        root = _cell(["GAZPROM"])
        current = (root,)
        chain = [
            ["GAZPROM", "NEFT"],
            ["GAZPROM", "NEFT", "SIBUR"],
            ["SIBUR", "SPV"],
        ]
        for index, members in enumerate(chain, start=1):
            incoming = {f"O{index}": Scope.entity(*members)}
            result = extend_or_recompute_cells(
                CTX,
                current,
                incoming,
                revealed_by={f"O{index}": current[-1].cell_id},
            )
            current = result.cells
            assert len(result.created) == 1, index
            assert len(current) == index + 1
            assert len(descendants_of(root.cell_id, current)) == index

    def test_created_cells_are_retrievable_under_their_root(self) -> None:
        root = _cell(["GAZPROM"])
        result = extend_or_recompute_cells(
            CTX,
            (root,),
            {"O1": Scope.entity("SPV-77", "DOMAIN-9")},
            revealed_by={"O1": root.cell_id},
        )
        under = descendants_of(root.cell_id, result.cells)
        assert len(under) == 1
        assert under[0].parent_cell == root.cell_id

    def test_a_refusal_makes_the_growth_incomplete(self) -> None:
        cell = _cell(["ORG-1"])
        result = extend_or_recompute_cells(
            CTX, (cell,), {"O1": Scope.semantic_unknown()}
        )
        assert result.is_complete() is False
        assert len(result.refused) == 1

    def test_a_refusal_still_returns_the_observation_id(self) -> None:
        """The observation is refused, not dropped: its id comes back."""
        cell = _cell(["ORG-1"])
        result = extend_or_recompute_cells(
            CTX, (cell,), {"O-dropped": Scope.entity("ORG-9")}
        )
        assert result.placements[0].observation_id == "O-dropped"
        assert result.placements[0].is_placed is False

    def test_a_refusal_records_an_obstruction(self) -> None:
        cell = _cell(["ORG-1"])
        result = extend_or_recompute_cells(
            CTX, (cell,), {"O1": Scope.semantic_unknown()}
        )
        assert result.obstructions
        assert result.obstructions[0].kind is ObstructionKind.SCOPE_OBSTRUCTION

    def test_nothing_is_dropped_from_an_incoming_batch(self) -> None:
        cell = _cell(["ORG-1"])
        incoming = {
            "O-absorbed": Scope.entity("ORG-1"),
            "O-widened": Scope.entity("ORG-1", "ORG-9"),
            "O-unknown": Scope.semantic_unknown(),
            "O-orphan": Scope.entity("ORG-77"),
        }
        result = extend_or_recompute_cells(
            CTX, (cell,), incoming, revealed_by={"O-widened": cell.cell_id}
        )
        assert {p.observation_id for p in result.placements} == set(incoming)

    def test_growth_is_deterministic(self) -> None:
        cell = _cell(["ORG-1"])
        incoming = {f"OBS-{i}": Scope.entity("ORG-1", f"ORG-{i}") for i in range(4)}
        anchors = {key: cell.cell_id for key in incoming}
        first = extend_or_recompute_cells(CTX, (cell,), incoming, revealed_by=anchors)
        second = extend_or_recompute_cells(CTX, (cell,), incoming, revealed_by=anchors)
        assert [c.cell_id for c in first.cells] == [c.cell_id for c in second.cells]

    def test_an_empty_batch_changes_nothing(self) -> None:
        cell = _cell(["ORG-1"])
        result = extend_or_recompute_cells(CTX, (cell,), {})
        assert result.created == ()
        assert result.is_complete() is True
        assert len(result.cells) == 1

    def test_ancestry_is_preserved_across_growth(self) -> None:
        root = _cell(["GAZPROM"])
        first = extend_or_recompute_cells(
            CTX,
            (root,),
            {"O1": Scope.entity("GAZPROM", "NEFT")},
            revealed_by={"O1": root.cell_id},
        )
        leaf = first.created[0]
        assert leaf.ancestry({c.cell_id: c for c in first.cells}) == (
            root.cell_id,
            leaf.cell_id,
        )


class TestMergeAbsorbed:
    def test_absorbed_observations_are_folded_into_the_cell(self) -> None:
        """Without this a placement is computed and then discarded."""
        anchor = _cell(["ORG-1"])
        widened = ContextCell(
            context_id=CTX,
            kind=CellKind.ORGANIZATION,
            scope=Scope.entity("ORG-1", "ORG-9"),
            parent_cell=anchor.cell_id,
            observation_refs=("O1",),
            produced_by="op",
            method_fingerprint="mf",
        )
        merged = merge_observing_cells((anchor,), (widened,))
        assert "O1" in merged[0].observation_refs

    def test_a_cell_without_absorptions_is_untouched(self) -> None:
        """A cell whose parent is not among the existing cells merges nothing."""
        anchor = _cell(["ORG-1"])
        elsewhere = ContextCell(
            context_id=CTX,
            kind=CellKind.ORGANIZATION,
            scope=Scope.entity("Z"),
            parent_cell="CXC-not-in-this-batch",
            observation_refs=("O1",),
            produced_by="op",
            method_fingerprint="mf",
        )
        assert merge_observing_cells((anchor,), (elsewhere,))[0] is anchor