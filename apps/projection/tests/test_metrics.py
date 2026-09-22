"""Unit tests: network metrics, communities, hypergraphs, temporal paths (T058/T059/T060)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graph.adjacency import build_adjacency
from metrics.community import label_propagation, modularity, normalized_mutual_information
from metrics.hypergraph_metrics import hypergraph_from_observations
from metrics.network_measures import network_measures
from metrics.temporal_paths import TemporalGraph


def _clique_view(node_count: int) -> object:
    edges = [
        (f"n{i}", f"n{j}", "rel")
        for i in range(node_count)
        for j in range(i + 1, node_count)
    ]
    return build_adjacency(edges)


def _ring_view(node_count: int = 6) -> object:
    edges = [(f"n{i}", f"n{(i + 1) % node_count}", "rel") for i in range(node_count)]
    return build_adjacency(edges)


class TestNetworkMeasures:
    def test_clique_density_and_clustering(self):
        view = _clique_view(5)
        measures = network_measures(view)
        assert measures.n_nodes == 5
        assert measures.n_edges == 10
        assert measures.density == 1.0
        assert measures.avg_clustering == 1.0
        assert measures.transitivity == 1.0
        assert measures.avg_shortest_path == 1.0

    def test_ring_no_triangles(self):
        measures = network_measures(_ring_view(10))
        assert measures.avg_clustering == 0.0
        assert measures.transitivity == 0.0
        assert measures.avg_degree == 2.0

    def test_degree_gini_zero_on_regular(self):
        gini = network_measures(_ring_view(6)).degree_gini
        assert gini == 0.0

    def test_power_law_on_star(self):
        edges = [("center", f"leaf{i}", "rel") for i in range(10)]
        measures = network_measures(build_adjacency(edges))
        assert measures.power_law_alpha > 1.0
        assert measures.max_degree == 10

    def test_as_dict_shape(self):
        data = network_measures(_ring_view(4)).as_dict()
        assert "density" in data and "small_world_sigma" in data


class TestCommunity:
    def test_two_cliques_isolated(self):
        edges = [
            (f"a{i}", f"a{(i + 1) % 4}", "c1") for i in range(4)
        ] + [(f"b{i}", f"b{(i + 1) % 4}", "c2") for i in range(4)]
        view = build_adjacency(edges)
        partition = label_propagation(view)
        a_labels = {partition[f"a{i}"] for i in range(4)}
        b_labels = {partition[f"b{i}"] for i in range(4)}
        assert len(a_labels) == 1 and len(b_labels) == 1
        assert a_labels != b_labels

    def test_modularity_at_most_one(self):
        view = _clique_view(6)
        partition = label_propagation(view)
        q = modularity(partition, view)
        assert -1.0 <= q <= 1.0

    def test_nmi_identical_is_one(self):
        partition = {"a": "x", "b": "y", "c": "x"}
        assert normalized_mutual_information(partition, partition) == 1.0

    def test_nmi_disjoint_is_zero(self):
        left = {"a": "1", "b": "1"}
        right = {"a": "a", "b": "b"}
        assert normalized_mutual_information(left, right) == 0.0

    def test_deterministic_across_runs(self):
        view = _clique_view(7)
        assert label_propagation(view) == label_propagation(view)


class TestHypergraph:
    def test_from_observations_drops_low_degree(self):
        observations = {
            "o1": ["A", "B", "C"],
            "o2": ["A", "B"],
            "o3": ["C", "D"],
        }
        hypergraph = hypergraph_from_observations(observations, min_degree=2)
        assert "D" not in hypergraph.nodes
        assert hypergraph.order() == 3
        assert hypergraph.num_edges() == 3

    def test_co_membership(self):
        hypergraph = hypergraph_from_observations({"o1": ["A", "B"], "o2": ["A", "B", "C"]})
        assert hypergraph.co_membership("A", "B") == 2
        assert hypergraph.co_membership("A", "C") == 1

    def test_jaccard(self):
        hypergraph = hypergraph_from_observations({"o1": [1, 2, 3], "o2": [2, 3, 4]})
        assert hypergraph.jaccard("o1", "o2") == 0.5

    def test_edge_sizes_and_incidence(self):
        hypergraph = hypergraph_from_observations({"o1": ["A", "B", "C"]})
        assert hypergraph.edge_sizes() == {3: 1}
        assert hypergraph.incidence_density() == 1.0


class TestTemporal:
    @staticmethod
    def _graph() -> TemporalGraph:
        graph = TemporalGraph()
        for source, target, t, edge_id in [
            ("a", "b", 1, "e1"),
            ("b", "c", 1, "e2"),
            ("a", "c", 3, "e3"),
            ("b", "d", 4, "e4"),
            ("c", "d", 5, "e5"),
        ]:
            graph.add_edge(source, target, t, edge_id=edge_id)
        return graph

    def test_earliest_arrival(self):
        arrival = self._graph().earliest_arrival("a")
        assert arrival["a"] == 0.0
        assert arrival["c"] == 1.0
        assert arrival["d"] == 4.0

    def test_equal_time_chain(self):
        graph = TemporalGraph()
        graph.add_edge("x", "b", 5, edge_id="e1")
        graph.add_edge("b", "c", 5, edge_id="e2")
        graph.add_edge("a", "x", 4, edge_id="e3")
        arrival = graph.earliest_arrival("a")
        assert arrival["c"] == 5.0

    def test_journey(self):
        edges, arrival = self._graph().journey("a", "d")
        assert [edge.edge_id for edge in edges] == ["e1", "e4"]
        assert arrival == 4.0

    def test_unreachable_is_infinite(self):
        graph = TemporalGraph()
        graph.add_edge("a", "b", 1)
        graph.add_edge("c", "d", 2)
        assert graph.journey("a", "d")[1] == float("inf")

    def test_temporal_motifs_deterministic(self):
        counts = self._graph().count_temporal_motifs()
        assert counts == self._graph().count_temporal_motifs()
        assert set(counts) == {"out_star", "in_star", "relay"}

    def test_distance_matrix_symmetric_sources(self):
        matrix = self._graph().temporal_distance_matrix()
        assert matrix["a"]["d"] == 4.0
        assert matrix["d"]["a"] == float("inf")  # no backward journeys

    def test_timeline_ordered(self):
        timeline = self._graph().timeline()
        assert timeline[0][0] == 1.0
        assert timeline[-1][0] == 5.0