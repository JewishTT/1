"""Guardrails for the Layer-0 public-document harvester.

These tests prove it extracts public professional metadata while redacting
private contact strings even when they appear in meta tags or JSON-LD.
"""

from __future__ import annotations

from zero.harvesters.public_document import PublicDocumentHarvester
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
