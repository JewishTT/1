"""Relevance-ranked search over indexed observation content (feature 010, slice 2).

The search-engine analog the zero-layer audit asks for: **mass-indexing
relevant web content**, not just classifying it. The projector already pushed
documents of seven kinds, but the in-memory adapter was boolean-AND retrieval
— no ranking, no scoring, no relevance. ``RankedInvertedIndex`` is a BM25-ish
retrieval core (stdlib only, no numpy):

- per-tenant inverted index with document frequencies + term statistics,
- BM25 scoring with idf smoothing and per-doc relevance (``body["relevance"]``),
- ranked ``results(query, top_k)`` plus snippet generation,
- idempotent by ``doc_id`` (I-11) — re-indexing the same doc is a no-op,
- ``all(tenant)`` / ``size()`` for rebuild **without a transport** (I-12).

The output hits are structurally compatible with
``interpretation.search.retriever.Hit`` (doc_id/text/score/backend) so a
``Retriever``-shaped adapter can fuse them into the cross-semantic ranker.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

from domain import enforce_projection_provenance

import path_shim  # noqa: F401

_TOKEN_RE = re.compile(r"[a-z0-9à-ÿ]+", re.IGNORECASE)
TITLE_DOC_KINDS = {"documents", "observations"}


def tokenize(text: str) -> list[str]:
    """Lowercased alphanumeric terms (keeps unicode letters, drops punctuation)."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t]


@dataclass(frozen=True)
class RelevanceHit:
    doc_id: str
    text: str = ""
    snippet: str = ""
    score: float = 0.0
    backend: str = "ranked-inmemory"

    def as_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "text": self.text,
            "snippet": self.snippet,
            "score": self.score,
            "backend": self.backend,
        }


@dataclass
class _RankedDoc:
    doc_id: str
    index: str
    body: dict
    tenant_id: str = ""


class RankedInvertedIndex:
    """BM25-ish inverted index with per-tenant isolation (I-12)."""

    def __init__(self) -> None:
        self._docs: dict[str, _RankedDoc] = {}
        self._by_tenant: dict[str, set[str]] = defaultdict(set)
        self._postings: dict[str, dict[str, int]] = defaultdict(dict)  # term -> {doc_id: tf}
        self._dlens: dict[str, int] = {}
        self._df: dict[str, int] = defaultdict(int)  # term -> doc frequency
        self._avgdl: float = 0.0

    # -- write side ---------------------------------------------------------

    def put(
        self, *, doc_id: str, index: str, body: dict, tenant_id: str, provenance: dict | None = None
    ) -> bool:
        """Index one document. Returns True when inserted, False on idempotent dup."""
        enforce_projection_provenance(provenance)
        if doc_id in self._docs:
            return False  # idempotent (I-11): same doc_id never overwrites
        text = " ".join(
            [
                str(body.get("text", "")),
                str(body.get("title", "")),
                " ".join(str(v) for v in (body.get("fields") or [])),
                " ".join(str(v) for v in (body.get("entities") or [])),
            ]
        )
        tokens = tokenize(text)
        self._docs[doc_id] = _RankedDoc(doc_id, index, dict(body), tenant_id)
        self._by_tenant[tenant_id].add(doc_id)
        unique_terms: set[str] = set()
        for tok in tokens:
            self._postings[tok][doc_id] = self._postings[tok].get(doc_id, 0) + 1
            unique_terms.add(tok)
        for tok in unique_terms:
            self._df[tok] += 1
        self._dlens[doc_id] = len(tokens)
        self._avgdl = (sum(self._dlens.values())) / (len(self._dlens) or 1)
        return True

    # -- read side ----------------------------------------------------------

    def results(
        self, query: str, *, top_k: int = 10, tenant_id: str | None = None
    ) -> list[RelevanceHit]:
        """Ranked retrieval: BM25 score, tenant-filtered, top_k slice."""
        terms = tokenize(query)
        if not terms:
            return []
        if tenant_id is not None:
            doc_ids = self._by_tenant.get(tenant_id, set())
        else:
            doc_ids = set(self._docs)
        n = max(len(self._docs), 1)
        scores: dict[str, float] = {}
        for term in terms:
            df = self._df.get(term, 0)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for doc_id, tf in self._postings.get(term, {}).items():
                if doc_id not in doc_ids:
                    continue
                doc = self._docs[doc_id]
                dl = self._dlens.get(doc_id, 0) or 1
                rel = float(doc.body.get("relevance", 0.5))
                k1, b = 1.2, 0.75
                tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / (self._avgdl or 1))))
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * tf_norm * (0.5 + rel)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [self.hit(doc_id, score) for doc_id, score in ranked]

    def hit(self, doc_id: str, score: float) -> RelevanceHit:
        doc = self._docs[doc_id]
        full = " ".join(
            [
                str(doc.body.get("title", "")),
                str(doc.body.get("text", "")),
                " ".join(str(v) for v in (doc.body.get("fields") or [])),
            ]
        )
        return RelevanceHit(
            doc_id=doc_id,
            text=str(doc.body.get("text", "")),
            snippet=self._snippet(full),
            score=round(score, 6),
            backend="ranked-inmemory",
        )

    # -- inspection / rebuild (I-12) -----------------------------------------

    def all(self, tenant_id: str | None = None) -> list[str]:
        if tenant_id is not None:
            return sorted(self._by_tenant.get(tenant_id, set()))
        return sorted(self._docs)

    def size(self, tenant_id: str | None = None) -> int:
        return len(self.all(tenant_id))

    def clear(self) -> None:
        self._docs.clear()
        self._by_tenant.clear()
        self._postings.clear()
        self._dlens.clear()
        self._df.clear()
        self._avgdl = 0.0

    def rebuild(self, docs: list[dict]) -> None:
        """Replay a durable doc list into a clean index (I-12)."""
        self.clear()
        for d in docs:
            self.put(
                doc_id=d["doc_id"],
                index=d["index"],
                body=d["body"],
                tenant_id=d["tenant_id"],
                provenance=d.get("provenance"),
            )

    @staticmethod
    def _snippet(text: str, width: int = 160) -> str:
        t = " ".join((text or "").split())
        return t if len(t) <= width else t[:width] + "…"


# -- text extraction: mass-index relevant web content ---------------------------
# The layers below turn raw observation bytes into indexable text — this is the
# "mass indexing" half of the search-engine analog (HTML, JSON, plain text).


@dataclass
class TextExtraction:
    text: str
    title: str = ""
    fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"text": self.text, "title": self.title, "fields": self.fields}


class ObservationTextExtractor:
    """Extract searchable text from observation bytes by declared content type.

    HTML → visible text (stdlib ``html.parser``); JSON → flattened values
    (bounded depth); XML/Feeds → element data; everything else → plain text.
    Degenerate input yields an empty extraction, never a crash (parser
    isolation, feature 005 US3 discipline).
    """

    MAX_JSON_DEPTH = 32

    #: Content types that are containers/bytes, never searchable text.
    BINARY_TYPES = (
        "image/",
        "audio/",
        "video/",
        "application/octet-stream",
        "application/pdf",
        "application/warc",
        "application/vnd.apache.parquet",
        "application/parquet",
        "application/x-parquet",
        "application/interactive",
    )

    def extract(self, body: bytes, content_type: str | None = None) -> TextExtraction:
        if not body:
            return TextExtraction("")
        ct = (content_type or "").lower()
        if any(ct.startswith(p) for p in self.BINARY_TYPES):
            # containers/media: no searchable text, no crash (honest zero).
            return TextExtraction("")
        if "html" in ct:
            return self._from_html(body)
        if "json" in ct:
            return self._from_json(body)
        if "xml" in ct or "+xml" in ct or "feed" in ct or "rss" in ct or "atom" in ct:
            return self._from_xml(body)
        if "csv" in ct:
            return self._from_csv(body)
        return TextExtraction(self._decode(body))

    # -- per-format extractors ----------------------------------------------

    def _from_html(self, body: bytes) -> TextExtraction:
        from html.parser import HTMLParser

        class _H(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.title: list[str] = []
                self.text: list[str] = []
                self._in_title = False
                self._skip = {"script", "style", "noscript"}

            def handle_starttag(self, tag, attrs):
                if tag == "title":
                    self._in_title = True
                if tag.lower() in self._skip:
                    self._in_title = False

            def handle_endtag(self, tag):
                if tag == "title":
                    self._in_title = False

            def handle_data(self, data):
                stripped = " ".join(data.split())
                if not stripped:
                    return
                if self._in_title:
                    self.title.append(stripped)
                else:
                    self.text.append(stripped)

        parser = _H()
        try:
            parser.feed(self._decode(body))
        except Exception:  # noqa: BLE001 - parser isolation
            return TextExtraction(self._decode(body))
        return TextExtraction(
            text=" ".join(parser.text),
            title=" ".join(parser.title),
        )

    def _from_json(self, body: bytes) -> TextExtraction:
        import json

        try:
            data = json.loads(self._decode(body))
        except Exception:  # noqa: BLE001 - malformed JSON → no crash
            return TextExtraction(self._decode(body))
        values: list[str] = []

        def walk(node, depth: int) -> None:
            if depth > self.MAX_JSON_DEPTH:
                return
            if isinstance(node, str):
                values.append(node)
            elif isinstance(node, dict):
                for v in node.values():
                    walk(v, depth + 1)
            elif isinstance(node, (list, tuple)):
                for v in node:
                    walk(v, depth + 1)
            elif node is not None:
                values.append(str(node))

        walk(data, 0)
        return TextExtraction(text=" ".join(values))

    def _from_xml(self, body: bytes) -> TextExtraction:
        from html.parser import HTMLParser

        class _X(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.parts: list[str] = []

            def handle_data(self, data):
                stripped = " ".join(data.split())
                if stripped:
                    self.parts.append(stripped)

        parser = _X()
        try:
            parser.feed(self._decode(body))
        except Exception:  # noqa: BLE001
            return TextExtraction(self._decode(body))
        return TextExtraction(text=" ".join(parser.parts))

    def _from_csv(self, body: bytes) -> TextExtraction:
        import csv
        import io

        rows: list[str] = []
        try:
            for row in csv.reader(io.StringIO(self._decode(body))):
                rows.append(" ".join(cell.strip() for cell in row if cell.strip()))
        except Exception:  # noqa: BLE001
            return TextExtraction(self._decode(body))
        return TextExtraction(text=" ".join(rows))

    @staticmethod
    def _decode(body: bytes) -> str:
        return body.decode("utf-8", errors="replace")
