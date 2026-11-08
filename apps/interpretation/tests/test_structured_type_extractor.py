from __future__ import annotations

from extractors.types import StructuredTypeSignalExtractor


def test_jsonld_schema_person_becomes_type_signal_not_assertion():
    source = '''
    <script type="application/ld+json">
    {"@context":"https://schema.org","@graph":[
      {"@type":"Person","name":"Ada Lovelace"}
    ]}
    </script>
    '''
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-1",
        mention_id_for_surface={"Ada Lovelace": "MN-ada"},
    )
    assert len(report.signals) == 1
    signal = report.signals[0]
    assert signal.source_vocab == "schema.org"
    assert signal.surface == "Person"
    assert signal.mention_ref == "MN-ada"
    assert signal.structural_path == ("jsonld[0]", "@graph", "0", "@type")
    assert signal.observation_refs == ("OBS-1",)
    assert report.refusals == ()


def test_jsonld_unresolved_mention_is_a_typed_refusal():
    source = '<script type="application/ld+json">{"@type":"Person","name":"Unknown Name"}</script>'
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-2",
        mention_id_for_surface={},
    )
    assert report.signals == ()
    assert report.refusals[0].code == "mention_unresolved"


def test_opengraph_page_type_is_not_misattached_to_a_person_mention():
    source = '''
    <meta property="og:type" content="profile">
    <meta property="og:title" content="Ada Lovelace">
    '''
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-3",
        mention_id_for_surface={"Ada Lovelace": "MN-ada"},
    )
    assert report.signals == ()
    assert report.refusals[0].code == "document_type_requires_document_mention"


def test_inherited_schema_context_applies_to_nested_graph_items():
    source = '''
    <script type="application/ld+json">
    {"@context":{"@vocab":"https://schema.org/"},"@graph":[
      {"@type":"Person","name":"Ada Lovelace"}
    ]}
    </script>
    '''
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-4",
        mention_id_for_surface={"Ada Lovelace": "MN-ada"},
    )
    assert len(report.signals) == 1
    assert report.signals[0].source_vocab == "schema.org"
