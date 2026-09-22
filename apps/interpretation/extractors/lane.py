"""Deterministic extraction lane (spec 007, T032, US1/US4).

Composition root of the stack: ParserRegistry (charset-normalized, name-ordered
multi-adapter) + DeterministicExtractorSet (no-ML extractors gated by the
OntologyPack) + normalization post-pass. One artifact → one ExtractionResult:
segments WITH byte offsets + typed mentions (structure-first), all lanes
deterministic and offline.

Contract with ``apps/interpretation/pipeline.py``: this lane ADDS a new
``extract_deterministic`` seam; it does not alter the pipeline's existing
path (T032 integrates via the same Observations flow later).
"""

from __future__ import annotations

import hashlib
from typing import Any

from extractors.normalize import normalize_pass
from extractors.registry import DeterministicExtractorSet
from extractors.types import ExtractionResult
from parsers.documents import DocumentsAdapter
from parsers.html_full import HtmlFullAdapter
from parsers.plaintext import PlainTextAdapter
from parsers.registry import ParserRegistry
from parsers.structured import StructuredAdapter

DETERMINISTIC_ADAPTERS = (DocumentsAdapter, HtmlFullAdapter, PlainTextAdapter, StructuredAdapter)
"""Registry re-sorts by name: documents < html_full < plaintext < structured."""


def build_default_stack(
    *,
    ontology_pack: Any = None,
    max_parse_ms: float | None = None,
    on_quarantine: Any = None,
) -> tuple[ParserRegistry, DeterministicExtractorSet]:
    registry = ParserRegistry(max_parse_ms=max_parse_ms, on_quarantine=on_quarantine)
    for adapter in DETERMINISTIC_ADAPTERS:
        registry.register_adapter(adapter())
    extractors = DeterministicExtractorSet(ontology_pack=ontology_pack)
    extractors.register_builtin()
    return registry, extractors


def extract_deterministic(
    artifact: Any,
    *,
    stack: tuple[ParserRegistry, DeterministicExtractorSet] | None = None,
    ontology_pack: Any = None,
    max_parse_ms: float | None = None,
) -> ExtractionResult:
    """Full deterministic extraction for one artifact (structure + body)."""
    registry, extractors = stack or build_default_stack(
        ontology_pack=ontology_pack, max_parse_ms=max_parse_ms
    )
    raw = _as_bytes(artifact)
    merged = registry.extract_artifact(artifact)
    if merged is None:
        return ExtractionResult(
            artifact_sha=hashlib.sha256(raw).hexdigest(),
            content_type=_content_type_of(raw),
            segments=[],
            mentions=[],
            reason="no-extraction-adapter: unclaimed artifact",
        )

    structured_seed = [m for m in merged.mentions]
    for seg in list(merged.segments):
        if seg.kind != "text":
            continue
        for m in extractors.extract(seg.text, lang=seg.lang_hint):
            m.offset += seg.offset
            if m.end_offset:
                m.end_offset += seg.offset
            merged.mentions.append(m)

    mentions = normalize_pass(merged.mentions, structured=structured_seed)
    merged.mentions = _final_order(mentions)
    merged.segments = [s for s in merged.segments]
    return merged


def _content_type_of(raw: bytes) -> str:
    if raw[:5] == b"%PDF-":
        return "application/pdf"
    if raw[:4] == b"PK\x03\x04":
        return "application/zip"
    if raw[:2] == b"\xff\xd8":
        return "image/jpeg"
    if raw[:4] == b"\x89PNG":
        return "image/png"
    token = raw[:200]
    low = token.decode("utf-8", errors="replace").lower()
    if any(m in low for m in ("<html", "<head", "<body", "<!doctype html")):
        return "text/html"
    return "text/plain"


def _final_order(mentions) -> list[Any]:
    return sorted(mentions, key=lambda m: (m.offset, m.kind, m.value))


def _as_bytes(artifact: Any) -> bytes:
    if isinstance(artifact, (bytes, bytearray)):
        return bytes(artifact)
    if isinstance(artifact, str):
        return artifact.encode("utf-8")
    return b""