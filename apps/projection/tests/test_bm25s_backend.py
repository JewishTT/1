"""bm25s-backed ranked index tests (feature 010 upgrade).

Pins the exact same invariants as the stdlib index (``test_relevance``) against
the bm25s backend: ranking, tenant isolation (I-12), idempotency (I-11),
provenance (I-11), rebuild replay — plus the default-factory preference and the
end-to-end indexer/retriever round-trip.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

pytest.importorskip("bm25s")

from domain import ProjectionRebuildableError

from search.bm25s_backend import BM25SRankedIndex
from search.indexer import RankedRetrieverBackend, RelevantContentIndexer, default_ranked_index


def _prov(event: str = "e1", obs: str = "o1") -> dict:
    return {"event_id": event, "observation_id": obs}


class TestBM25SRankedIndex:
    def test_ranks_relevant_doc_first(self):
        idx = BM25SRankedIndex()
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
        assert hits[0].score >= hits[1].score
        assert hits[0].snippet
        assert hits[0].backend == "ranked-bm25s"

    def test_tenant_isolation(self):
        idx = BM25SRankedIndex()
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
        idx = BM25SRankedIndex()
        kwargs = {
            "doc_id": "x",
            "index": "documents",
            "body": {"text": "wire transfer"},
            "tenant_id": "t",
            "provenance": _prov(),
        }
        assert idx.put(**kwargs) is True
        assert idx.put(**kwargs) is False
        assert idx.size("t") == 1

    def test_requires_provenance(self):
        idx = BM25SRankedIndex()
        with pytest.raises(ProjectionRebuildableError):
            idx.put(
                doc_id="x", index="documents", body={"text": "hi"}, tenant_id="t", provenance=None
            )

    def test_rebuild_replays(self):
        snap = [
            {
                "doc_id": "a",
                "index": "documents",
                "body": {"text": "asset freeze"},
                "tenant_id": "t",
                "provenance": _prov(),
            }
        ]
        fresh = BM25SRankedIndex()
        fresh.rebuild(snap)
        assert fresh.size("t") == 1
        assert fresh.results("freeze", tenant_id="t")[0].doc_id == "a"

    def test_new_docs_visible_after_first_query(self):
        idx = BM25SRankedIndex()
        idx.put(
            doc_id="a",
            index="documents",
            body={"text": "asset freeze"},
            tenant_id="t",
            provenance=_prov(),
        )
        assert idx.results("freeze", tenant_id="t")[0].doc_id == "a"
        idx.put(
            doc_id="b",
            index="documents",
            body={"text": "freeze order extended"},
            tenant_id="t",
            provenance=_prov(),
        )
        assert {h.doc_id for h in idx.results("freeze", tenant_id="t", top_k=5)} == {"a", "b"}

    def test_no_tenant_searches_all(self):
        idx = BM25SRankedIndex()
        idx.put(
            doc_id="a", index="documents", body={"text": "offshore"}, tenant_id="t1", provenance=_prov()
        )
        idx.put(
            doc_id="b", index="documents", body={"text": "offshore"}, tenant_id="t2", provenance=_prov()
        )
        assert {h.doc_id for h in idx.results("offshore")} == {"a", "b"}


class TestBM25SIntegration:
    def test_default_factory_prefers_bm25s(self):
        assert isinstance(default_ranked_index(), BM25SRankedIndex)

    def test_indexer_and_backend_roundtrip(self):
        indexer = RelevantContentIndexer(index=BM25SRankedIndex())
        inserted = indexer.index(
            observation_id="o1",
            uri="http://site.test/b",
            body=b"<title>KYC body</title><p>sanctions compliance</p>",
            content_type="text/html",
            tenant_id="t1",
        )
        assert inserted is True
        backend = RankedRetrieverBackend(indexer=indexer, tenant_id="t1")
        hits = backend.retrieve("http", "compliance", top_k=1)
        assert hits and hits[0].doc_id == "obs:o1"
