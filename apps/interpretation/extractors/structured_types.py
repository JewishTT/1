"""Structured source type statements -> TypeSignal, never TypeAssertion.

JSON-LD/schema.org is supported for mention-bound type observations. OpenGraph og:type is
page-level metadata and is deliberately refused until the platform has a document mention;
it must never be attached to the person named in og:title.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from html import unescape
from typing import Any

from semantic.type_signal import TypeSignal

_JSON_LD = re.compile(r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>",
                      flags=re.IGNORECASE | re.DOTALL)
_META = re.compile(r"<meta\b(?P<attrs>[^>]*)>", flags=re.IGNORECASE | re.DOTALL)
_ATTR = re.compile(r"""([:\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""",
                   flags=re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TypeExtractionRefusal:
    code: str
    detail: str
    structural_path: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail,
                "structural_path": list(self.structural_path)}


@dataclass(frozen=True, slots=True)
class TypeExtractionReport:
    signals: tuple[TypeSignal, ...]
    refusals: tuple[TypeExtractionRefusal, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "signals", tuple(self.signals))
        object.__setattr__(self, "refusals", tuple(self.refusals))


def _attrs(raw: str) -> dict[str, str]:
    result = {}
    for match in _ATTR.finditer(raw):
        result[match.group(1).casefold()] = unescape(
            next(value for value in match.groups()[1:] if value is not None)
        )
    return result


def _context_has_schema(value: Any) -> bool:
    if isinstance(value, str):
        return "schema.org" in value.casefold()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "@vocab" and isinstance(item, str) and "schema.org" in item.casefold():
                return True
            if key == "schema" and isinstance(item, str) and "schema.org" in item.casefold():
                return True
    if isinstance(value, (list, tuple)):
        return any(_context_has_schema(item) for item in value)
    return False


def _walk_jsonld(value: Any, path: tuple[str, ...] = (),
                 inherited_schema: bool = False) -> list[tuple[tuple[str, ...], str, str, bool]]:
    found = []
    if isinstance(value, Mapping):
        schema_context = inherited_schema or _context_has_schema(value.get("@context"))
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            raw_types = value.get("@type")
            raw_types = (raw_types,) if isinstance(raw_types, str) else tuple(raw_types or ())
            for item in raw_types:
                surface = str(item).strip()
                if surface:
                    is_schema = (schema_context or "schema.org/" in surface.casefold()
                                 or surface.casefold().startswith("schema:"))
                    found.append((path + ("@type",), surface, name, is_schema))
        for key, child in value.items():
            if isinstance(child, (Mapping, list, tuple)):
                found.extend(_walk_jsonld(child, path + (str(key),), schema_context))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found.extend(_walk_jsonld(child, path + (str(index),), inherited_schema))
    return found


def _json_name_offset(raw: str, name: str, cursor: int) -> tuple[int, int] | None:
    encoded = json.dumps(name, ensure_ascii=False)
    if len(encoded) < 2 or encoded[1:-1] != name:
        # A decoded string with JSON escapes must not be cited using guessed source offsets.
        return None
    # Anchor the exact JSON-LD "name" value, not an equal substring in description,
    # script text, or another property. Escaped quote sequences are not JSON keys.
    pattern = re.compile(r'(?<!\\)"name"\s*:\s*(' + re.escape(encoded) + r')')
    match = pattern.search(raw, cursor)
    if match is None:
        return None
    return match.start(1) + 1, match.end(1) - 1


class StructuredTypeSignalExtractor:
    """Extract JSON-LD/schema.org statements against existing mention references."""

    producer_jsonld = "structured/json-ld"

    def extract(
        self, html: str, *, tenant_id: str, observation_ref: str,
        mention_id_for_surface: Callable[[str], str | None] | Mapping[str, str],
    ) -> TypeExtractionReport:
        if not tenant_id.strip() or not observation_ref.strip():
            raise ValueError("tenant_id and observation_ref are required")
        if isinstance(mention_id_for_surface, Mapping):
            mention_lookup = lambda surface: mention_id_for_surface.get(surface)
        else:
            mention_lookup = mention_id_for_surface
        signals, refusals = [], []

        for block_index, block in enumerate(_JSON_LD.finditer(html)):
            script_type = _attrs(block.group("attrs")).get("type", "")
            script_type = script_type.split(";", 1)[0].strip().casefold()
            if script_type != "application/ld+json":
                continue
            raw = block.group("body")
            try:
                document = json.loads(raw)
            except (TypeError, ValueError):
                refusals.append(TypeExtractionRefusal(
                    "jsonld_invalid", f"JSON-LD block {block_index} is invalid JSON"))
                continue
            cursor = 0
            node_offsets: dict[tuple[tuple[str, ...], str], tuple[int, int]] = {}
            for path, type_surface, name, schema_vocab in _walk_jsonld(document):
                mention_ref = mention_lookup(name)
                if not mention_ref:
                    refusals.append(TypeExtractionRefusal(
                        "mention_unresolved",
                        f"JSON-LD type {type_surface!r} names {name!r}, but no existing mention was bound",
                        path))
                    continue
                if not schema_vocab:
                    refusals.append(TypeExtractionRefusal(
                        "unsupported_type_vocabulary",
                        f"JSON-LD type {type_surface!r} is not explicitly bound to schema.org",
                        path))
                    continue
                # A single JSON-LD node may declare several @type values for the
                # same name. Reuse that node's verified name span; advance the cursor
                # only when binding a different node.
                node_key = (path[:-1], name)
                offset = node_offsets.get(node_key)
                if offset is None:
                    offset = _json_name_offset(raw, name, cursor)
                    if offset is None:
                        refusals.append(TypeExtractionRefusal(
                            "mention_surface_not_source_addressable",
                            f"could not verify an unescaped source span for JSON-LD name {name!r}",
                            path))
                        continue
                    cursor = offset[1]
                    node_offsets[node_key] = offset
                signals.append(TypeSignal(
                    source_vocab="schema.org", surface=type_surface,
                    mention_ref=str(mention_ref),
                    structural_path=(f"jsonld[{block_index}]",) + path,
                    observation_refs=(observation_ref,), evidence_refs=(observation_ref,),
                    producer_ref=self.producer_jsonld, tenant_id=tenant_id,
                ))

        meta: dict[str, str] = {}
        for tag in _META.finditer(html):
            attrs = _attrs(tag.group("attrs"))
            key = (attrs.get("property") or attrs.get("name") or "").casefold()
            value = attrs.get("content", "").strip()
            if key and value:
                meta[key] = value
        if meta.get("og:type"):
            refusals.append(TypeExtractionRefusal(
                "document_type_requires_document_mention",
                "OpenGraph og:type describes the retrieved page, not the person named by "
                "og:title; no document-level Mention exists for this TypeSignal",
                ("meta", "og:type"),
            ))

        unique = {}
        for signal in signals:
            unique.setdefault(signal.signal_id, signal)
        return TypeExtractionReport(tuple(unique.values()), tuple(refusals))


__all__ = ["StructuredTypeSignalExtractor", "TypeExtractionRefusal", "TypeExtractionReport"]
