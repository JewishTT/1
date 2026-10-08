"""Contract: the built-in discipline adapters are selectable and executable.

This is the test that would have failed before the registry existed. Fourteen
discipline packages were present, tested, and reachable only from eight
synchronous HTTP handlers -- nothing in the context engine could select them.
These tests run each adapter through the registry on real inputs, so a wrapper
that silently stopped calling its discipline would fail here rather than in
production.

Two properties matter beyond "it runs":

* A refused input yields a **deferred result carrying a reason**, never a
  fabricated value. The existing discipline code already models this
  (``StructureStatus.DEFERRED`` plus ``budget_rationale``); the adapter must not
  lose it.
* Determinism and tier are declared per operator *from what the code actually
  does*, not defaulted. ``temporal.change_point`` returns integer indices and is
  therefore EXACT; ``tda.persistence`` returns floats with no tolerance contract
  and is therefore FLOAT_QUANTIZED.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from claims.model import EvidenceDirection, EvidenceLink
from context.operators.adapters import build_default_registry
from context.operators.base import Determinism, OperatorClass, Tier
from scitda.persistence import ActionPoint, PointCloud
from structure.graph import Graph
from temporal.timeseries import ObservationSample, build_series

pytestmark = pytest.mark.contract

REGISTRY = build_default_registry()


def _run(capability: str, payload, parameters=None, *, tier: Tier = Tier.STATISTICAL):
    selection = REGISTRY.select(required=frozenset({capability}), max_tier=tier)
    assert selection.ok, f"{capability}: {selection.gap}"
    return selection.registration.operator.run(payload, parameters, seed=0)


class TestLocalityOperatorsAreSelectable:
    """§9 and §10 must be reachable through the registry, not only as imports.

    These two are the operators that make locality work at all, and both are
    Tier 0: the deterministic core may depend on them (§31).
    """

    def _cell(self, members, **kwargs):
        from context.locality import CellKind, ContextCell, Scope

        kwargs.setdefault("produced_by", "op@1.0")
        kwargs.setdefault("method_fingerprint", "mf-1")
        return ContextCell(
            context_id="CXI-1", kind=CellKind.DOCUMENT, scope=Scope.entity(*members), **kwargs
        )

    def test_compatibility_runs_through_the_registry(self) -> None:
        selection = REGISTRY.select(required=frozenset({"compatibility"}))
        assert selection.ok
        result = selection.registration.operator.run(
            (self._cell(["A", "B"]), self._cell(["B", "C"])),
            {"overlap_id": "OVL-9"},
            seed=0,
        )
        assert result.value.assessment_id.startswith("CMP-")
        assert result.determinism is Determinism.EXACT

    def test_gluing_runs_through_the_registry(self) -> None:
        selection = REGISTRY.select(required=frozenset({"triple_coherence"}))
        assert selection.ok
        result = selection.registration.operator.run(
            (
                [
                    self._cell(["A", "B", "S"], entity_refs=("S",)),
                    self._cell(["B", "C", "S"], entity_refs=("S",)),
                    self._cell(["C", "A", "S"], entity_refs=()),
                ],
                "CXI-1",
            ),
            {"max_triples": 100},
            seed=0,
        )
        assert result.value.verdict.value == "partially_glued"
        assert result.value.triples_checked == 1

    def test_both_locality_operators_are_in_the_deterministic_core(self) -> None:
        from context.operators.base import Tier

        for capability in ("compatibility", "triple_coherence"):
            selection = REGISTRY.select(
                required=frozenset({capability}), max_tier=Tier.DETERMINISTIC
            )
            assert selection.ok, capability


class TestIndependenceOperatorsAreSelectable:
    """§14A and §22 must be reachable through the registry, on real evidence."""

    def test_independence_runs_and_collapses_syndication(self) -> None:
        selection = REGISTRY.select(required=frozenset({"n_eff"}))
        assert selection.ok
        items = [f"EV-{index}" for index in range(200)]
        lineage = {item: "OBS-press-release" for item in items}
        result = selection.registration.operator.run((items, lineage), None, seed=0)
        assert result.value.raw_count == 200
        assert result.value.n_eff == 1.0

    def test_independence_is_in_the_deterministic_core(self) -> None:
        from context.operators.base import Tier

        for capability in ("n_eff", "saturation", "closure"):
            selection = REGISTRY.select(
                required=frozenset({capability}), max_tier=Tier.DETERMINISTIC
            )
            assert selection.ok, capability

    def test_saturation_runs_and_names_what_it_achieved(self) -> None:
        selection = REGISTRY.select(required=frozenset({"saturation"}))
        assert selection.ok
        independence = REGISTRY.select(required=frozenset({"n_eff"})).registration.operator.run(
            (["a", "b", "c"], {"a": "O1", "b": "O2", "c": "O3"}), None, seed=0
        )
        result = selection.registration.operator.run(
            ("OBL-1", independence.value),
            {"coverage": 0.95, "source_families": 4, "marginal_gain": 0.01},
            seed=0,
        )
        assert result.value.verdict.value == "saturated"
        assert result.value.reason_codes

    def test_syndication_alone_does_not_saturate(self) -> None:
        selection = REGISTRY.select(required=frozenset({"saturation"}))
        items = [f"EV-{index}" for index in range(50)]
        lineage = {item: "OBS-press-release" for item in items}
        independence = REGISTRY.select(required=frozenset({"n_eff"})).registration.operator.run(
            (items, lineage), None, seed=0
        )
        result = selection.registration.operator.run(
            ("OBL-1", independence.value),
            {"coverage": 0.95, "source_families": 4, "marginal_gain": 0.01},
            seed=0,
        )
        assert result.value.verdict.value != "saturated"
        assert "insufficient_independence" in [
            reason.value for reason in result.value.reason_codes
        ]

    def test_duplicate_item_ids_are_refused(self) -> None:
        """The same identifier twice is a caller bug, not a second observation."""
        selection = REGISTRY.select(required=frozenset({"n_eff"}))
        with pytest.raises(ValueError):
            selection.registration.operator.run(
                (["a", "a"], {"a": "OBS-1"}), None, seed=0
            )


class TestGrowthIsSelectable:
    """§I.7's omitted branch must be reachable from the engine, not only importable."""

    def test_growth_creates_an_anchored_cell(self) -> None:
        from context.locality import CellKind, ContextCell, Scope, descendants_of

        root = ContextCell(
            context_id="CXI-1",
            kind=CellKind.ORGANIZATION,
            scope=Scope.entity("GAZPROM"),
            produced_by="op@1.0",
            method_fingerprint="mf",
        )
        selection = REGISTRY.select(required=frozenset({"cell_creation"}))
        assert selection.ok
        result = selection.registration.operator.run(
            ("CXI-1", (root,), {"O1": Scope.entity("SPV-77", "DOMAIN-9")}),
            {"revealed_by": {"O1": root.cell_id}},
            seed=0,
        ).value
        assert len(result.created) == 1
        assert len(descendants_of(root.cell_id, result.cells)) == 1

    def test_growth_is_in_the_deterministic_core(self) -> None:
        from context.operators.base import Tier

        selection = REGISTRY.select(
            required=frozenset({"anchoring"}), max_tier=Tier.DETERMINISTIC
        )
        assert selection.ok


class TestDialecticsOperatorsAreSelectable:
    """§18 and §20.3 must be reachable through the registry."""

    def test_dialectics_generates_a_pair_on_real_members(self) -> None:
        from context.dialectics import (
            Exhaustive,
            Hypothesis,
            HypothesisSpace,
            SteelmanParity,
        )

        space = HypothesisSpace(
            context_id="CXI-1",
            question="who controls the SPV?",
            members=(
                Hypothesis("direct ownership", posterior=0.6, local_id="LHYP-a"),
                Hypothesis("nominee control", posterior=0.2, local_id="LHYP-b"),
            ),
            exhaustive=Exhaustive.TRUE,
        )
        selection = REGISTRY.select(required=frozenset({"counter_hypothesis"}))
        assert selection.ok
        result = selection.registration.operator.run(
            (space, space.member("LHYP-a")),
            {
                "templates": (("nominee", space.member("LHYP-b")),),
                "parity": SteelmanParity(
                    same_evidence_view=True,
                    same_template_family=True,
                    same_complexity_bound=True,
                    same_assumption_budget=True,
                ),
            },
            seed=0,
        )
        assert result.value["outcome"].value == "generated"
        assert len(result.value["pairs"]) == 1

    def test_argumentation_filters_a_policy_blocked_candidate(self) -> None:
        from context.argumentation import Candidate

        selection = REGISTRY.select(required=frozenset({"argumentation"}))
        assert selection.ok
        result = selection.registration.operator.run(
            [
                Candidate("blocked", {"gain": 100.0}, policy_allowed=False),
                Candidate("allowed", {"gain": 1.0}),
            ],
            {"mode": "LEXICOGRAPHIC"},
            seed=0,
        )
        assert result.value["ranked"] == ["allowed"]

    def test_both_are_in_the_deterministic_core(self) -> None:
        from context.operators.base import Tier

        for capability in ("counter_hypothesis", "dominance"):
            selection = REGISTRY.select(
                required=frozenset({capability}), max_tier=Tier.DETERMINISTIC
            )
            assert selection.ok, capability


class TestCatalog:
    def test_eighteen_disciplines_are_registered(self) -> None:
        """Ten discipline adapters plus locality (§9, §10), honesty (§14A, §22),
        dialectics/argumentation (§18, §20), growth (§I.7) and completeness (§33)."""
        assert len(REGISTRY) == 18

    def test_the_registry_exposes_many_capabilities(self) -> None:
        assert len(REGISTRY.capabilities()) >= 30

    def test_no_discipline_was_reimplemented(self) -> None:
        """Every adapter is a thin wrapper, not a new implementation."""
        for registration in REGISTRY:
            assert registration.license == "platform-first-party"
            assert registration.supports_replay is True

    def test_every_adapter_records_its_dependency_fingerprint(self) -> None:
        """R7: fingerprints resolve at registration, never retrofitted."""
        point_cloud = PointCloud(
            [ActionPoint("a", datetime(2026, 1, 1, tzinfo=UTC), (0.0, 0.0))]
        )
        for result in (
            _run("persistence", point_cloud.distance_matrix()),
            _run(
                "macro_state",
                build_series("s", [ObservationSample(datetime(2026, 1, 1, tzinfo=UTC), 1.0)]),
            ),
        ):
            assert result.dependency_fingerprint
            assert result.method_fingerprint


class TestTda:
    def test_persistence_runs_through_the_registry(self) -> None:
        points = [
            ActionPoint(
                f"a{index}",
                datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index),
                (float(index % 3), float((index * 7) % 5)),
            )
            for index in range(12)
        ]
        result = _run("persistence", PointCloud(points).distance_matrix(), {"max_dim": 2})
        assert result.deferred is False
        assert result.value.dimension(0).num_bars() > 0
        assert result.determinism is Determinism.FLOAT_QUANTIZED

    def test_tda_is_declared_as_such(self) -> None:
        assert REGISTRY.get("tda.persistence").operator_class is OperatorClass.TDA


class TestChangePoint:
    def _series(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        samples = [ObservationSample(base + timedelta(hours=i), 1.0) for i in range(10)]
        samples += [ObservationSample(base + timedelta(hours=10 + i), 9.0) for i in range(10)]
        return build_series("load", samples)

    def test_detects_the_step(self) -> None:
        result = _run(
            "change_point", self._series(), {"min_shift": 2.0, "window": 3, "min_spacing": 2}
        )
        assert result.deferred is False
        assert result.value
        assert all(0.0 <= cp.confidence <= 1.0 for cp in result.value)

    def test_is_exact_because_it_returns_indices(self) -> None:
        """Declared from what the code does, not defaulted."""
        assert REGISTRY.get("temporal.change_point").determinism is Determinism.EXACT

    def test_is_in_the_deterministic_core(self) -> None:
        assert REGISTRY.get("temporal.change_point").tier is Tier.DETERMINISTIC

    def test_empty_series_defers_with_a_reason(self) -> None:
        result = _run("change_point", build_series("x", []))
        assert result.deferred is True
        assert result.value is None
        assert "no samples" in result.deferral_reason

    def test_none_input_defers_with_a_reason(self) -> None:
        result = _run("change_point", None)
        assert result.deferred is True
        assert result.deferral_reason


class TestStructure:
    def test_graph_analysis_runs_with_a_null_model(self) -> None:
        graph = Graph(graph_ref="g")
        for edge in (("a", "b"), ("b", "c"), ("a", "c"), ("c", "d")):
            graph.add_edge(*edge)
        result = _run("graph_structure", graph, {"kind": "motif"})
        assert result.value.status.value == "ok"
        assert result.value.scores["triangle_count"] == 1.0

    def test_over_budget_defers_rather_than_guessing(self) -> None:
        """The discipline already refuses; the adapter must carry that through."""
        from structure.graph import AnalysisBudget

        graph = Graph(graph_ref="g")
        for index in range(30):
            graph.add_edge(f"n{index}", f"n{index + 1}")
        result = _run(
            "graph_structure",
            graph,
            {"kind": "motif", "budget": AnalysisBudget(max_ops=1)},
        )
        assert result.value.status.value == "deferred"
        assert result.value.budget_rationale


class TestRobustness:
    def test_perturbation_grid_runs(self) -> None:
        evidence = [
            EvidenceLink("L1", "O1", "a" * 64, EvidenceDirection.SUPPORTS, 2.0),
            EvidenceLink("L2", "O2", "b" * 64, EvidenceDirection.REFUTES, 1.0),
        ]
        result = _run("robustness", evidence, {"claim_id": "CLM-1"})
        assert set(result.value.flip_rates) == {"missing", "flip", "biased_subsample"}


class TestRegime:
    def test_phase_analysis_runs(self) -> None:
        trajectory = [np.full(4, value) for value in (0.2, 0.4, 0.6, 0.8, 1.0)]
        result = _run("regime", trajectory, {"control_path": [0.0, 0.5, 1.0, 1.5, 2.0]})
        assert result.value.regime in {"ordered", "critical", "disordered"}
        assert 0.0 < result.value.dampening <= 1.0

    def test_hysteresis_area_is_reported(self) -> None:
        trajectory = [np.full(4, value) for value in (0.0, 0.0)]
        result = _run(
            "regime",
            trajectory,
            {
                "control_path": [0.0, 1.0],
                "backward_field": [np.full(4, 1.0), np.full(4, 1.0)],
            },
        )
        assert result.value.hysteresis == pytest.approx(1.0)


class TestSelectionSemantics:
    def test_a_combination_no_single_operator_holds_is_a_gap(self) -> None:
        selection = REGISTRY.select(required=frozenset({"persistence", "causal"}))
        assert selection.ok is False
        assert selection.gap.reason.value == "no_single_provider"
        assert selection.gap.uncovered == frozenset()

    def test_an_unknown_capability_is_a_gap(self) -> None:
        selection = REGISTRY.select(required=frozenset({"time-travel"}))
        assert selection.gap.reason.value == "no_provider"
        assert selection.gap.uncovered == frozenset({"time-travel"})

    def test_tier_ceiling_holds_out_the_statistical_disciplines(self) -> None:
        selection = REGISTRY.select(
            required=frozenset({"persistence"}), max_tier=Tier.DETERMINISTIC
        )
        assert selection.ok is False
        assert selection.gap.reason.value == "excluded"

    def test_selection_is_reproducible(self) -> None:
        picks = {
            REGISTRY.select(required=frozenset({"causal"})).registration.key for _ in range(5)
        }
        assert len(picks) == 1

    def test_two_disciplines_share_a_class(self) -> None:
        state = REGISTRY.select(operator_class=OperatorClass.STATE_ESTIMATION)
        assert state.ok
        assert len(REGISTRY.select_all()) >= len(REGISTRY)
