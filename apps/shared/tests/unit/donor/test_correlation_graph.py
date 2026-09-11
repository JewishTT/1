import json
import xml.etree.ElementTree as ET

from donor.correlation_graph import CorrelationGraph, CorrelationKind, CorrelationLink, make_node


def test_make_node_normalizes_url() -> None:
    node = make_node(CorrelationKind.URL, "https://Example.com/Path/", 0.9, observation="OBS-1")
    assert node.normalized == "example.com/path"


def test_make_node_normalizes_lowercase() -> None:
    node = make_node(CorrelationKind.DOMAIN, " ACME.example ", 0.5)
    assert node.normalized == "acme.example"
    assert node.observations == set()


def test_add_node_dedups_by_identity_and_merges(correlation_graph) -> None:
    first = correlation_graph.add_node(
        make_node(CorrelationKind.DOMAIN, "acme.example", 0.6, observation="OBS-1")
    )
    second = correlation_graph.add_node(
        make_node(CorrelationKind.DOMAIN, "ACME.example", 0.9, observation="OBS-2")
    )
    assert first is second
    assert first.observations == {"OBS-1", "OBS-2"}
    assert first.confidence == 0.9


def test_add_node_without_observation_is_separate(correlation_graph) -> None:
    a = correlation_graph.add_node(make_node(CorrelationKind.IP, "1.2.3.4", 0.5))
    b = correlation_graph.add_node(make_node(CorrelationKind.DOMAIN, "1.2.3.4", 0.5))
    assert a is not b
    assert len(correlation_graph._nodes) == 2


def test_add_link_discards_duplicates(correlation_graph) -> None:
    a = correlation_graph.add_node(make_node(CorrelationKind.PERSON, "Ann", 0.8))
    b = correlation_graph.add_node(make_node(CorrelationKind.EMAIL, "ann@x.example", 0.8))
    correlation_graph.add_link(
        CorrelationLink(a, b, kind="contact", observation="OBS-1")
    )
    correlation_graph.add_link(
        CorrelationLink(a, b, kind="contact", observation="OBS-1")
    )
    assert len(correlation_graph._links) == 1


def test_neighbors_both_directions() -> None:
    graph = CorrelationGraph()
    a = graph.add_node(make_node(CorrelationKind.PERSON, "Ann", 0.8, "OBS-1"))
    b = graph.add_node(make_node(CorrelationKind.EMAIL, "ann@x.example", 0.8, "OBS-1"))
    c = graph.add_node(make_node(CorrelationKind.USERNAME, "ann_x", 0.8, "OBS-2"))
    graph.add_link(CorrelationLink(a, b, kind="contact", observation="OBS-1"))
    graph.add_link(CorrelationLink(c, a, kind="alias", observation="OBS-2"))
    assert set(n.normalized for n in graph.neighbors(a)) == {"ann@x.example", "ann_x"}


def test_merge_absorbs_disjoint_content() -> None:
    left = CorrelationGraph()
    a = left.add_node(make_node(CorrelationKind.DOMAIN, "a.example", 0.7, "OBS-1"))
    right = CorrelationGraph()
    b = right.add_node(make_node(CorrelationKind.DOMAIN, "b.example", 0.7, "OBS-2"))
    right.add_link(CorrelationLink(b, a, kind="related", observation="OBS-2"))
    left.merge(right)
    assert len(left._nodes) == 2
    assert len(left._links) == 1


def test_to_dict_node_link_layout() -> None:
    graph = CorrelationGraph()
    a = graph.add_node(make_node(CorrelationKind.PERSON, "Ann", 0.8, "OBS-1"))
    b = graph.add_node(make_node(CorrelationKind.EMAIL, "ann@x.example", 0.9, "OBS-1"))
    graph.add_link(CorrelationLink(a, b, kind="contact", observation="OBS-1"))
    payload = graph.to_dict()
    assert len(payload["nodes"]) == 2
    assert len(payload["links"]) == 1
    link = payload["links"][0]
    assert payload["nodes"][link["source"]]["value"] == "Ann"
    assert payload["nodes"][link["target"]]["type"] == "email"
    assert "observations" in payload["nodes"][0]


def test_to_json_round_trips() -> None:
    graph = CorrelationGraph()
    a = graph.add_node(make_node(CorrelationKind.DOMAIN, "acme.example", 0.6))
    b = graph.add_node(make_node(CorrelationKind.URL, "http://acme.example/x", 0.6))
    graph.add_link(CorrelationLink(a, b, kind="owns", observation="OBS-1"))
    data = json.loads(graph.to_json())
    assert data["nodes"][0]["value"] == "acme.example"


def test_to_graphml_is_valid_xml_with_nodes_and_edges() -> None:
    graph = CorrelationGraph()
    a = graph.add_node(make_node(CorrelationKind.PERSON, "Ann", 0.8, "OBS-1"))
    b = graph.add_node(make_node(CorrelationKind.EMAIL, "ann@x.example", 0.8, "OBS-1"))
    graph.add_link(CorrelationLink(a, b, kind="contact", observation="OBS-1"))
    root = ET.fromstring(graph.to_graphml())
    ns = {"g": "http://graphml.graphdrawing.org/graphml"}
    nodes = root.findall(".//g:node", ns)
    edges = root.findall(".//g:edge", ns)
    assert len(nodes) == 2
    assert len(edges) == 1


def test_to_mermaid_sanitizes_and_links() -> None:
    graph = CorrelationGraph()
    a = graph.add_node(make_node(CorrelationKind.PERSON, "Ann | Ry", 0.8))
    b = graph.add_node(make_node(CorrelationKind.EMAIL, "ann@x.example", 0.8))
    graph.add_link(CorrelationLink(a, b, kind="contact", observation="OBS-1"))
    rendered = graph.to_mermaid()
    assert rendered.startswith("graph TD")
    assert "Ann | Ry" not in rendered
    assert "-->" in rendered


def test_summary_reports_counts() -> None:
    graph = CorrelationGraph()
    graph.add_node(make_node(CorrelationKind.DOMAIN, "a.example", 0.5))
    graph.add_node(make_node(CorrelationKind.EMAIL, "a@b.example", 0.5))
    summary = graph.summary()
    assert summary.startswith("Graph: 2 nodes")
    assert "1 domain" in summary
    assert "1 email" in summary


def test_node_equality_ignores_casing() -> None:
    a = make_node(CorrelationKind.DOMAIN, "ACME.example", 0.4)
    b = make_node(CorrelationKind.DOMAIN, "acme.example", 0.4)
    assert a in {b}
    assert a == b