"""T019/T020/T021/T028: GraphStore direction, N-ary idempotency, edge-id identity.

Regression cover for the defects enumerated in research.md "Defects found in the
existing implementation" items 1, 2, 3 and 7: the N-ary idempotency guard that
never fired, ``neighbors`` that discarded direction, a ``GraphEdge`` with no
identifier, and an adjacency view built from ``str(GraphNode)``.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from graph.abstraction import (
    EdgeDirection,
    GraphEdge,
    GraphNode,
    HyperEdge,
    InMemoryGraphStore,
)
from graph.adjacency import adjacency_from_store

pytestmark = pytest.mark.unit

PROV = {"event_id": "e1", "observation_id": "o1"}


def _store(node_ids: tuple[str, ...], edges: tuple[GraphEdge, ...]) -> InMemoryGraphStore:
    store = InMemoryGraphStore()
    for node_id in node_ids:
        store.write_node(GraphNode(node_id=node_id, node_type="Entity"), PROV)
    for edge in edges:
        store.write_edge(edge, PROV)
    return store


def _bidirectional_pair(
    arity_mode: str, extra: Mapping[str, Any] | None = None
) -> InMemoryGraphStore:
    """A -> B and C -> A, both typed ``reports_to`` with the given arity mode."""
    props = {"arity_mode": arity_mode, **(extra or {})}
    return _store(
        ("a", "b", "c"),
        (
            GraphEdge(
                edge_id="REL-out",
                edge_type="reports_to",
                source="a",
                target="b",
                properties=dict(props),
            ),
            GraphEdge(
                edge_id="REL-in",
                edge_type="reports_to",
                source="c",
                target="a",
                properties=dict(props),
            ),
        ),
    )


class TestNeighborsDirection:
    """T019: direction is honoured and the default comes from the arity mode."""

    def test_out_returns_targets(self) -> None:
        store = _store(
            ("a", "b", "c"),
            (GraphEdge(edge_id="R1", edge_type="rel", source="a", target="b"),),
        )
        assert store.neighbors("a", "rel", direction="out") == ["b"]

    def test_in_returns_sources(self) -> None:
        store = _store(
            ("a", "b"),
            (GraphEdge(edge_id="R1", edge_type="rel", source="a", target="b"),),
        )
        assert store.neighbors("b", "rel", direction="in") == ["a"]

    def test_both_returns_the_union(self) -> None:
        store = _store(
            ("a", "b", "c"),
            (
                GraphEdge(edge_id="R1", edge_type="rel", source="a", target="b"),
                GraphEdge(edge_id="R2", edge_type="rel", source="c", target="a"),
            ),
        )
        assert store.neighbors("a", "rel", direction="both") == ["b", "c"]

    def test_default_for_directed_is_out(self) -> None:
        store = _bidirectional_pair("directed")
        assert store.neighbors("a", "reports_to") == ["b"]

    def test_a_windowed_directed_edge_still_defaults_to_out(self) -> None:
        # Temporality is ``TemporalSemantics``, not arity: a validity window on
        # the edge must not move the default off ``out`` and back to ``both``.
        store = _bidirectional_pair(
            "directed",
            {"valid_from": "2017-01-01T00:00:00+00:00", "valid_to": "2020-01-01T00:00:00+00:00"},
        )
        assert store.neighbors("a", "reports_to") == ["b"]

    def test_default_for_undirected_is_both(self) -> None:
        store = _bidirectional_pair("undirected")
        assert store.neighbors("a", "reports_to") == ["b", "c"]

    def test_default_for_nary_is_both(self) -> None:
        store = _bidirectional_pair("nary")
        assert store.neighbors("a", "reports_to") == ["b", "c"]

    def test_default_without_arity_mode_stays_both(self) -> None:
        store = _store(
            ("a", "b"),
            (GraphEdge(edge_id="R1", edge_type="rel", source="a", target="b"),),
        )
        assert store.neighbors("a", "rel") == ["b"]
        assert store.neighbors("b", "rel") == ["a"]

    def test_edge_type_filter_applies_before_direction(self) -> None:
        store = _store(
            ("a", "b", "c"),
            (
                GraphEdge(
                    edge_id="R1",
                    edge_type="rel",
                    source="a",
                    target="b",
                    properties={"arity_mode": "directed"},
                ),
                GraphEdge(edge_id="R2", edge_type="other", source="a", target="c"),
            ),
        )
        assert store.neighbors("a", "rel") == ["b"]
        assert store.neighbors("a", "rel", direction="both") == ["b"]
        assert store.neighbors("a", "other", direction="both") == ["c"]

    def test_enum_members_are_accepted(self) -> None:
        store = _bidirectional_pair("directed")
        assert store.neighbors("a", "reports_to", direction=EdgeDirection.IN) == ["c"]
        assert store.neighbors("a", "reports_to", direction=EdgeDirection.BOTH) == ["b", "c"]
        assert store.neighbors("a", "reports_to", direction=EdgeDirection.OUT) == ["b"]

    def test_unknown_direction_rejected(self) -> None:
        store = _bidirectional_pair("directed")
        with pytest.raises(ValueError):
            store.neighbors("a", "reports_to", direction="sideways")

    def test_legacy_two_positional_argument_form_still_works(self) -> None:
        store = _store(
            ("a", "b"),
            (GraphEdge(edge_id="R1", edge_type="rel", source="a", target="b"),),
        )
        assert store.neighbors("a") == ["b"]
        assert store.neighbors("a", "rel") == ["b"]

    def test_direction_is_keyword_only(self) -> None:
        store = _store(
            ("a", "b"),
            (GraphEdge(edge_id="R1", edge_type="rel", source="a", target="b"),),
        )
        with pytest.raises(TypeError):
            store.neighbors("a", "rel", "out")  # type: ignore[misc]


class TestHyperedgeIdempotency:
    """T020: the N-ary guard compares the id, not the object, against the mapping."""

    def test_writing_the_same_hyperedge_twice_leaves_the_count_unchanged(self) -> None:
        store = _store(("a", "b", "c"), ())
        edge = HyperEdge(edge_type="Employment", source=("a", "b"))
        first = store.write_hyperedge(edge, PROV)
        second = store.write_hyperedge(edge, PROV)
        assert first == second
        assert len(store.hyperedges()) == 1

    def test_equal_but_distinct_hyperedge_object_is_still_idempotent(self) -> None:
        store = _store(("a", "b", "c"), ())
        first = store.write_hyperedge(
            HyperEdge(edge_type="Employment", source=("a", "b"), properties={"rev": 1}), PROV
        )
        twin = HyperEdge(edge_type="Employment", source=("b", "a"), properties={"rev": 2})
        assert twin.edge_id == first  # same identity material
        store.write_hyperedge(twin, PROV)
        assert len(store.hyperedges()) == 1
        assert store.hyperedges()[0] is not twin  # guard fired: first write wins
        assert store.hyperedges()[0].properties == {"rev": 1}

    def test_different_content_increases_the_hyperedge_count(self) -> None:
        store = _store(("a", "b", "c"), ())
        store.write_hyperedge(HyperEdge(edge_type="Employment", source=("a", "b")), PROV)
        store.write_hyperedge(HyperEdge(edge_type="Employment", source=("a", "c")), PROV)
        assert len(store.hyperedges()) == 2
        assert [h.members for h in store.hyperedges()] == [("a", "b"), ("a", "c")]

    def test_membership_is_not_duplicated_by_the_second_write(self) -> None:
        store = _store(("a", "b"), ())
        edge = HyperEdge(edge_type="Employment", source=("a", "b"))
        store.write_hyperedge(edge, PROV)
        store.write_hyperedge(edge, PROV)
        assert [h.edge_id for h in store.member_hyperedges("a")] == [edge.edge_id]
        assert store.hyperedge(edge.edge_id) is not None

    def test_hyperedge_still_requires_provenance_and_known_members(self) -> None:
        from domain import ProjectionRebuildableError

        store = _store(("a",), ())
        edge = HyperEdge(edge_type="Employment", source=("a", "zz"))
        with pytest.raises(ValueError):
            store.write_hyperedge(edge, PROV)
        with pytest.raises(ProjectionRebuildableError):
            store.write_hyperedge(HyperEdge(edge_type="E", source=("a", "b")), {})


class TestGraphEdgeIdentity:
    """T021: identity is the caller-supplied edge_id, not the triple."""

    def test_edge_id_is_required(self) -> None:
        with pytest.raises(TypeError):
            GraphEdge(edge_type="rel", source="a", target="b")  # type: ignore[call-arg]

    def test_same_triple_different_edge_id_are_distinct_entries(self) -> None:
        first = GraphEdge(edge_id="REL-1", edge_type="rel", source="a", target="b")
        second = GraphEdge(edge_id="REL-2", edge_type="rel", source="a", target="b")
        assert first != second
        assert len({first, second}) == 2
        store = _store(("a", "b"), (first, second))
        assert len(store.edges()) == 2
        assert [e.edge_id for e in store.edges()] == ["REL-1", "REL-2"]

    def test_same_edge_id_with_different_properties_is_a_no_op(self) -> None:
        store = _store(
            ("a", "b"),
            (GraphEdge(edge_id="REL-1", edge_type="rel", source="a", target="b", properties={"n": 1}),),
        )
        store.write_edge(
            GraphEdge(
                edge_id="REL-1", edge_type="rel", source="a", target="b", properties={"n": 2}
            ),
            PROV,
        )
        assert len(store.edges()) == 1
        assert len(store._adj["a"]) == 1
        assert store.edges()[0].properties == {"n": 1}

    def test_identity_survives_property_reordering(self) -> None:
        store = _store(("a", "b"), ())
        store.write_edge(
            GraphEdge(
                edge_id="REL-1",
                edge_type="rel",
                source="a",
                target="b",
                properties={"a": 1, "b": 2},
            ),
            PROV,
        )
        store.write_edge(
            GraphEdge(
                edge_id="REL-1",
                edge_type="rel",
                source="a",
                target="b",
                properties={"b": 2, "a": 1},
            ),
            PROV,
        )
        assert len(store.edges()) == 1

    def test_hash_and_eq_agree_on_edge_id(self) -> None:
        base = GraphEdge(
            edge_id="REL-1", edge_type="rel", source="a", target="b", properties={"n": 1}
        )
        same = GraphEdge(
            edge_id="REL-1", edge_type="rel", source="a", target="b", properties={"n": 99}
        )
        assert hash(base) == hash(same)
        assert base == same
        assert hash(base) == hash(("REL-1",))
        assert base != "REL-1"

    def test_edges_are_sorted_by_edge_id(self) -> None:
        store = _store(
            ("a", "b", "c"),
            (
                GraphEdge(edge_id="REL-3", edge_type="rel", source="a", target="b"),
                GraphEdge(edge_id="REL-1", edge_type="rel", source="a", target="c"),
            ),
        )
        assert [e.edge_id for e in store.edges()] == ["REL-1", "REL-3"]


class TestAdjacencyFromStore:
    """T028: node ids come from ``node_id``, not from ``str(GraphNode)``."""

    def test_view_is_built_from_node_ids(self) -> None:
        store = _store(
            ("n1", "n2", "n3"),
            (
                GraphEdge(
                    edge_id="R1",
                    edge_type="rel",
                    source="n1",
                    target="n2",
                    properties={"arity_mode": "directed"},
                ),
                GraphEdge(
                    edge_id="R2",
                    edge_type="rel",
                    source="n1",
                    target="n3",
                    properties={"arity_mode": "directed"},
                ),
            ),
        )
        view = adjacency_from_store(store, provenance=PROV)
        assert view.nodes == ["n1", "n2", "n3"]
        assert [(e.source, e.target) for e in view.edges] == [("n1", "n2"), ("n1", "n3")]

    def test_undirected_edge_is_reachable_from_both_sides(self) -> None:
        store = _store(
            ("a", "b"),
            (
                GraphEdge(
                    edge_id="R1",
                    edge_type="rel",
                    source="a",
                    target="b",
                    properties={"arity_mode": "undirected"},
                ),
            ),
        )
        view = adjacency_from_store(store, edge_type="rel", provenance=PROV)
        assert [(e.source, e.target) for e in view.edges] == [("a", "b"), ("b", "a")]

    def test_repeated_neighbours_are_emitted_once(self) -> None:
        class DuplicatingStore:
            def nodes(self) -> list[GraphNode]:
                return [GraphNode(node_id="a", node_type="Entity")]

            def neighbors(self, node_id, edge_type=None):
                return ["b", "b", "b"]

        view = adjacency_from_store(DuplicatingStore(), provenance=PROV)
        assert view.nodes == ["a", "b"]
        assert [(e.source, e.target) for e in view.edges] == [("a", "b")]

    def test_explicit_node_ids_restrict_the_view(self) -> None:
        store = _store(
            ("a", "b", "c"),
            (
                GraphEdge(
                    edge_id="R1",
                    edge_type="rel",
                    source="a",
                    target="b",
                    properties={"arity_mode": "directed"},
                ),
            ),
        )
        view = adjacency_from_store(store, node_ids=["a", "b"], provenance=PROV)
        assert view.nodes == ["a", "b"]
        assert [(e.source, e.target) for e in view.edges] == [("a", "b")]
