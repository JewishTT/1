"""Observation → segments parser scaffold (T032, FR-011).

Dispatch by content type (HTML/JSON/XML/PDF/plain). Heavy parsers are isolated
behind a registry so a malformed parser can't take down the pipeline. Returns
segments: synchronized text blocks with offsets + language hint.

Feature 005 US3 hardening (T022): size/depth/time limits + deterministic
adapter dispatch; hostile/oversized input is quarantined (never parsed) using
the shared DLQ/quarantine semantics (``events.dlq``), preserving the payload
for replay instead of crashing or silently dropping.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser as _HTMLParser
from typing import Any, Protocol, runtime_checkable

from events.dlq import DLQRecord

MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_JSON_DEPTH = 64


class ParserLimitError(Exception):
    """Raised when an artifact exceeds parser limits and no quarantine sink is set."""


@dataclass
class Segment:
    text: str
    offset: int
    lang_hint: str | None = None
    kind: str = "text"
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    """Deterministic parser finding (FR-010, NetForensicAI pattern)."""

    kind: str
    value: str
    offset: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ParserAdapter(Protocol):
    """Unified parser interface (FR-010): can_parse detects, parse yields findings.

    Adapters are deterministic (same artifact → same findings) and isolated
    (heavy/unsafe formats run in isolated worker classes, C-7). Convention:
    adapters also carry ``name: str`` and ``content_types: list[str]``.

    Spec 007 extraction adapters (html_full, structured, documents, plaintext)
    additionally implement ``extract(artifact) -> ExtractionResult``; the
    extraction lane detects them via ``hasattr(adapter, "extract")`` so this
    method stays OUT of the runtime protocol (adding it would break legacy
    parse-only adapters on ``isinstance`` checks, NFR-4).
    """

    def can_parse(self, artifact: Any) -> bool: ...
    def parse(self, artifact: Any) -> list[Finding]: ...


class _TextExtract(_HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[tuple[int, str]] = []
        self._depth = 0

    def handle_data(self, data: str) -> None:
        stripped = " ".join(data.split())
        if stripped:
            self.parts.append((self._depth, stripped))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        self._depth = max(0, self._depth - 1)


class ParserRegistry:
    """Dispatch parser by content type; unknown types fall back to plain text.

    Also registers ParserAdapter instances (FR-010): `can_parse` detects an
    artifact, `parse_artifact` yields deterministic Finding objects.

    Limits (feature 005 US3): artifacts larger than ``max_body_bytes``, JSON
    deeper than ``max_depth``, or a parse exceeding ``max_parse_ms`` are never
    parsed — they are quarantined via ``on_quarantine`` when set, otherwise a
    ``ParserLimitError`` is raised. Adapter dispatch is stable: first match in
    name-sorted order, so the same artifact always uses the same adapter.
    """

    def __init__(
        self,
        *,
        max_body_bytes: int = MAX_BODY_BYTES,
        max_depth: int = MAX_JSON_DEPTH,
        max_parse_ms: float | None = None,
        on_quarantine: Callable[[DLQRecord], str | None] | None = None,
    ) -> None:
        self._parsers: dict[str, Any] = {
            "text/html": self._parse_html,
            "application/xhtml+xml": self._parse_html,
            "application/xml": self._parse_feed,
            "application/rss+xml": self._parse_feed,
            "application/atom+xml": self._parse_feed,
            "text/csv": self._parse_csv,
            "application/json": self._parse_json,
            "text/plain": self._parse_text,
        }
        self._adapters: list[ParserAdapter] = []
        self.max_body_bytes = max_body_bytes
        self.max_depth = max_depth
        self.max_parse_ms = max_parse_ms
        self.on_quarantine = on_quarantine

    def parse(self, body: bytes, content_type: str | None = None) -> list[Segment]:
        self._guard_size(body)
        parser = self._parsers.get(content_type or "text/plain", self._parse_text)
        return parser(body)

    def register_adapter(self, adapter: ParserAdapter) -> None:
        """Register a can_parse/parse adapter (NetForensicAI pattern)."""
        if not isinstance(adapter, ParserAdapter):
            raise TypeError(f"{adapter!r} does not satisfy the ParserAdapter protocol")
        if any(a.name == adapter.name for a in self._adapters):
            raise ValueError(f"parser adapter already registered: {adapter.name}")
        self._adapters.append(adapter)

    def can_parse(self, artifact: Any) -> bool:
        """True if any registered adapter claims the artifact (FR-010)."""
        self._guard_size(_as_bytes(artifact))
        return any(adapter.can_parse(artifact) for adapter in self._dispatch_order())

    def parse_artifact(self, artifact: Any) -> list[Finding]:
        """Deterministic finding extraction via the first matching adapter.

        Dispatch order is name-stable (``_dispatch_order``); a faulting adapter
        is skipped (fault isolation, C-7) and the artifact quarantined. Unknown
        binary formats fall through to quarantine/none instead of being parsed
        as text.
        """
        raw = _as_bytes(artifact)
        self._guard_size(raw)
        deadline = _deadline(self.max_parse_ms)
        for adapter in self._dispatch_order():
            try:
                if not adapter.can_parse(artifact):
                    continue
                return list(adapter.parse(artifact))
            except (ParserLimitError, RecursionError):
                self._quarantine("parser.depth_or_time_limit", raw)
                raise
            except Exception as exc:
                self._quarantine(f"parser.adapter_fault:{adapter.name}", raw, detail=str(exc))
                if deadline is not None and time.monotonic() > deadline:
                    self._quarantine("parser.timeout", raw)
                    raise ParserLimitError("parse exceeded max_parse_ms") from exc
                continue
        if _looks_binary(raw):
            self._quarantine("parser.unknown_format", raw)
        return []

    def adapters(self) -> list[ParserAdapter]:
        return list(self._adapters)

    def extract_artifact(self, artifact: Any) -> Any:
        """Spec-007 extraction lane: run ALL extraction-aware adapters, merged.

        Every registered adapter that ``can_parse`` AND implements ``extract``
        runs in name-stable order (documents < html_full < structured), so a
        single artifact yields both body segments and structured mentions.
        Results are merged into one ``ExtractionResult``; per-adapter faults
        are quarantined and skipped (C-7 isolation). No adapter → ``None``.
        """
        from extractors.types import ExtractionResult

        raw = _as_bytes(artifact)
        self._guard_size(raw)
        merged = None
        for adapter in self._dispatch_order():
            if not hasattr(adapter, "extract"):
                continue
            try:
                if not adapter.can_parse(artifact):
                    continue
                result = adapter.extract(artifact)
                if result is None:
                    continue
                if not isinstance(result, ExtractionResult):
                    raise TypeError(f"{adapter.name}.extract returned {type(result).__name__}")
                merged = result if merged is None else _merge_extraction(merged, result)
            except (ParserLimitError, RecursionError):
                self._quarantine("parser.depth_or_time_limit", raw)
                raise
            except Exception as exc:  # noqa: BLE001 - adapter isolation
                self._quarantine(f"parser.adapter_fault:{adapter.name}", raw, detail=str(exc))
                continue
        return merged

    def normalize_encoding(self, body: bytes) -> str:
        """Charset-normalized text (deterministic; crashes never escape)."""
        try:
            from extractors.language import decode_bytes

            return decode_bytes(body)[0]
        except Exception:  # noqa: BLE001 - hostile bytes still degrade to utf-8
            return body.decode("utf-8", errors="replace")

    def _dispatch_order(self) -> list[ParserAdapter]:
        """Name-stable adapter order: same artifact → same adapter every time."""
        return sorted(self._adapters, key=lambda a: a.name)

    def _guard_size(self, body: bytes) -> None:
        if len(body) > self.max_body_bytes:
            self._quarantine(
                "parser.oversized",
                body,
                detail=f"{len(body)} bytes > {self.max_body_bytes}",
            )
            raise ParserLimitError(
                f"artifact too large: {len(body)} bytes exceeds {self.max_body_bytes}"
            )

    def _quarantine(self, reason: str, payload: bytes, detail: str | None = None) -> None:
        if self.on_quarantine is None:
            return
        record = DLQRecord(reason=reason, payload=payload, topic="interpretation")
        if detail:
            record.reason = f"{reason}: {detail}"
        self.on_quarantine(record)

    def _parse_html(self, body: bytes) -> list[Segment]:
        extractor = _TextExtract()
        try:
            extractor.feed(self.normalize_encoding(body))
        except Exception:  # noqa: BLE001 - parser isolation: one bad doc must not kill the pipeline
            return []
        return [
            Segment(text=t, offset=i, kind="text") for i, (_, t) in enumerate(extractor.parts) if t
        ]

    def _parse_csv(self, body: bytes) -> list[Segment]:
        import csv

        text = self.normalize_encoding(body)
        try:
            rows = list(csv.reader(text.splitlines()))
        except Exception:  # noqa: BLE001 - malformed CSV → no segments, not a crash
            return []
        if not rows:
            return []
        header = [c.strip() for c in rows[0]]
        segments: list[Segment] = []
        for i, row in enumerate(rows[1:], start=1):
            cells = dict(zip(header, [c.strip() for c in row])) if len(header) == len(row) else {}
            meta = {"kind": "csv-row", "row": i}
            if cells:
                meta["fields"] = cells
            segments.append(
                Segment(
                    text=" ".join(c.strip() for c in row if c.strip()),
                    offset=i,
                    kind="text",
                    meta=meta,
                )
            )
        return segments

    def _parse_feed(self, body: bytes) -> list[Segment]:
        import xml.etree.ElementTree as ET

        text = self.normalize_encoding(body)
        try:
            root = ET.fromstring(text)
        except (ET.ParseError, ValueError):
            return []
        segments: list[Segment] = []
        for el in root.iter():
            tag = el.tag.rsplit("}", 1)[-1].lower()
            # RSS items and Atom entries are the per-document records.
            if tag in ("item", "entry"):
                title = _child_text(el, "title")
                link = _child_text(el, "link") or _child_text(el, "id")
                summary = _child_text(el, "description") or _child_text(el, "summary")
                snippet = " ".join(x for x in (title, summary) if x)
                meta = {"kind": "feed-entry"}
                if link:
                    meta["uri"] = link
                    snippet = f"{snippet} {link}".strip()
                if title:
                    meta["title"] = title
                if snippet:
                    segments.append(
                        Segment(text=snippet, offset=len(segments), kind="text", meta=meta)
                    )
        return segments if segments else self._parse_html(body)

    def _parse_json(self, body: bytes) -> list[Segment]:
        import json

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:  # noqa: BLE001 - malformed JSON → no segments, not a crash
            return []
        try:
            return [self._walk_json(data, depth=0)]
        except RecursionError:
            self._quarantine("parser.depth_limit", body)
            raise ParserLimitError("json nesting exceeded max_depth") from None

    def _walk_json(self, node: Any, depth: int) -> Segment:
        if depth > self.max_depth:
            raise RecursionError(f"depth {depth} > {self.max_depth}")
        if isinstance(node, str):
            return Segment(text=node, offset=0, kind="text", meta={"kind": "json-string"})
        if isinstance(node, list):
            return Segment(
                text=" ".join(s.text for s in (self._walk_json(x, depth + 1) for x in node)),
                offset=0,
                kind="text",
                meta={"kind": "json-array"},
            )
        if isinstance(node, dict):
            text = " ".join(s.text for s in (self._walk_json(v, depth + 1) for v in node.values()))
            return Segment(text=text, offset=0, kind="text", meta={"kind": "json-object"})
        return Segment(text=str(node), offset=0, kind="text", meta={"kind": "scalar"})

    def _parse_text(self, body: bytes) -> list[Segment]:
        text = self.normalize_encoding(body)
        return [Segment(text=text, offset=0, kind="text")] if text.strip() else []


def _merge_extraction(acc: Any, result: Any) -> Any:
    """Combine two ExtractionResults: segments + mentions, stable key order."""
    seen_segments = {_seg_core(s) for s in acc.segments}
    for s in result.segments:
        if _seg_core(s) in seen_segments:
            continue
        seen_segments.add(_seg_core(s))
        acc.segments.append(s)
    acc.mentions = _merge_mentions(list(acc.mentions), list(result.mentions))
    return acc


def _seg_core(seg: Any) -> tuple:
    return (seg.offset, seg.kind, seg.text)


def _merge_mentions(left: list[Any], right: list[Any]) -> list[Any]:
    seen: set[tuple] = {_mention_key(m) for m in left}
    out = list(left)
    for m in right:
        key = _mention_key(m)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return sorted(out, key=_mention_key)


def _mention_key(m: Any) -> tuple:
    return (m.offset, m.kind, m.value)


def _child_text(el: Any, tag: str) -> str:
    """Text of the first direct child with local name ``tag`` (RSS/Atom agnostic)."""
    for child in el:
        if child.tag.rsplit("}", 1)[-1].lower() == tag:
            return " ".join((child.text or "").split())
    return ""


def _as_bytes(artifact: Any) -> bytes:
    if isinstance(artifact, (bytes, bytearray)):
        return bytes(artifact)
    if isinstance(artifact, str):
        return artifact.encode("utf-8")
    return b""


def _looks_binary(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:512]
    return b"\x00" in sample


def _deadline(max_parse_ms: float | None) -> float | None:
    return None if max_parse_ms is None else time.monotonic() + max_parse_ms / 1000.0
