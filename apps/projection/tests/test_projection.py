"""Unit tests for projection graph/search/analytics/TDA (T038-T043)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from analytics.projector import AnalyticsProjector
from graph.abstraction import GraphEdge, GraphNode, InMemoryGraphStore
from graph.neo4j import Neo4jGraphStore
from graph.snapshot import RebuildableGraphStore
from search.index import InMemorySearchIndex
from search.projector import SearchEvent, SearchProjector
from tda.features import TDAFeatureBuilder
from tda.pipeline import MemoryBudgetExceeded, TDAPipeline


class NumpyPersistence:
    """Test provider: no gudhi needed — returns scaled distances as diagrams."""

    def compute(self, distance_matrix, dimension):
        n = distance_matrix.shape[0]
        diag: dict[int, list[tuple[float, float]]] = {}
        # H0: one component born 0, others essentially 0.5 offset
        pairs = [(0.0, 0.0)] + [(0.1 * i, None) for i in range(1, min(n, dimension + 2))]
        diag[0] = [(b, float(d) if d is not None else float("inf")) for b, d in pairs]
        diag[1] = [(0.3, None)] if n >= 3 else []
        return diag


class TestGraph:
    def test_write_double_proves_imp_detection_single_edge(self):
        store = InMemoryGraphStore()
        prov = {"event_id": "e1", "observation_id": "o1"}
        node = GraphNode(node_id="n1", node_type="Entity")
        store.write_node(node, prov)
        store.write_node(node, prov)  # idempotent (I-11)
        assert len(store.nodes()) == 1

    def test_write_requires_provenance(self):
        from domain import ProjectionRebuildableError

        store = InMemoryGraphStore()
        try:
            store.write_node(GraphNode(node_id="n1", node_type="Entity"), {})
            assert False, "expected ProjectionRebuildableError"
        except ProjectionRebuildableError:
            pass

    def test_node_type_immutable(self):
        store = InMemoryGraphStore()
        store.write_node(GraphNode(node_id="n1", node_type="Entity"), {"event_id": "e", "observation_id": "o"})
        try:
            store.write_node(GraphNode(node_id="n1", node_type="Candidate"), {"event_id": "e", "observation_id": "o"})
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_edge_neighbors(self):
        store = InMemoryGraphStore()
        prov = {"event_id": "e", "observation_id": "o"}
        store.write_node(GraphNode("a", "Entity"), prov)
        store.write_node(GraphNode("b", "Entity"), prov)
        store.write_edge(GraphEdge("resolves_to", "a", "b"), prov)
        assert store.neighbors("a") == ["b"]
        assert store.neighbors("a", "resolves_to") == ["b"]


class TestSnapshot:
    def test_rebuild_reproduces(self):
        wrapped = RebuildableGraphStore()
        prov = {"event_id": "e", "observation_id": "o1"}
        wrapped.write_node(GraphNode("a", "Entity"), prov)
        wrapped.write_node(GraphNode("b", "Entity"), prov)
        wrapped.write_edge(GraphEdge("resolves_to", "a", "b"), prov)
        snap = wrapped.snapshot()
        assert snap.edge_count == 1 and snap.node_count == 2 and snap.last_offset == 3
        fresh = wrapped.rebuild(snap.projection_id)
        assert sorted(fresh.neighbors("a")) == ["b"]
        assert fresh.node("b") is not None


class TestSearchProjector:
    def test_six_kinds_index(self):
        idx = InMemorySearchIndex()
        projector = SearchProjector(idx)
        for kind in ["observation", "document", "mention", "candidate", "entity", "assertion", "finding"]:
            projector.project(SearchEvent(kind=kind, doc_id=f"id-{kind}", body={"text": f"stuxnet {kind}"}))
        assert len(idx.all("entities")) == 1
        assert idx.all("observations") == ["id-observation"]

    def test_search_filters_by_index(self):
        idx = InMemorySearchIndex()
        projector = SearchProjector(idx)
        projector.project(SearchEvent(kind="entity", doc_id="e1", body={"text": "financial"}))
        projector.project(SearchEvent(kind="finding", doc_id="f1", body={"text": "financial"}))
        assert projector.search("entity", "financial") == ["e1"]
        assert projector.search("finding", "financial") == ["f1"]

    def test_rebuild_reprojects_all(self):
        idx = InMemorySearchIndex()
        projector = SearchProjector(idx)
        projector.project(SearchEvent(kind="candidate", doc_id="c1", body={"text": "alias based"}))
        projector.rebuild()
        assert idx.all("candidates") == ["c1"]
        assert projector.search("candidate", "alias") == ["c1"]

    def test_unknown_kind_rejected(self):
        idx = InMemorySearchIndex()
        projector = SearchProjector(idx)
        try:
            projector.project(SearchEvent(kind="nonsense", doc_id="x", body={}))
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestAnalytics:
    def test_idempotent_and_aggregates(self):
        projector = AnalyticsProjector()
        prov = {"event_id": "e1", "observation_id": "o1"}
        projector.project_observation(
            projection_key="obs:1", source_id="src-a", event_type="observation.created",
            changed=True, size_bytes=1024, cost_ms=12.0, provenance=prov,
        )
        projector.project_observation(
            projection_key="obs:1", source_id="src-a", event_type="observation.created",
            changed=True, size_bytes=1024, cost_ms=12.0, provenance=prov,
        )
        store = projector.store
        assert store.count() == 1  # idempotent on (projection_key, source)
        agg = store.per_source("src-a")
        assert agg.observations == 1 and agg.bytes_received == 1024

    def test_rebuild_from_log(self):
        projector = AnalyticsProjector()
        projector.project_observation(
            projection_key="obs:1", source_id="s", event_type="observation.created",
            size_bytes=7, provenance={"event_id": "e", "observation_id": "o"},
        )
        fresh = projector.rebuild()
        assert fresh.count() == 1
        assert fresh.per_source("s").bytes_received == 7


class TestTDA:
    def test_pipeline_runs_with_provider(self):
        pipeline = TDAPipeline(provider=NumpyPersistence(), dimension=2)
        result = pipeline.run(["a", "b", "c"], {
            "a": np.array([1.0, 0.0]),
            "b": np.array([0.9, 0.1]),
            "c": np.array([0.0, 1.0]),
        })
        assert result["dimension"] == 2
        assert 0 in result["diagrams"]

    def test_memory_budget_guard(self):
        big = [f"n{i}" for i in range(400)]
        pipeline = TDAPipeline(provider=NumpyPersistence(), max_nodes=256)
        try:
            pipeline.run(big, {n: np.array([1.0]) for n in big})
            assert False, "expected MemoryBudgetExceeded"
        except MemoryBudgetExceeded:
            pass

    def test_multiparameter_not_supported(self):
        pipeline = TDAPipeline(provider=NumpyPersistence())
        try:
            pipeline.run_multiparameter()
            assert False, "expected NotImplementedError"
        except NotImplementedError:
            pass


class TestTDAFeatures:
    def test_materialize_structural_only(self):
        builder = TDAFeatureBuilder()
        features = builder.materialize({"nodes": ["a", "b", "c"], "diagrams": {0: [(0.0, None)], 1: [(0.3, None)]}})
        assert len(features) == 2
        assert all(f.structural_only for f in features)  # I-6
        assert features[0].persistence == float("inf")

    def test_emits_tda_completed(self):
        events: list[tuple] = []
        builder = TDAFeatureBuilder(emitter=lambda et, payload: events.append((et, payload)))
        builder.materialize({"nodes": ["a", "b"], "diagrams": {0: [(0.0, 1.0)]}})
        assert events and events[0][0] == "tda.completed"
        assert events[0][1]["structural_only"] is True


class TestNeo4jAdapter:
    def test_inner_sanitize(self):
        class FakeDriver:
            def session(self):
                raise AssertionError("sanitize must not hit driver")

        store = Neo4jGraphStore.__new__(Neo4jGraphStore)  # avoid __init__ requirement
        store._driver = FakeDriver()
        # Build with chr() so shell quoting can never mangle underscores.
        name = "assertion_references" + chr(45) + "observation" + chr(33)  # -, !
        assert store._sanitize(name) == "assertion_references_observation"
        assert store._sanitize("7xx") == "_7xx"