"""T022: the Neo4j adapter MERGEs a relation on its id and carries the payload.

The adapter is exercised through a recording fake driver, reusing the shape of
the fake used by ``apps/projection/tests/test_projection.py`` so that no live
Neo4j is required and the emitted Cypher is asserted directly (SC-013).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Self

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from graph.abstraction import GraphEdge, GraphNode, HyperEdge
from graph.neo4j import Neo4jGraphStore

pytestmark = pytest.mark.unit

PROV = {"event_id": "e1", "observation_id": "o1"}
CYRILLIC = "связан"  # not an ASCII identifier


class FakeResult:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = list(rows or [])

    def data(self) -> list[dict]:
        return list(self._rows)


class FakeSession:
    """Records every (cypher, params) pair the adapter emits."""

    def __init__(self, log: list[tuple[str, dict]]) -> None:
        self._log = log

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def run(self, cypher: str, **params: object) -> FakeResult:
        self._log.append((cypher, params))
        return FakeResult()


class FakeDriver:
    def __init__(self, log: list[tuple[str, dict]] | None = None) -> None:
        self.log: list[tuple[str, dict]] = [] if log is None else log

    def session(self) -> FakeSession:
        return FakeSession(self.log)

    @property
    def queries(self) -> list[str]:
        return [cypher for cypher, _ in self.log]

    @property
    def params(self) -> list[dict]:
        return [params for _, params in self.log]


@pytest.fixture
def store() -> Neo4jGraphStore:
    return Neo4jGraphStore(driver=FakeDriver())


def _driver_of(store: Neo4jGraphStore) -> FakeDriver:
    assert isinstance(store._driver, FakeDriver)
    return store._driver


class TestWriteEdge:
    def test_emitted_cypher_merges_on_the_relation_id(self, store: Neo4jGraphStore) -> None:
        edge = GraphEdge(
            edge_id="REL-0001",
            edge_type="resolves_to",
            source="a",
            target="b",
            properties={"context_ref": "CX-1", "confidence": 0.5},
        )
        store.write_edge(edge, PROV)
        driver = _driver_of(store)
        assert len(driver.log) == 1
        cypher, params = driver.log[0]
        compact = " ".join(cypher.split())
        assert compact == (
            "MATCH (a {node_id:$source}), (b {node_id:$target}) "
            "MERGE (a)-[r:resolves_to {rel_id:$rel_id}]->(b) "
            "SET r += $props "
            "RETURN r"
        )
        assert params["source"] == "a"
        assert params["target"] == "b"

    def test_relation_id_is_a_parameter(self, store: Neo4jGraphStore) -> None:
        store.write_edge(
            GraphEdge(edge_id="REL-0002", edge_type="rel", source="a", target="b"), PROV
        )
        _, params = _driver_of(store).log[0]
        assert params["rel_id"] == "REL-0002"

    def test_full_property_payload_is_carried(self, store: Neo4jGraphStore) -> None:
        payload = {
            "context_ref": "CX-abc",
            "logical_relation_id": "RELATION-abc",
            "confidence": 0.91,
            "status": "active",
        }
        store.write_edge(
            GraphEdge(
                edge_id="REL-0003",
                edge_type="rel",
                source="a",
                target="b",
                properties=dict(payload),
            ),
            PROV,
        )
        cypher, params = _driver_of(store).log[0]
        assert "SET r += $props" in " ".join(cypher.split())
        assert params["props"] == payload

    def test_rewrite_of_the_same_relation_id_is_idempotent(self, store: Neo4jGraphStore) -> None:
        edge = GraphEdge(
            edge_id="REL-0004",
            edge_type="rel",
            source="a",
            target="b",
            properties={"n": 1},
        )
        store.write_edge(edge, PROV)
        first = list(_driver_of(store).log)
        store.write_edge(edge, PROV)
        second = list(_driver_of(store).log)[1:]
        assert first == second
        assert first[0][0].count("MERGE") == 1
        assert "rel_id:$rel_id" in " ".join(first[0][0].split())

    def test_two_relations_of_the_same_type_between_a_pair_stay_distinct(
        self, store: Neo4jGraphStore
    ) -> None:
        driver = _driver_of(store)
        store.write_edge(
            GraphEdge(edge_id="REL-0005", edge_type="rel", source="a", target="b"), PROV
        )
        store.write_edge(
            GraphEdge(edge_id="REL-0006", edge_type="rel", source="a", target="b"), PROV
        )
        ids = [params["rel_id"] for params in driver.params]
        assert ids == ["REL-0005", "REL-0006"]
        assert " ".join(driver.queries[0].split()) == " ".join(driver.queries[1].split())

    def test_write_requires_provenance(self, store: Neo4jGraphStore) -> None:
        from domain import ProjectionRebuildableError

        with pytest.raises(ProjectionRebuildableError):
            store.write_edge(
                GraphEdge(edge_id="REL-0007", edge_type="rel", source="a", target="b"), {}
            )
        assert _driver_of(store).log == []


class TestWriteHyperedge:
    def test_reified_node_sets_rel_id(self, store: Neo4jGraphStore) -> None:
        edge = HyperEdge(
            edge_type="Employment",
            source=("p1", "o1"),
            properties={"tenant_id": "t-1", "valid_from": "2024-01-01"},
        )
        assert store.write_hyperedge(edge, PROV) == edge.edge_id
        driver = _driver_of(store)
        cypher, params = driver.log[0]
        compact = " ".join(cypher.split())
        assert "MERGE (h:HyperEdge {" in compact
        assert "rel_id: $edge_id" in compact
        assert "edge_id: $edge_id" in compact
        assert params["edge_id"] == edge.edge_id
        assert params["props"] == edge.properties

    def test_reification_is_idempotent_on_the_id(self, store: Neo4jGraphStore) -> None:
        edge = HyperEdge(edge_type="Employment", source=("p1", "o1"))
        store.write_hyperedge(edge, PROV)
        first = list(_driver_of(store).log)
        store.write_hyperedge(edge, PROV)
        assert list(_driver_of(store).log)[len(first) :] == first
        assert len(first) == 1 + len(edge.members)

    def test_participation_edges_remain(self, store: Neo4jGraphStore) -> None:
        edge = HyperEdge(edge_type="Employment", source=("p1", "o1"))
        store.write_hyperedge(edge, PROV)
        participation = _driver_of(store).queries[1:]
        assert len(participation) == 2
        assert all("PART_OF_Employment" in q for q in participation)


class TestSanitize:
    def test_rejects_a_cyrillic_relation_type(self) -> None:
        safe = Neo4jGraphStore._sanitize(CYRILLIC)
        assert safe.isascii()
        assert safe == "_"  # no ASCII content left, and a legal (if empty) label

    def test_rejects_an_embedded_non_ascii_character(self) -> None:
        safe = Neo4jGraphStore._sanitize("rel" + CYRILLIC + "ates")
        assert safe.isascii()
        assert safe == "rel_ates"

    def test_keeps_ascii_identifiers_untouched(self) -> None:
        assert Neo4jGraphStore._sanitize("resolves_to") == "resolves_to"
        assert Neo4jGraphStore._sanitize("7xx") == "_7xx"
        assert Neo4jGraphStore._sanitize("Employment") == "Employment"


class TestWriteNode:
    def test_node_merge_is_unchanged(self, store: Neo4jGraphStore) -> None:
        store.write_node(GraphNode("a", "Entity", {"label": "acme"}), PROV)
        cypher, params = _driver_of(store).log[0]
        assert " ".join(cypher.split()) == (
            "MERGE (n:Entity {node_id: $node_id}) ON CREATE SET n += $props RETURN n"
        )
        assert params == {"node_id": "a", "props": {"label": "acme"}}
