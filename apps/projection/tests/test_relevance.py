"""Ranked relevance index + mass-format extraction tests (feature 010, slice 2).

The zero-layer audit wanted a "search-engine" analog: mass-index relevant web
content with retrieval that *ranks*. These tests pin BM25-style scoring, tenant
isolation (I-12), idempotency (I-11), provenance (I-11), and the cross-format
extractors (HTML/JSON/XML/CSV/plain) feeding the index.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain import ProjectionRebuildableError

from search.indexer import RankedRetrieverBackend, RelevantContentIndexer
from search.relevance import ObservationTextExtractor, RankedInvertedIndex


def _prov(event: str = "e1", obs: str = "o1") -> dict:
    return {"event_id": event, "observation_id": obs}


class TestRankedIndex:
    def test_ranks_relevant_doc_first(self):
        idx = RankedInvertedIndex()
        idx.put(
            doc_id="a",
            index="documents",
            body={"text": "sanctions list assets offshore", "relevance": 0.9},
            tenant_id="t1",
            provenance=_prov(),
        )
        idx.put(
            doc_id="b",
            index="documents",
            body={"text": "sanctions are garden vegetables", "relevance": 0.1},
            tenant_id="t1",
            provenance=_prov(),
        )
        hits = idx.results("sanctions assets", top_k=2, tenant_id="t1")
        assert hits[0].doc_id == "a"
        assert hits[0].score > hits[1].score
        assert hits[0].snippet

    def test_tenant_isolation(self):
        idx = RankedInvertedIndex()
        idx.put(
            doc_id="a",
            index="documents",
            body={"text": "shell company offshore"},
            tenant_id="t1",
            provenance=_prov(),
        )
        idx.put(
            doc_id="b",
            index="documents",
            body={"text": "shell company offshore"},
            tenant_id="t2",
            provenance=_prov(),
        )
        assert [h.doc_id for h in idx.results("offshore", tenant_id="t1")] == ["a"]
        assert [h.doc_id for h in idx.results("offshore", tenant_id="t2")] == ["b"]

    def test_idempotent_put(self):
        idx = RankedInvertedIndex()
        a = idx.put(
            doc_id="x",
            index="documents",
            body={"text": "wire transfer"},
            tenant_id="t",
            provenance=_prov(),
        )
        b = idx.put(
            doc_id="x",
            index="documents",
            body={"text": "wire transfer"},
            tenant_id="t",
            provenance=_prov(),
        )
        assert a is True and b is False
        assert idx.size("t") == 1

    def test_requires_provenance(self):
        idx = RankedInvertedIndex()
        try:
            idx.put(
                doc_id="x", index="documents", body={"text": "hi"}, tenant_id="t", provenance=None
            )
            assert False, "expected ProjectionRebuildableError"
        except ProjectionRebuildableError:
            pass

    def test_rebuild_replays(self):
        idx = RankedInvertedIndex()
        idx.put(
            doc_id="a",
            index="documents",
            body={"text": "asset freeze"},
            tenant_id="t",
            provenance=_prov(),
        )
        snap = [
            {
                "doc_id": "a",
                "index": "documents",
                "body": {"text": "asset freeze"},
                "tenant_id": "t",
                "provenance": _prov(),
            }
        ]
        fresh = RankedInvertedIndex()
        fresh.rebuild(snap)
        assert fresh.size("t") == 1
        assert fresh.results("freeze", tenant_id="t")[0].doc_id == "a"


class TestObservationTextExtractor:
    def test_html_extracts_title_and_text(self):
        body = b"<html><head><title>ACME Holdings</title></head><body><p>Offshore <b>entity</b> found</p></body></html>"
        ex = ObservationTextExtractor()
        r = ex.extract(body, "text/html")
        assert "ACME Holdings" in r.title
        assert "Offshore" in r.text and "found" in r.text

    def test_json_flattens_values(self):
        body = b'{"org":{"name":"Cayman Co"},"account":"IBAN-XY1","active":true}'
        ex = ObservationTextExtractor()
        r = ex.extract(body, "application/json")
        assert "Cayman Co" in r.text
        assert "IBAN-XY1" in r.text
        assert "active" not in r.text  # keys are not values

    def test_csv_rows_indexed(self):
        body = b"name,email\nJane, jane@x.test\nBob, bob@y.test\n"
        ex = ObservationTextExtractor()
        r = ex.extract(body, "text/csv")
        assert "Jane" in r.text and "jane@x.test" in r.text and "Bob" in r.text

    def test_feed_xml_data(self):
        body = b'<?xml version="1.0"?><rss><channel><title>Feed Two</title><item><title>Item Six</title></item></channel></rss>'
        ex = ObservationTextExtractor()
        r = ex.extract(body, "application/rss+xml")
        assert "Feed" in r.text and "Item" in r.text

    def test_plain_text_passthrough(self):
        ex = ObservationTextExtractor()
        r = ex.extract(b"plain disclosure text", "text/plain")
        assert r.text == "plain disclosure text"

    def test_degenerate_input_no_crash(self):
        ex = ObservationTextExtractor()
        assert ex.extract(b"") == ex.extract(b"")
        r = ex.extract(b"{invalid json", "application/json")
        assert r.text  # falls back to raw decode, still no crash


class TestRelevantContentIndexer:
    def test_indexes_observation_into_ranked_index(self):
        idx = RankedInvertedIndex()
        indexer = RelevantContentIndexer(index=idx)
        inserted = indexer.index(
            observation_id="o1",
            uri="http://site.test/b",
            body=b"<title>KYC body</title><p>sanctions compliance</p>",
            content_type="text/html",
            tenant_id="t1",
        )
        assert inserted is True
        assert idx.size("t1") == 1
        hits = idx.results("compliance", tenant_id="t1")
        assert hits and hits[0].doc_id == "obs:o1"

    def test_binary_not_indexable(self):
        indexer = RelevantContentIndexer()
        assert (
            indexer.index(
                observation_id="o2",
                uri="http://x/img",
                body=b"\x89PNG\r\n\x1a\n...",
                content_type="image/png",
                tenant_id="t1",
            )
            is False
        )

    def test_index_with_entities(self):
        idx = RankedInvertedIndex()
        indexer = RelevantContentIndexer(index=idx)
        indexer.index_with_entities(
            observation_id="o3",
            uri="http://site.test/c",
            body=b"<title>Acme</title>Acme is a flagged entity",
            content_type="text/html",
            tenant_id="t1",
            entities=["Acme"],
        )
        assert idx.results("Acme", tenant_id="t1")[0].doc_id == "obs:o3"


class TestRankedRetrieverBackend:
    def test_retrieve_returns_ranked_hits(self):
        idx = RankedInvertedIndex()
        idx.put(
            doc_id="d1",
            index="documents",
            body={"text": "whale tail offices London", "relevance": 0.9},
            tenant_id="t1",
            provenance=_prov(),
        )
        idx.put(
            doc_id="d2",
            index="documents",
            body={"text": "whale dishes restaurant", "relevance": 0.1},
            tenant_id="t1",
            provenance=_prov(),
        )
        backend = RankedRetrieverBackend(index=idx, tenant_id="t1")
        assert backend.supports("http")
        hits = backend.retrieve("http", "whale offices", top_k=2)
        assert hits[0].doc_id == "d1"
        assert hits[0].score > hits[1].score
        assert hits[0].backend == "ranked-inmemory"
        # retriever-protocol shape consumed by interpretation.CrossSemanticRetriever
        assert {"doc_id", "text", "score", "backend"} <= set(hits[0].as_dict())
