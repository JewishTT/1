"""Contract: cells, the scope lattice, recorded restriction loss, obstructions.

None of this existed: §7.1's ``ContextCell``, §7.2's scope algebra, §8.1's
``RestrictionMap`` with its ``loss_profile``, and §10.3's obstruction taxonomy
were specification-only. The object's summary found zero code for
``ContextCell``/``ScopeKind``/``RestrictionMap``/``OBST-``.

Three behaviours are pinned hardest, because each one is a §0.2 violation waiting
to happen:

* An undetermined scope yields ``UNKNOWN``, never ``EMPTY``. §0.2: "unknown
  relation type != discard relation signal". If UNKNOWN collapsed to EMPTY, an
  unmapped relation would silently remove every cell that could have carried it.
* An empty determination and an absent determination are different things.
* A restriction must record what it dropped, and it may narrow but never widen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.locality import (
    CellKind,
    ContextCell,
    LossProfile,
    Obstruction,
    ObstructionKind,
    PrecisionLoss,
    RestrictionMap,
    Scope,
    ScopeIntersection,
    ScopeKind,
    cells_within,
    children_of,
    descendants_of,
    intersect_scopes,
    measure_loss,
    roots_of,
    scopes_disjoint,
)

pytestmark = pytest.mark.contract

CTX = "CXI-test"


class TestScopeLattice:
    def test_nine_scope_kinds_exist(self) -> None:
        assert len(list(ScopeKind)) == 9

    def test_eight_cell_kinds_exist(self) -> None:
        assert len(list(CellKind)) == 8

    def test_exact_on_identical(self) -> None:
        scope = Scope.entity("A", "B")
        assert intersect_scopes(scope, Scope.entity("A", "B")) is ScopeIntersection.EXACT

    def test_exact_on_containment_either_way(self) -> None:
        big = Scope.entity("A", "B", "C")
        assert intersect_scopes(big, Scope.entity("A", "B")) is ScopeIntersection.EXACT
        assert intersect_scopes(Scope.entity("A", "B"), big) is ScopeIntersection.EXACT

    def test_partial_on_overlap_without_containment(self) -> None:
        verdict = intersect_scopes(Scope.entity("A", "B"), Scope.entity("B", "C"))
        assert verdict is ScopeIntersection.PARTIAL

    def test_empty_on_disjoint(self) -> None:
        assert intersect_scopes(Scope.entity("A"), Scope.entity("Z")) is ScopeIntersection.EMPTY

    def test_empty_across_kinds_with_no_shared_member(self) -> None:
        entity = Scope.entity("A")
        temporal = Scope.temporal("2024-01-01", "2024-12-31")
        assert intersect_scopes(entity, temporal) is ScopeIntersection.EMPTY

    def test_different_kinds_never_reach_exact(self) -> None:
        """Same referent, different kind: compatible, but not the same scope."""
        custom = Scope(ScopeKind.CUSTOM, frozenset({"A"}))
        assert intersect_scopes(Scope.entity("A"), custom) is ScopeIntersection.PARTIAL

    def test_undetermined_scope_is_unknown_not_empty(self) -> None:
        """The §0.2 rule, at scope level. This is the one that must not regress."""
        assert (
            intersect_scopes(Scope.entity("A"), Scope.semantic_unknown())
            is ScopeIntersection.UNKNOWN
        )

    def test_undetermined_wins_even_against_disjoint_members(self) -> None:
        assert (
            intersect_scopes(Scope.entity("A"), Scope(ScopeKind.ENTITY, frozenset(), unknown=True))
            is ScopeIntersection.UNKNOWN
        )

    def test_empty_determination_is_empty(self) -> None:
        assert intersect_scopes(Scope.entity("A"), Scope(ScopeKind.ENTITY, frozenset())) is (
            ScopeIntersection.EMPTY
        )

    def test_empty_and_undetermined_are_different_things(self) -> None:
        determined = Scope(ScopeKind.ENTITY, frozenset())
        undetermined = Scope(ScopeKind.ENTITY, frozenset(), unknown=True)
        assert determined.is_empty() is True
        assert undetermined.is_empty() is False

    def test_disjoint_helper_agrees_with_the_lattice(self) -> None:
        assert scopes_disjoint(Scope.entity("A"), Scope.entity("B")) is True
        assert scopes_disjoint(Scope.entity("A", "B"), Scope.entity("B")) is False


class TestCellIdentity:
    def test_cell_id_is_content_addressed(self) -> None:
        cell = ContextCell(context_id=CTX, kind=CellKind.DOCUMENT, scope=Scope.entity("A"))
        assert cell.cell_id.startswith("CXC-")
        assert cell.cell_id == cell.address()

    def test_declared_mismatched_id_is_refused(self) -> None:
        with pytest.raises(ValueError):
            ContextCell(
                context_id=CTX,
                kind=CellKind.DOCUMENT,
                scope=Scope.entity("A"),
                cell_id="CXC-wrong",
            )

    def test_same_material_yields_the_same_id(self) -> None:
        one = ContextCell(context_id=CTX, kind=CellKind.DOCUMENT, scope=Scope.entity("A"))
        two = ContextCell(context_id=CTX, kind=CellKind.DOCUMENT, scope=Scope.entity("A"))
        assert one.cell_id == two.cell_id

    def test_parent_participates_in_identity(self) -> None:
        """Two identical sub-questions under different parents are different cells."""
        left = ContextCell(context_id=CTX, kind=CellKind.DOCUMENT, scope=Scope.entity("A"))
        right = ContextCell(context_id=CTX, kind=CellKind.DOCUMENT, scope=Scope.entity("A"))
        a = ContextCell(context_id=CTX, kind=CellKind.CUSTOM, scope=Scope.entity("A"),
                        parent_cell=left.cell_id)
        b = ContextCell(context_id=CTX, kind=CellKind.CUSTOM, scope=Scope.entity("A"),
                        parent_cell=right.cell_id)
        assert a.cell_id == b.cell_id  # same parent material
        c = ContextCell(context_id=CTX, kind=CellKind.CUSTOM, scope=Scope.entity("A"),
                        parent_cell="CXC-different")
        assert c.cell_id != a.cell_id

    def test_unknown_trust_state_is_refused(self) -> None:
        with pytest.raises(ValueError):
            ContextCell(
                context_id=CTX,
                kind=CellKind.DOCUMENT,
                scope=Scope.entity("A"),
                trust_state="probably-fine",
            )

    def test_cell_without_a_context_is_refused(self) -> None:
        with pytest.raises(ValueError):
            ContextCell(context_id="", kind=CellKind.DOCUMENT, scope=Scope.entity("A"))

    def test_serialises_with_every_inspectability_field(self) -> None:
        cell = ContextCell(
            context_id=CTX,
            kind=CellKind.SOURCE,
            scope=Scope.entity("A"),
            temporal_slice=("2024-01-01", "2024-06-01"),
            semantic_regime_ref="SR-1",
            produced_by="operator.x@1.0",
            method_fingerprint="mf-1",
        )
        payload = cell.as_dict()
        for field in (
            "scope",
            "temporal_slice",
            "semantic_regime_ref",
            "trust_state",
            "produced_by",
            "method_fingerprint",
        ):
            assert field in payload


def _cell(scope: Scope, *, kind: CellKind = CellKind.DOCUMENT, parent: str = "", **kwargs):
    return ContextCell(
        context_id=CTX, kind=kind, scope=scope, parent_cell=parent, **kwargs
    )


class TestAncestry:
    def _chain(self):
        a = _cell(Scope.entity("GAZPROM"), kind=CellKind.ORGANIZATION)
        b = _cell(Scope.entity("GAZPROM", "GAZPROM_NEFT"), parent=a.cell_id)
        c = _cell(Scope.entity("GAZPROM", "GAZPROM_NEFT", "SIBUR"), parent=b.cell_id)
        return a, b, c

    def test_root_is_a_root(self) -> None:
        a, _, _ = self._chain()
        assert a.is_root is True

    def test_ancestry_runs_root_to_self(self) -> None:
        a, b, c = self._chain()
        index = {cell.cell_id: cell for cell in (a, b, c)}
        assert c.ancestry(index) == (a.cell_id, b.cell_id, c.cell_id)

    def test_descendants_are_reachable_in_one_query(self) -> None:
        """The query flat cells cannot answer at all."""
        a, b, c = self._chain()
        found = descendants_of(a.cell_id, (a, b, c))
        assert {cell.cell_id for cell in found} == {b.cell_id, c.cell_id}

    def test_descendant_order_does_not_depend_on_input_order(self) -> None:
        """BFS by level, key-ordered within a level.

        Level order is what makes a subtree readable; the guarantee that matters
        is that it does not depend on how the cells happened to be supplied.
        """
        a, b, c = self._chain()
        forward = [cell.cell_id for cell in descendants_of(a.cell_id, (a, b, c))]
        reverse = [cell.cell_id for cell in descendants_of(a.cell_id, (c, b, a))]
        assert forward == reverse
        assert set(forward) == {b.cell_id, c.cell_id}
        assert forward.index(b.cell_id) < forward.index(c.cell_id)

    def test_roots_of_a_forest(self) -> None:
        a, _, _ = self._chain()
        lonely = _cell(Scope.entity("OTHER"))
        assert {cell.cell_id for cell in roots_of((a, lonely))} == {a.cell_id, lonely.cell_id}

    def test_children_of_leaf_is_empty(self) -> None:
        a, b, c = self._chain()
        assert children_of(c.cell_id, (a, b, c)) == ()

    def test_missing_parent_raises_rather_than_truncating(self) -> None:
        orphan = _cell(Scope.entity("A"), parent="CXC-absent")
        with pytest.raises(KeyError):
            orphan.ancestry({orphan.cell_id: orphan})

    def test_cycle_terminates_with_an_error(self) -> None:
        """A corrupt store must produce a short answer, not a hung investigation."""
        first = _cell(Scope.entity("A"))
        second = _cell(Scope.entity("B"), parent=first.cell_id)
        corrupt = _cell(Scope.entity("C"), parent=second.cell_id)
        index = {cell.cell_id: cell for cell in (first, second, corrupt)}
        object.__setattr__(first, "parent_cell", corrupt.cell_id)
        object.__setattr__(first, "cell_id", first.address())
        index[first.cell_id] = first
        with pytest.raises(ValueError):
            first.ancestry(index)


class TestScopeQuery:
    def test_cells_within_uses_the_lattice(self) -> None:
        target = Scope.entity("ORG-1", "ORG-2")
        inside = _cell(Scope.entity("ORG-1", "ORG-2", "ORG-3"))
        outside = _cell(Scope.entity("ORG-9"))
        found = cells_within(target, (inside, outside))
        assert [cell.cell_id for cell in found] == [inside.cell_id]

    def test_undetermined_cells_stay_reachable(self) -> None:
        """A cell that was never determined must not become invisible."""
        target = Scope.entity("ORG-1")
        undetermined = _cell(Scope.semantic_unknown())
        found = cells_within(target, (undetermined,))
        assert len(found) == 1


class TestRestrictionLoss:
    def _source(self):
        return ContextCell(
            context_id=CTX,
            kind=CellKind.ORGANIZATION,
            scope=Scope.entity("ORG-1", "ORG-2", "ORG-3"),
            entity_refs=("E1", "E2", "E3"),
            relation_refs=("R1", "R2"),
        )

    def test_measured_loss_reflects_what_was_dropped(self) -> None:
        source = self._source()
        loss = measure_loss(
            source, kept_observations=(), kept_entities=("E1",), kept_relations=("R1",)
        )
        assert loss.entities_removed == 2
        assert loss.relations_removed == 1
        assert loss.is_lossless is False

    def test_lossless_restriction_is_reported_as_such(self) -> None:
        source = self._source()
        loss = measure_loss(
            source,
            kept_observations=("O1",),
            kept_entities=source.entity_refs,
            kept_relations=source.relation_refs,
        )
        assert loss.is_lossless is True

    def test_precision_loss_is_recorded_not_implied(self) -> None:
        source = self._source()
        loss = measure_loss(
            source,
            kept_observations=(),
            kept_entities=source.entity_refs,
            kept_relations=source.relation_refs,
            temporal_precision_loss=PrecisionLoss.COARSENED,
            semantic_precision_loss=PrecisionLoss.UNKNOWN,
        )
        assert loss.temporal_precision_loss is PrecisionLoss.COARSENED
        assert loss.semantic_precision_loss is PrecisionLoss.UNKNOWN
        assert loss.is_lossless is False

    def test_restriction_id_is_content_addressed(self) -> None:
        source = self._source()
        restriction = RestrictionMap(
            from_cell=source.cell_id, to_scope=Scope.entity("ORG-1"), loss_profile=LossProfile()
        )
        assert restriction.restriction_id.startswith("RST-")
        assert restriction.restriction_id == restriction.address()

    def test_restriction_requires_a_source_cell(self) -> None:
        with pytest.raises(ValueError):
            RestrictionMap(
                from_cell="", to_scope=Scope.entity("A"), loss_profile=LossProfile()
            )

    def test_narrowing_is_monotonic(self) -> None:
        source = self._source()
        restriction = RestrictionMap(
            from_cell=source.cell_id, to_scope=Scope.entity("ORG-1"), loss_profile=LossProfile()
        )
        assert restriction.is_monotonic(source) is True

    def test_disjoint_scope_is_not_monotonic(self) -> None:
        """A restriction may narrow but never widen into unrelated space."""
        source = self._source()
        restriction = RestrictionMap(
            from_cell=source.cell_id, to_scope=Scope.entity("ORG-99"), loss_profile=LossProfile()
        )
        assert restriction.is_monotonic(source) is False


class TestObstructions:
    def test_twelve_kinds_match_section_10_3(self) -> None:
        assert len(list(ObstructionKind)) == 12

    def test_obstruction_id_uses_the_obst_prefix(self) -> None:
        """``OBS-`` stays reserved for Observation (§10.3, v2)."""
        obstruction = Obstruction(kind=ObstructionKind.BUCKET_OVERFLOW, detail="overflow")
        assert obstruction.obstruction_id.startswith("OBST-")

    def test_obstruction_must_explain_itself(self) -> None:
        with pytest.raises(ValueError):
            Obstruction(kind=ObstructionKind.SEMANTIC_OBSTRUCTION, detail="")

    def test_identical_obstructions_address_identically(self) -> None:
        one = Obstruction(kind=ObstructionKind.SCOPE_OBSTRUCTION, detail="d")
        two = Obstruction(kind=ObstructionKind.SCOPE_OBSTRUCTION, detail="d")
        assert one.obstruction_id == two.obstruction_id

    def test_different_kinds_address_differently(self) -> None:
        one = Obstruction(kind=ObstructionKind.SCOPE_OBSTRUCTION, detail="d")
        two = Obstruction(kind=ObstructionKind.TEMPORAL_OBSTRUCTION, detail="d")
        assert one.obstruction_id != two.obstruction_id

    def test_bucket_overflow_is_a_first_class_kind(self) -> None:
        """§8.3 requires overflow to be recorded, not applied silently."""
        assert ObstructionKind.BUCKET_OVERFLOW.value == "bucket_overflow"
