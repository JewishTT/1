"""Guardrails for the Layer-0 public-document harvester.

These tests prove it extracts public professional metadata while redacting
private contact strings even when they appear in meta tags or JSON-LD.
"""

from __future__ import annotations

from zero.harvesters.public_document import PublicDocumentHarvester, same_origin_public_links, MAX_INTERNAL_LINKS_PER_PAGE
from zero.harvesters.registry import HarvesterContext
from zero.harvesters.transport import DictTransport
from zero.type_detector import TypeDetector


def test_public_document_extracts_role_and_affiliation_without_private_contacts() -> None:
    url = "https://example.org/about"
    html = """
    <html><head>
      <title>Dr. Example — public office</title>
      <meta property="og:description" content="Email private@example.org or +1 202 555 0199">
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Dr. Example",
        "jobTitle": "Minister of Example Affairs",
        "worksFor": {"@type": "Organization", "name": "Example Ministry"},
        "email": "private@example.org",
        "telephone": "+1 202 555 0199"
      }
      </script>
    </head><body><h1>Dr. Example</h1></body></html>
    """
    seed = TypeDetector().detect(url)
    context = HarvesterContext(seed=seed, transport=DictTransport(bodies={url: html}))
    result = PublicDocumentHarvester().run(seed, context)

    by_kind = {candidate.kind: candidate.value for candidate in result.candidates}
    assert by_kind["public_name"] == "Dr. Example"
    assert by_kind["public_role"] == "Minister of Example Affairs"
    assert by_kind["public_affiliation"] == "Example Ministry"
    assert "private@example.org" not in " ".join(by_kind.values())
    assert "+1 202 555 0199" not in " ".join(by_kind.values())
    assert "email" not in by_kind
    assert "phone" not in by_kind


def test_public_document_refuses_to_invent_a_record_from_empty_transport() -> None:
    url = "https://example.org/empty"
    seed = TypeDetector().detect(url)
    context = HarvesterContext(seed=seed, transport=DictTransport())
    result = PublicDocumentHarvester().run(seed, context)
    assert result.candidates == ()
    assert result.notes



def test_jsonld_walker_is_iterative_and_bounded() -> None:
    from zero.harvesters.public_document import MAX_JSONLD_NODES, _jsonld_nodes

    nodes = [{"@type": "Person", "name": f"Person {i}"} for i in range(MAX_JSONLD_NODES + 10)]
    walked = list(_jsonld_nodes({"@graph": nodes}))
    assert len(walked) == MAX_JSONLD_NODES
    assert walked[0]["name"] == "Person 0"
    assert walked[-1]["name"] == f"Person {MAX_JSONLD_NODES - 1}"


def test_jsonld_walker_handles_deep_graph_wrappers_without_recursion() -> None:
    from zero.harvesters.public_document import _jsonld_nodes

    root: object = {"@type": "Person", "name": "Public Example"}
    for _ in range(1500):
        root = {"@graph": [root]}
    assert list(_jsonld_nodes(root))[0]["name"] == "Public Example"


def test_public_document_candidate_limit_matches_reserved_record_ceiling() -> None:
    from zero.harvesters.public_document import MAX_CANDIDATES_PER_PAGE

    assert MAX_CANDIDATES_PER_PAGE == 8


def test_public_document_only_emits_bounded_same_origin_links() -> None:
    base = "https://example.org/about"
    links = same_origin_public_links(base, [
        "/official",
        "https://example.org/leadership",
        "https://evil.example.net/collect",
        "http://example.org/insecure",
        "javascript:alert(1)",
        "https://example.org/private.pdf",
        "mailto:press@example.org",
    ])
    assert links == ("https://example.org/leadership", "https://example.org/official")
    assert len(same_origin_public_links(base, [f"/page-{i}" for i in range(10)])) == MAX_INTERNAL_LINKS_PER_PAGE


def test_public_document_exposes_same_origin_links_as_discovery_candidates() -> None:
    url = "https://example.org/about"
    html = '<html><body><a href="/official">Official profile</a><a href="https://outside.test/x">outside</a></body></html>'
    seed = TypeDetector().detect(url)
    result = PublicDocumentHarvester().run(
        seed,
        HarvesterContext(seed=seed, transport=DictTransport(bodies={url: html})),
    )
    links = [candidate for candidate in result.candidates if candidate.kind == "public_page_link"]
    assert [item.value for item in links] == ["https://example.org/official"]
    assert links[0].raw_fields["parent_url"] == url
