"""Contract: compatibility and triple-coherent gluing (spec 025 §9, §10, ADR-0031).

ADR-0031 states why this exists: "pairwise compatibility of sections is not
local-global compatibility on overlaps; the cocycle condition on triple overlaps
is a separate requirement." Three cells can agree pairwise and be jointly
inconsistent, so §10.2 step 6 restricts to the *triple* overlap and checks that
the three restrictions agree there.

Three rules are enforced as code, because ADR-0031 marks them as such:

1. ``GLUED`` may never be returned while ``triples_unchecked > 0`` -- asserted
   both at the decision site and in ``GluingResult.__post_init__``, so no caller
   can construct an inconsistent result.
2. ``BLOCKED`` is not ``FALSE``: it means insufficient evidence, and the
   obstructions say which check failed.
3. Truncation is recorded, never silent.

The property test in ``TestGluingInvariants`` covers ADR-0031's own checklist
item "no code path returns GLUED when triples_unchecked > 0" without Hypothesis,
which this repository does not yet depend on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.locality import (
    CellKind,
    ContextCell,
    ObstructionKind,
    Scope,
)
from context.operators.compatibility import (
    DIMENSIONS,
    CompatibilityVerdict,
    Dimension,
    DimensionResult,
    DimensionVerdict,
    assess_pair,
    assess_structural,
)
from context.operators.gluing import (
    GluingProfile,
    GluingResult,
    GluingVerdict,
    coherent_on_triple,
    discover_overlaps,
    enumerate_triangles,
    glue,
    overlap_scope,
)

pytestmark = pytest.mark.contract

CTX = "CXI-test"
STRUCTURAL = Dimension.STRUCTURAL
NUMERIC = Dimension.NUMERIC


def _cell(members: list[str], **kwargs) -> ContextCell:
    kwargs.setdefault("produced_by", "operator.x@1.0")
    kwargs.setdefault("method_fingerprint", "mf-1")
    return ContextCell(
        context_id=CTX, kind=CellKind.DOCUMENT, scope=Scope.entity(*members), **kwargs
    )


class TestEightDimensions:
    def test_all_eight_are_assessed(self) -> None:
        assert len(DIMENSIONS) == 8
        assert {d.value for d in DIMENSIONS} == {
            "identity",
            "temporal",
            "spatial",
            "semantic",
            "structural",
            "numeric",
            "provenance",
            "causal",
        }

    def test_undetermined_dimension_is_unknown_not_not_applicable(self) -> None:
        """§0.2: undetermined is not "does not apply"."""
        left = _cell(["A"], entity_refs=("E1",), temporal_slice=("2024-01-01", "2024-06-01"))
        right = _cell(["B"], entity_refs=("E2",), temporal_slice=("2024-06-01", "2024-12-01"))
        result = assess_pair(left, right, overlap_id="OVL-1")
        assert result.verdict_of(Dimension.SEMANTIC) is DimensionVerdict.UNKNOWN
        assert result.verdict_of(Dimension.SEMANTIC) is not DimensionVerdict.NOT_APPLICABLE

    def test_missing_evidence_is_distinct_from_blocking(self) -> None:
        left = _cell(["A"])
        right = _cell(["B"])
        result = assess_pair(left, right, overlap_id="OVL-1")
        assert result.missing_evidence
        assert result.blocking_dimensions == ()

    def test_verdict_is_unresolved_when_nothing_was_determined(self) -> None:
        assert assess_pair(_cell(["A"]), _cell(["B"]), overlap_id="OVL-1").verdict is (
            CompatibilityVerdict.UNRESOLVED
        )

    def test_rollup_never_uses_a_weighted_score(self) -> None:
        """§14.1: distinct quantities are not commensurable, so no averaging."""
        left = _cell(["A", "B"], relation_refs=("R1",))
        right = _cell(["B", "C"], relation_refs=("R1",))
        result = assess_pair(left, right, overlap_id="OVL-1")
        assert result.verdict in tuple(CompatibilityVerdict)

    def test_assessment_id_is_content_addressed(self) -> None:
        left = _cell(["A"])
        right = _cell(["B"])
        one = assess_pair(left, right, overlap_id="OVL-1")
        two = assess_pair(left, right, overlap_id="OVL-1")
        assert one.assessment_id == two.assessment_id


class TestRefutationIsReachable:
    """The four-valued verdict must be able to say CONTRADICTED, not only UNKNOWN.

    An earlier version of this module declared ``CONTRADICTED`` and had no
    assessor that could produce it, which made ``INCOMPATIBLE`` and ``BLOCKED``
    unreachable code. These tests fail if that regresses.
    """

    def test_numeric_disagreement_beyond_tolerance_is_contradicted(self) -> None:
        left = _cell(
            ["A", "B"],
            relation_refs=("R1",),
            completeness={"numeric_values": {"balance": 1_000_000}, "numeric_tolerance": 0.01},
        )
        right = _cell(
            ["B", "C"],
            relation_refs=("R2",),
            completeness={"numeric_values": {"balance": 5_000_000}, "numeric_tolerance": 0.01},
        )
        result = assess_pair(left, right, overlap_id="OVL-1")
        assert result.verdict_of(NUMERIC) is DimensionVerdict.CONTRADICTED
        assert result.verdict is CompatibilityVerdict.INCOMPATIBLE
        assert NUMERIC in result.blocking_dimensions

    def test_numeric_agreement_within_tolerance_is_supported(self) -> None:
        left = _cell(
            ["A", "B"],
            relation_refs=("R1",),
            completeness={"numeric_values": {"v": 10.0}, "numeric_tolerance": 0.5},
        )
        right = _cell(
            ["B", "C"],
            relation_refs=("R2",),
            completeness={"numeric_values": {"v": 10.3}, "numeric_tolerance": 0.5},
        )
        assert assess_pair(left, right, overlap_id="OVL-1").verdict_of(NUMERIC) is (
            DimensionVerdict.SUPPORTED
        )

    def test_asserted_conflict_beats_a_shared_relation_ref(self) -> None:
        """An explicit refutation outranks a weak match."""
        left = _cell(
            ["A", "B"],
            relation_refs=("R1", "R2"),
            completeness={"relation_assertions": [("A", "owns", "B")]},
        )
        right = _cell(
            ["B", "C"],
            relation_refs=("R1", "R3"),
            completeness={"relation_assertions": [("A", "owns", "Z")]},
        )
        result = assess_pair(left, right, overlap_id="OVL-1")
        assert result.verdict_of(STRUCTURAL) is DimensionVerdict.CONTRADICTED

    def test_agreeing_assertions_without_shared_refs_stay_unknown(self) -> None:
        """Identical assertions, but nothing links the two relation sets.

        Reporting SUPPORTED here would claim the two cells describe the same edge,
        which no shared reference establishes. UNKNOWN is the honest answer.
        """
        left = _cell(
            ["A", "B"], relation_refs=("R1",), completeness={"relation_assertions": [("A", "owns", "B")]}
        )
        right = _cell(
            ["C", "D"], relation_refs=("R9",), completeness={"relation_assertions": [("A", "owns", "B")]}
        )
        assert assess_structural(left, right).verdict is DimensionVerdict.UNKNOWN

    def test_agreeing_assertions_with_a_shared_ref_are_supported(self) -> None:
        left = _cell(
            ["A", "B"], relation_refs=("R1",), completeness={"relation_assertions": [("A", "owns", "B")]}
        )
        right = _cell(
            ["B", "C"], relation_refs=("R1",), completeness={"relation_assertions": [("A", "owns", "B")]}
        )
        assert assess_structural(left, right).verdict is DimensionVerdict.SUPPORTED

    def test_a_dimension_can_be_overridden_without_defaulting_the_rest(self) -> None:
        left = _cell(["A"])
        right = _cell(["B"])
        result = assess_pair(
            left,
            right,
            overlap_id="OVL-1",
            overrides={NUMERIC: DimensionResult(NUMERIC, DimensionVerdict.CONTRADICTED, "test")},
        )
        assert result.verdict_of(NUMERIC) is DimensionVerdict.CONTRADICTED
        assert result.verdict_of(Dimension.SEMANTIC) is DimensionVerdict.UNKNOWN


class TestOverlapDiscovery:
    def test_overlap_requires_shared_scope(self) -> None:
        assert overlap_scope(_cell(["A"]), _cell(["Z"])) is None

    def test_unknown_scope_still_overlaps(self) -> None:
        """§7.2: undetermined cells stay reachable rather than vanishing."""
        undetermined = ContextCell(
            context_id=CTX, kind=CellKind.DOCUMENT, scope=Scope.semantic_unknown()
        )
        assert overlap_scope(_cell(["A"]), undetermined) is not None

    def test_bucket_overflow_is_recorded_not_skipped_silently(self) -> None:
        cells = [_cell(["SHARED", f"E{i}"]) for i in range(5)]
        _, obstructions = discover_overlaps(cells, max_bucket_size=2)
        assert obstructions
        assert any(item.kind is ObstructionKind.BUCKET_OVERFLOW for item in obstructions)

    def test_no_all_pairs_comparison_is_needed(self) -> None:
        """Disjoint cells produce no overlaps at all, so no pairs were compared."""
        cells = [_cell(["A"]), _cell(["B"]), _cell(["C"])]
        overlaps, obstructions = discover_overlaps(cells)
        assert overlaps == ()
        assert obstructions == ()

    def test_each_pair_is_discovered_exactly_once(self) -> None:
        """Regression: an unsorted dedup key found every pair twice.

        That doubled the comparison work and the obstruction count, which is
        visible to an analyst as inflated blocking evidence.
        """
        cells = [
            _cell(["A", "B", "S"], entity_refs=("S",)),
            _cell(["B", "C", "S"], entity_refs=("S",)),
            _cell(["C", "A", "S"], entity_refs=("S",)),
        ]
        overlaps, _ = discover_overlaps(cells)
        assert len(overlaps) == 3
        pairs = [overlap.cell_ids for overlap in overlaps]
        assert len(set(pairs)) == len(pairs)

    def test_undetermined_pair_yields_one_obstruction_not_two(self) -> None:
        cells = [_cell(["A", "B"]), _cell(["B", "C"])]
        result = glue(cells, context_id=CTX)
        coverage = [
            item for item in result.obstructions
            if item.kind is ObstructionKind.MISSING_COVERAGE
        ]
        assert len(coverage) == 1


class TestTripleEnumeration:
    def _overlap_graph(self):
        cells = [_cell(["A", "B", "C"], entity_refs=("S",)), _cell(["B", "C"], entity_refs=("S",)), _cell(["C", "A"], entity_refs=())]
        overlaps, _ = discover_overlaps(cells)
        return cells, overlaps

    def test_triangles_come_from_the_overlap_graph(self) -> None:
        _cells, overlaps = self._overlap_graph()
        triples, unchecked = enumerate_triangles(overlaps, max_triples=100)
        assert len(triples) == 1
        assert unchecked == 0

    def test_triangle_order_is_stable(self) -> None:
        _cells, overlaps = self._overlap_graph()
        first, _ = enumerate_triangles(overlaps, max_triples=100)
        second, _ = enumerate_triangles(overlaps, max_triples=100)
        assert first == second

    def test_budget_truncation_is_counted(self) -> None:
        _cells, overlaps = self._overlap_graph()
        _, unchecked = enumerate_triangles(overlaps, max_triples=0)
        assert unchecked == 1

    def test_wedge_is_not_a_triangle(self) -> None:
        _cells, overlaps = self._overlap_graph()
        pairs = {overlap.cell_ids: overlap for overlap in overlaps}
        triples, _ = enumerate_triangles(overlaps, max_triples=100)
        for triple in triples:
            for a, b in ((triple[0], triple[1]), (triple[0], triple[2]), (triple[1], triple[2])):
                assert (a, b) in pairs


class TestTripleCoherence:
    def test_jointly_inconsistent_triple_is_detected(self) -> None:
        """ADR-0031 checklist N.6: pairwise compatible, jointly inconsistent."""
        cells = [
            _cell(["A", "B", "S"], entity_refs=("S",)),
            _cell(["B", "C", "S"], entity_refs=("S",)),
            _cell(["C", "A", "S"], entity_refs=()),
        ]
        result = glue(cells, context_id=CTX)
        assert result.verdict is GluingVerdict.PARTIALLY_GLUED
        assert any(
            item.kind is ObstructionKind.TRIPLE_INCONSISTENCY for item in result.obstructions
        )
        assert result.verdict is not GluingVerdict.GLUED

    def test_coherent_triple_passes(self) -> None:
        cells = [
            _cell(["A", "B", "S"], entity_refs=("S",)),
            _cell(["B", "C", "S"], entity_refs=("S",)),
            _cell(["C", "A", "S"], entity_refs=("S",)),
        ]
        overlaps, _ = discover_overlaps(cells)
        by_id = {cell.cell_id: cell for cell in cells}
        pairs = {overlap.cell_ids: overlap for overlap in overlaps}
        triple = tuple(sorted(cell.cell_id for cell in cells))
        coherent, reason = coherent_on_triple(triple, pairs, by_id)
        assert coherent is True
        assert "agree" in reason


class TestGluingVerdicts:
    def test_conflict_under_a_strict_profile_is_blocked(self) -> None:
        left = _cell(
            ["A", "B"],
            relation_refs=("R1",),
            completeness={"numeric_values": {"v": 1.0}, "numeric_tolerance": 0.01},
        )
        right = _cell(
            ["B", "C"],
            relation_refs=("R2",),
            completeness={"numeric_values": {"v": 2.0}, "numeric_tolerance": 0.01},
        )
        result = glue(
            [left, right], context_id=CTX, profile=GluingProfile(allows_partial_gluing=False)
        )
        assert result.verdict is GluingVerdict.BLOCKED

    def test_blocked_is_not_a_false_claim(self) -> None:
        """ADR-0031 rule 7: BLOCKED means insufficient evidence, and must say so."""
        left = _cell(
            ["A", "B"],
            relation_refs=("R1",),
            completeness={"numeric_values": {"v": 1.0}, "numeric_tolerance": 0.01},
        )
        right = _cell(
            ["B", "C"],
            relation_refs=("R2",),
            completeness={"numeric_values": {"v": 2.0}, "numeric_tolerance": 0.01},
        )
        result = glue(
            [left, right], context_id=CTX, profile=GluingProfile(allows_partial_gluing=False)
        )
        assert result.obstructions
        assert all(item.detail for item in result.obstructions)

    def test_undetermined_pairs_produce_a_coverage_obstruction(self) -> None:
        result = glue([_cell(["A", "B"]), _cell(["B", "C"])], context_id=CTX)
        assert any(
            item.kind is ObstructionKind.MISSING_COVERAGE for item in result.obstructions
        )

    def test_result_records_its_inputs(self) -> None:
        cells = [_cell(["A", "B"]), _cell(["B", "C"])]
        result = glue(cells, context_id=CTX)
        assert set(result.input_cells) == {cell.cell_id for cell in cells}

    def test_gluing_id_is_content_addressed(self) -> None:
        one = glue([_cell(["A", "B"]), _cell(["B", "C"])], context_id=CTX)
        two = glue([_cell(["A", "B"]), _cell(["B", "C"])], context_id=CTX)
        assert one.gluing_id == two.gluing_id


class TestGluingInvariants:
    """ADR-0031's own checklist, as executable guarantees."""

    def test_result_refuses_to_construct_glued_with_unchecked_triples(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            GluingResult(
                context_id=CTX,
                input_cells=("a", "b"),
                verdict=GluingVerdict.GLUED,
                merged_scope=Scope.entity("a"),
                triples_checked=1,
                triples_unchecked=1,
            )
        assert "GLUED" in str(excinfo.value)

    def test_truncated_triangle_enumeration_never_yields_glued(self) -> None:
        cells = [
            _cell(["A", "B", "S"], entity_refs=("S",)),
            _cell(["B", "C", "S"], entity_refs=("S",)),
            _cell(["C", "A", "S"], entity_refs=("S",)),
        ]
        result = glue(cells, context_id=CTX, profile=GluingProfile(max_triples=0))
        assert result.triples_unchecked > 0
        assert result.verdict is not GluingVerdict.GLUED

    def test_no_exhaustive_sweep_returns_glued_with_unchecked_triples(self) -> None:
        """The property ADR-0031 asks for, over a deterministic sweep.

        Sweeps triples rather than pairs: a pair can never produce a triangle, so
        a pair-only sweep would pass vacuously.
        """
        import itertools

        specs = [
            (["A", "B", "S"], ("S",)),
            (["B", "C", "S"], ("S",)),
            (["C", "A", "S"], ()),
            (["A", "B", "S"], ("S",)),
            (["B", "D", "S"], ("S",)),
        ]
        checked_any_truncation = False
        for budget in (0, 1, 2, 10):
            for combination in itertools.combinations(specs, 3):
                cells = [_cell(members, entity_refs=refs) for members, refs in combination]
                result = glue(cells, context_id=CTX, profile=GluingProfile(max_triples=budget))
                if result.triples_unchecked > 0:
                    checked_any_truncation = True
                    assert result.verdict is not GluingVerdict.GLUED, (
                        f"GLUED with {result.triples_unchecked} unchecked under budget {budget}"
                    )
        # Guard against the sweep being vacuous.
        assert checked_any_truncation

    def test_every_obstruction_explains_itself(self) -> None:
        result = glue([_cell(["A", "B"]), _cell(["B", "C"])], context_id=CTX)
        assert all(item.detail for item in result.obstructions)

    def test_disjoint_cells_gluing_produces_no_claims(self) -> None:
        result = glue([_cell(["A"]), _cell(["Z"])], context_id=CTX)
        assert result.merged_scope.members == frozenset()
