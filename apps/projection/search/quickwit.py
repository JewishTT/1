"""Quickwit search-projection adapter (FR-008..FR-012, ADR-0019).

Implements the existing ``SearchIndex`` contract on top of Quickwit: ingestion
is Kafka-native in production (Quickwit consumes ``search.projected``), and this
adapter covers the query path, the rebuild path and the contract tests.

Two invariants are enforced here, not upstream:

* provenance — every document carries projection provenance (I-12);
* tenant isolation — a query without a tenant fails closed, so a caller can
  never read across tenants even by accident (FR-011).

The transport is injected, so contract tests run without a live index.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from domain import enforce_projection_provenance

import path_shim  # noqa: F401 - keep apps/shared ahead of conflicting dirs

from .index import IndexedDoc
from .mappings import alias_name, index_config, physical_index_name

Transport = Callable[[str, str, bytes | None], "tuple[int, str]"]


class QuickwitError(RuntimeError):
    """A Quickwit call failed (transport error or non-2xx response)."""


class TenantIsolationError(PermissionError):
    """A query without a tenant was attempted (fail-closed, FR-011)."""


def _default_transport(method: str, url: str, body: bytes | None) -> tuple[int, str]:
    """HTTP transport used in production (lazy httpx import)."""
    import httpx

    headers = {"Content-Type": "application/json"}
    response = httpx.request(method, url, content=body, headers=headers, timeout=30.0)
    return response.status_code, response.text


class QuickwitSearchIndex:
    """``SearchIndex`` implementation backed by Quickwit (ADR-0019)."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:7280",
        transport: Transport | None = None,
        max_hits: int = 100,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport or _default_transport
        self._max_hits = max_hits

    # -- SearchIndex protocol ---------------------------------------------
    def index_doc(self, doc: IndexedDoc, provenance: dict | None = None) -> None:
        """Index one projected document (idempotent upstream on ``doc_id``)."""
        enforce_projection_provenance(doc.provenance or provenance)
        body = self._prepare(doc)
        physical = physical_index_name(doc.index, str(body["tenant_id"]))
        self._post(f"/api/v1/{physical}/ingest", self._ndjson([body]))

    def bulk_index_docs(self, docs: list[IndexedDoc]) -> None:
        """Bulk-index documents, grouped per (kind, tenant) physical index."""
        if not docs:
            return
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for doc in docs:
            enforce_projection_provenance(doc.provenance)
            body = self._prepare(doc)
            grouped.setdefault((doc.index, str(body["tenant_id"])), []).append(body)
        for (kind, tenant), bodies in grouped.items():
            physical = physical_index_name(kind, tenant)
            self._post(f"/api/v1/{physical}/ingest", self._ndjson(bodies))

    def search(
        self,
        index: str,
        query: str,
        *,
        tenant: str | None = None,
        search_fields: list[str] | None = None,
    ) -> list[str]:
        """Search one kind inside exactly one tenant; returns ``doc_id`` list."""
        if not tenant:
            raise TenantIsolationError(
                "tenant is required for search (fail-closed, FR-011)"
            )
        alias = alias_name(index, tenant)
        payload: dict[str, Any] = {"query": query, "max_hits": self._max_hits}
        if search_fields:
            payload["search_fields"] = search_fields
        result = self._post(f"/api/v1/{alias}/search", payload)
        hits = result.get("hits", [])
        out: list[str] = []
        for hit in hits:
            source = hit.get("_source", hit)
            doc_id = source.get("doc_id")
            if doc_id:
                out.append(str(doc_id))
        return out

    # -- index lifecycle ---------------------------------------------------
    def ensure_index(self, kind: str, tenant: str, **overrides: Any) -> dict[str, Any]:
        """Create the tenant index if missing; returns the applied config."""
        config = index_config(kind, tenant=tenant, **overrides)
        status, _ = self._transport(
            "POST", f"{self._base_url}/api/v1/indexes", self._encode(config)
        )
        if status not in (200, 201) and status != 400:  # 400: already exists
            raise QuickwitError(f"ensure_index failed: HTTP {status}")
        return config

    def rebuild(
        self,
        kind: str,
        tenant: str,
        docs: list[IndexedDoc],
        *,
        index_id: str,
    ) -> str:
        """Rebuild a fresh physical index from a replayed document set (SC-003).

        Replay always writes into a brand-new index id, so the resulting index
        is identical to a first build regardless of the live index state.
        """
        physical = physical_index_name(kind, tenant)
        target = f"{physical}-{index_id}"
        lines: list[str] = []
        for doc in docs:
            enforce_projection_provenance(doc.provenance)
            body = self._prepare(doc)
            body["rebuild_id"] = index_id
            lines.append(json.dumps(body, sort_keys=True, default=str))
        self._post(f"/api/v1/{target}/ingest", "\n".join(lines) + "\n")
        return target

    # -- internals ---------------------------------------------------------
    def _prepare(self, doc: IndexedDoc) -> dict[str, Any]:
        body = dict(doc.body)
        body["doc_id"] = doc.doc_id
        body["kind"] = doc.index
        tenant = str(body.get("tenant_id", ""))
        if not tenant:
            raise ValueError(f"document {doc.doc_id} lacks tenant_id (fail-closed)")
        return body

    def _post(self, path: str, payload: str | dict[str, Any]) -> dict[str, Any]:
        body = self._encode(payload)
        status, text = self._transport("POST", f"{self._base_url}{path}", body)
        if status < 200 or status >= 300:
            raise QuickwitError(f"POST {path} failed: HTTP {status}: {text[:200]}")
        if not text.strip():
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
        return parsed if isinstance(parsed, dict) else {"hits": parsed}

    @staticmethod
    def _encode(payload: str | dict[str, Any]) -> bytes:
        if isinstance(payload, str):
            return payload.encode("utf-8")
        return json.dumps(payload, sort_keys=True, default=str).encode("utf-8")

    @staticmethod
    def _ndjson(bodies: list[dict[str, Any]]) -> str:
        return (
            "\n".join(json.dumps(b, sort_keys=True, default=str) for b in bodies)
            + "\n"
        )
