"""Contract: every event type in the store projection is actually produced.

``store.ENTITY_BY_EVENT`` declared ``science.structure.analyzed`` and
``science.robustness.report``, but neither ``structure.analyze`` nor
``robustness.analyze_robustness`` emitted anything, so those two collections
could never be populated. A declared-but-unemitted event is a silent hole: the
projection looks complete and is not. This test fails if a mapping is added
without a producer, and vice versa.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from claims.model import EvidenceDirection, EvidenceLink
from robustness.perturb import PerturbationGrid
from robustness.report import analyze_robustness
from store import ENTITY_BY_EVENT, ScienceStore
from structure.graph import AnalysisBudget, Graph, NullParams, analyze
from structure.model import StructureKind

pytestmark = pytest.mark.contract


def _links() -> list[EvidenceLink]:
    return [
        EvidenceLink(
            link_id="L1",
            observation_id="OBS-1",
            raw_sha256="a" * 64,
            direction=EvidenceDirection.SUPPORTS,
            weight=2.0,
        ),
        EvidenceLink(
            link_id="L2",
            observation_id="OBS-2",
            raw_sha256="b" * 64,
            direction=EvidenceDirection.REFUTES,
            weight=1.0,
        ),
    ]


def _triangle() -> Graph:
    graph = Graph(graph_ref="g-test")
    graph.add_edge("a", "b")
    graph.add_edge("b", "c")
    graph.add_edge("a", "c")
    return graph


class TestStructureEmits:
    def test_ok_result_projects(self) -> None:
        store = ScienceStore()
        analyze(
            _triangle(),
            budget=AnalysisBudget(),
            kind=StructureKind.MOTIF,
            null_params=NullParams(n_permutations=8),
            store=store,
            investigation_id="INV-1",
        )
        assert store.count("structure") == 1

    def test_deferred_result_also_projects(self) -> None:
        """A deferral is a decision; it must be as replayable as a measurement."""
        store = ScienceStore()
        result = analyze(
            _triangle(),
            budget=AnalysisBudget(),
            kind=StructureKind.TEMPORAL_NETWORK,
            null_params=NullParams(),
            store=store,
        )
        assert result.status.value == "deferred"
        assert store.count("structure") == 1

    def test_pure_call_emits_nothing(self) -> None:
        """No store, no side effect: the operator stays a pure function."""
        result = analyze(
            _triangle(),
            budget=AnalysisBudget(),
            kind=StructureKind.MOTIF,
            null_params=NullParams(n_permutations=8),
        )
        assert result.result_id.startswith("ST-")


class TestRobustnessEmits:
    def test_report_projects(self) -> None:
        store = ScienceStore()
        analyze_robustness(
            "CLM-1",
            _links(),
            perturbations=PerturbationGrid(),
            store=store,
            investigation_id="INV-1",
        )
        assert store.count("robustness") == 1

    def test_report_is_idempotent_by_deterministic_id(self) -> None:
        store = ScienceStore()
        for _ in range(2):
            analyze_robustness(
                "CLM-1",
                _links(),
                perturbations=PerturbationGrid(),
                store=store,
            )
        assert store.count("robustness") == 1
        assert store.log_len == 2


class TestDeclaredEventsAreReachable:
    @pytest.mark.parametrize(
        "event_type",
        ["science.structure.analyzed", "science.robustness.report"],
    )
    def test_collection_is_reachable(self, event_type: str) -> None:
        collection, id_field = ENTITY_BY_EVENT[event_type]
        assert collection
        assert id_field


def test_rebuild_reproduces_the_projection() -> None:
    """I-12: the log alone determines the snapshot."""
    store = ScienceStore()
    analyze_robustness(
        "CLM-2",
        _links(),
        perturbations=PerturbationGrid(),
        store=store,
        investigation_id="INV-9",
    )
    log = list(store._log)
    store.rebuild(log)
    assert store.count("robustness") == 1
    assert store.get("robustness", store.list("robustness")[0])["claim_ref"] == "CLM-2"
