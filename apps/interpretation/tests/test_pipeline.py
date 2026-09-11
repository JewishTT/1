"""Unit tests for interpretation pipeline (T032-T034, T081, US1)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "interpretation"))

from aggregation.candidates import CandidateAggregator, CanonicalMention
from extractors.registry import ExtractorRegistry, Mention
from normalization.canonical import Normalizer, normalize_url
from parsers.registry import ParserRegistry
from pipeline import InterpretationPipeline


class TestParsers:
    def test_html_pulls_text_blocks(self):
        body = b"<html><body><p>hello world</p><p>another one</p></body></html>"
        segs = ParserRegistry().parse(body, "text/html")
        assert any(s.text == "hello world" for s in segs)
        assert any(s.text == "another one" for s in segs)

    def test_json_recurses(self):
        segs = ParserRegistry().parse(b'{"a": "x", "b": ["y", 3]}', "application/json")
        assert any("x" in s.text for s in segs)
        assert any("y" in s.text for s in segs)

    def test_plain_text_fallback(self):
        segs = ParserRegistry().parse(b"just text", None)
        assert segs[0].text == "just text"

    def test_unknown_type_falls_back_to_plain(self):
        segs = ParserRegistry().parse(b"opaque", "application/octet-stream")
        assert segs[0].text == "opaque"


class TestExtractors:
    def test_url_email_ipv4_cve(self):
        text = "contact a@b.com from http://example.com/x and 1.2.3.4, CVE-2021-44228"
        mentions = ExtractorRegistry().extract(text)
        kinds = {m.kind for m in mentions}
        assert "email" in kinds and "url" in kinds and "ipv4" in kinds and "cve" in kinds
        assert any(m.value == "CVE-2021-44228" for m in mentions)

    def test_invalid_ip_rejected(self):
        mentions = ExtractorRegistry().extract("999.1.1.1 not an ip")
        assert not any(m.kind == "ipv4" and m.value == "999.1.1.1" for m in mentions)

    def test_dedup_same_value_kept_once(self):
        mentions = ExtractorRegistry().extract("go to http://x.com/a now http://x.com/a again")
        urls = [m.value for m in mentions if m.kind == "url"]
        assert urls.count("http://x.com/a") == 1


class TestNormalization:
    def test_url_case_and_slash(self):
        assert normalize_url("HTTPS://Example.COM:443/path//") == "https://example.com:443/path"
        assert normalize_url("http://example.com//") == "http://example.com/"

    def test_case_insensitive_keyword(self):
        assert Normalizer().keyword("  Hello World  ") == "hello world"

    def test_ip_compaction(self):
        assert Normalizer().normalize(Mention("ipv4", "1.2.3.4")).canonical == "1.2.3.4"


class TestAggregation:
    def test_fanout_unique_sources_raise_confidence(self):
        agg = CandidateAggregator()
        m1 = CanonicalMention(kind="url", canonical="http://x.com/a")
        m2 = CanonicalMention(kind="url", canonical="http://x.com/a", alias="X.com/A/")
        agg.add(m1, source_id="s1")
        agg.add(m2, source_id="s2")
        cand = agg.all()[0]
        assert cand.count == 2
        assert len(cand.sources) == 2
        assert cand.aliases == ["X.com/A/"]
        assert 0.5 <= cand.confidence <= 1.0


class TestOntologyFilter:
    def test_pack_restricts_types(self):
        from events.ontology_pack import OntologyPack, OntologyPackRegistry

        pack = OntologyPack(entity_types=["EMAIL", "URL"])
        registry = OntologyPackRegistry()
        registry.register(pack)
        registry.activate(pack.pack_version)
        extractors = ExtractorRegistry(ontology_pack=registry.active_for())
        kinds = {m.kind for m in extractors.extract("a@b.com and 1.2.3.4")}
        assert "email" in kinds
        assert "ipv4" not in kinds

    def test_no_pack_keeps_all_types(self):
        extractors = ExtractorRegistry()
        kinds = {m.kind for m in extractors.extract("a@b.com and 1.2.3.4")}
        assert "email" in kinds and "ipv4" in kinds


class TestPipeline:
    def test_full_pipeline_extracts_and_dedups(self):
        body = (
            b"<html><body>CVE-2021-44228 at https://x.com/p "
            b"and https://x.com/p again.</body></html>"
        )
        result = InterpretationPipeline().run("obs-1", body, "text/html")
        assert result.completed
        assert result.mention_count > 0
        assert any(c.kind == "cve" for c in result.candidates)
        urls = [c for c in result.candidates if c.kind == "url"]
        assert len(urls) == 1

    def test_immutable_observation_not_mutated_pipeline(self):
        data = b"stable content"
        result = InterpretationPipeline().run("obs-2", data, "text/plain")
        assert result.observation_id == "obs-2"
        assert data == b"stable content"


class _MockProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


class TestDomainStatements:
    def test_run_without_dataset_produces_no_statements(self):
        result = InterpretationPipeline().run(
            "obs-3", b"contact a@b.com and https://x.com", "text/plain"
        )
        assert result.statements == []

    def test_run_with_dataset_emits_canonical_statements_and_entities(self):
        producer = _MockProducer()
        result = InterpretationPipeline().run(
            "obs-4",
            b"contact a@b.com and use CVE-2021-44228",
            "text/plain",
            dataset_id="ds-intel",
            producer=producer,
        )
        assert result.statements, "expected statements for parsed candidates"
        email_stmts = [s for s in result.statements if s.schema_name == "Email"]
        assert email_stmts, "email candidate should be schematised"
        assert any(e.schema_name == "Email" for e in result.entities)
        assert all(
            s.dataset_id == "ds-intel" and s.provenance["producer"] == "interpretation-pipeline"
            for s in result.statements
        )
        assert len(producer.sent) == len(result.statements) + len(result.manifests)
        statement_events = [
            e for _, e, _ in producer.sent if e.event_type == "statement.created"
        ]
        manifest_events = [
            e for _, e, _ in producer.sent if e.event_type == "evidence.manifest_created"
        ]
        assert len(statement_events) == len(result.statements)
        assert len(manifest_events) == len(result.manifests)
        assert all(e.event_type == "statement.created" for e in statement_events)
        asserted = {}
        for _, env, key in producer.sent:
            if env.event_type == "statement.created":
                asserted[key] = env.entity_id
        for s in result.statements:
            assert asserted[s.statement_id] == s.entity_id

    def test_run_attaches_evidence_manifests_chain(self):
        producer = _MockProducer()
        result = InterpretationPipeline().run(
            "obs-5",
            b"contact a@b.com",
            "text/plain",
            dataset_id="ds-intel",
            producer=producer,
        )
        assert result.manifests, "parsed observations carry evidence manifests (US3)"
        assert len(result.manifests) == len(result.candidates)
        assert all(m.observation_id == "obs-5" for m in result.manifests)
        assert all(m.evidence_id.startswith("EVD-") for m in result.manifests)
        chain = result.manifests[0].chain()
        assert len(chain) == 4  # finding → evidence → observation → raw sha256
        raw_sha256 = chain[3]
        assert result.manifests[0].raw_sha256 == raw_sha256
        assert len(raw_sha256) == 64