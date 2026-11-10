from __future__ import annotations

from extractors.structured_types import StructuredTypeSignalExtractor


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


def test_non_jsonld_script_is_ignored_even_when_it_contains_schema_shaped_json():
    source = '''<script type="text/javascript">
    {"@context":"https://schema.org","@type":"Person","name":"Ada Lovelace"}
    </script>'''
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-js",
        mention_id_for_surface={"Ada Lovelace": "MN-ada"},
    )
    assert report.signals == ()
    assert report.refusals == ()


def test_multiple_types_on_one_jsonld_node_reuse_the_same_existing_mention():
    source = '''<script type="application/ld+json">
    {"@context":"https://schema.org","@type":["Person","Thing"],"name":"Ada Lovelace"}
    </script>'''
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-multiple-types",
        mention_id_for_surface={"Ada Lovelace": "MN-ada"},
    )
    assert {signal.surface for signal in report.signals} == {"Person", "Thing"}
    assert len(report.signals) == 2
    assert {signal.mention_ref for signal in report.signals} == {"MN-ada"}
    assert len({signal.structural_path for signal in report.signals}) == 1
    assert report.refusals == ()


def test_jsonld_unresolved_mention_is_a_typed_refusal():
    source = '<script type="application/ld+json">{"@type":"Person","name":"Unknown Name"}</script>'
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-2",
        mention_id_for_surface={},
    )
    assert report.signals == ()
    assert report.refusals[0].code == "mention_unresolved"


def test_absolute_foreign_type_is_not_overridden_by_schema_default_vocab():
    source = '''<script type="application/ld+json">
    {"@context":"https://schema.org","@type":"https://evil.example/Person","name":"Ada Lovelace"}
    </script>'''
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-foreign-type",
        mention_id_for_surface={"Ada Lovelace": "MN-ada"},
    )
    assert report.signals == ()
    assert [item.code for item in report.refusals] == ["unsupported_type_vocabulary"]


def test_schema_lookalike_host_does_not_establish_the_schema_default_vocab():
    source = '''<script type="application/ld+json">
    {"@context":"https://schema.org.attacker.invalid/","@type":"Person","name":"Ada Lovelace"}
    </script>'''
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-lookalike-context",
        mention_id_for_surface={"Ada Lovelace": "MN-ada"},
    )
    assert report.signals == ()
    assert [item.code for item in report.refusals] == ["unsupported_type_vocabulary"]


def test_schema_compact_iri_requires_an_explicit_schema_prefix_binding():
    source = '''<script type="application/ld+json">
    {"@context":{"schema":"https://schema.org/"},"@type":"schema:Person","name":"Ada Lovelace"}
    </script>'''
    report = StructuredTypeSignalExtractor().extract(
        source, tenant_id="tenant-test", observation_ref="OBS-schema-prefix",
        mention_id_for_surface={"Ada Lovelace": "MN-ada"},
    )
    assert len(report.signals) == 1
    assert report.signals[0].source_vocab == "schema.org"
    assert report.signals[0].surface == "schema:Person"


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
