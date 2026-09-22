"""Tantivy search-index adapter tests (feature 010 upgrade, on-disk tier).

Pins the ``SearchIndex`` contract on tantivy: kind + tenant filtered search,
fail-closed tenant requirement (FR-011), idempotent writes (I-11) and
provenance enforcement (I-12). Runs fully hermetic (in-process index; disk mode
uses pytest's tmp_path).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

pytest.importorskip("tantivy")

from domain import ProjectionRebuildableError

from search.index import IndexedDoc
from search.quickwit import TenantIsolationError
from search.tantivy_backend import TantivySearchIndex


def _doc(doc_id: str, text: str, tenant: str, kind: str = "documents") -> IndexedDoc:
    return IndexedDoc(
        doc_id=doc_id,
        index=kind,
        body={"doc_id": doc_id, "tenant_id": tenant, "kind": kind, "text": text},
        provenance={"event_id": doc_id, "observation_id": doc_id},
    )


class TestTantivySearchIndex:
    def test_index_and_search_within_tenant(self, tmp_path):
        idx = TantivySearchIndex(dir_path=str(tmp_path / "ix"))
        idx.bulk_index_docs(
            [
                _doc("d1", "offshore assets freeze", "t1"),
                _doc("d2", "garden vegetables", "t1"),
                _doc("d3", "offshore shell company", "t2"),
            ]
        )
        assert idx.search("documents", "offshore", tenant="t1") == ["d1"]
        assert idx.search("documents", "offshore", tenant="t2") == ["d3"]
        assert idx.search("documents", "vegetables", tenant="t1") == ["d2"]

    def test_tenant_required_fail_closed(self):
        idx = TantivySearchIndex()
        idx.index_doc(_doc("d1", "offshore", "t1"))
        with pytest.raises(TenantIsolationError):
            idx.search("documents", "offshore")

    def test_idempotent_index_doc(self):
        idx = TantivySearchIndex()
        doc = _doc("d1", "wire transfer", "t1")
        idx.index_doc(doc)
        idx.index_doc(doc)
        assert idx.count() == 1

    def test_requires_provenance(self):
        idx = TantivySearchIndex()
        with pytest.raises(ProjectionRebuildableError):
            idx.index_doc(
                IndexedDoc(doc_id="x", index="documents", body={"tenant_id": "t1", "text": "hi"})
            )

    def test_kind_isolation(self):
        idx = TantivySearchIndex()
        idx.bulk_index_docs(
            [
                _doc("d1", "offshore", "t1"),
                _doc("m1", "offshore mention", "t1", kind="mentions"),
            ]
        )
        assert idx.search("documents", "offshore", tenant="t1") == ["d1"]
        assert idx.search("mentions", "offshore", tenant="t1") == ["m1"]

    def test_pending_docs_searchable_immediately(self):
        idx = TantivySearchIndex()
        idx.index_doc(_doc("d1", "sanctions list", "t1"))
        assert idx.search("documents", "sanctions", tenant="t1") == ["d1"]

    def test_empty_query_returns_empty(self):
        idx = TantivySearchIndex()
        idx.index_doc(_doc("d1", "sanctions list", "t1"))
        assert idx.search("documents", "   ", tenant="t1") == []
