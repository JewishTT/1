"""Structured-semantics parser adapter: JSON-LD / microdata / RDFa / meta (spec 007, T009/T011).

Uses extruct (BSD-3) for JSON-LD/microdata/microformat/RDFa and selectolax for
quick meta/OpenGraph tag reads. Every declared value surfaces as a
``source=structure`` mention with confidence 1.0; ``sameAs``/profile URLs are
typed evidence attributes on the produced person mention. Deterministic and
offline: extruct is a pure HTML→dict parser.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import extruct  # type: ignore[import-not-found]
from selectolax.parser import HTMLParser  # type: ignore[import-not-found]

from extractors.language import decode_bytes, detect_language
from extractors.types import ExtractionResult, NormalizedName, TypedMention
from parsers.registry import Finding

_PROFILE_HOSTS = ("github.com", "t.me", "vk.com", "linkedin.com", "x.com", "twitter.com", "instagram.com", "facebook.com", "telegram.me")
_STRUCTURED_MARKERS = ("application/ld+json", 'application/ld_json', "itemscope", "itemtype", "itemprop", "og:", "property=", "itemtype=", "rdfa")


@dataclass
class StructuredAdapter:
    name: str = "structured"
    content_types: tuple[str, ...] = ("text/html", "application/xhtml+xml")

    def can_parse(self, artifact) -> bool:
        text = _to_text(artifact)
        lowered = text.lower()
        return any(marker in lowered for marker in _STRUCTURED_MARKERS)

    def parse(self, artifact) -> list[Finding]:
        mentions = self._mentions(_to_text(artifact))
        return [
            Finding(kind=m.kind, value=m.value, offset=m.offset, meta={"extractor": "structured"})
            for m in mentions
        ]

    def extract(self, artifact) -> ExtractionResult:
        raw = _to_bytes(artifact)
        text, _ = decode_bytes(raw)
        mentions = self._mentions(text)
        lang = detect_language(" ".join(m.value for m in mentions)) if mentions else None
        for m in mentions:
            if m.lang is None:
                m.lang = lang
        return ExtractionResult(
            artifact_sha=hashlib.sha256(raw).hexdigest(),
            content_type="text/html",
            segments=[],
            mentions=mentions,
        )

    # -- internals ---------------------------------------------------------
    def _mentions(self, text: str) -> list[TypedMention]:
        out: list[TypedMention] = []
        try:
            data = extruct.extract(text, syntaxes=["json-ld", "microdata", "microformat", "rdfa"])
        except Exception:  # noqa: BLE001 - a malformed page never crashes the lane
            data = {"json-ld": [], "microdata": [], "microformat": [], "rdfa": []}
        for node in data.get("json-ld", []) or []:
            out += self._from_jsonld(node, text)
        for micro in data.get("microdata", []) or []:
            out += self._from_micro(micro, text)
        out += self._from_meta(text)
        return _dedup(out)

    def _from_jsonld(self, node: dict, text: str) -> list[TypedMention]:
        if not isinstance(node, dict):
            return []
        node_type = _as_list(node.get("@type"))
        mentions: list[TypedMention] = []
        if "Person" in node_type:
            mentions += self._person(node, text)
        elif "Organization" in node_type:
            mentions += self._org(node, text)
        elif "PostalAddress" in node_type:
            mentions += self._address(node, text)
        works_for = node.get("worksFor")
        if works_for and isinstance(works_for, dict) and "Person" not in node_type:
            mentions += self._org(works_for, text)
        return mentions

    def _person(self, node: dict, text: str) -> list[TypedMention]:
        name = _first_text(node.get("name"))
        if not name:
            return []
        same_as = _as_urls(node.get("sameAs"))
        mention = TypedMention(
            kind="person",
            value=name,
            offset=_offset_of(text, name),
            end_offset=_offset_of(text, name) + len(name.encode("utf-8")),
            extractor="structured",
            source="structure",
            confidence=1.0,
            evidence=_evidence_for(same_as),
            normalized=NormalizedName(canonical=name, transforms=["structure"]),
        )
        return [mention, *self._contact_mentions(node, text)]

    def _org(self, node: dict, text: str) -> list[TypedMention]:
        name = _first_text(node.get("name"))
        if not name:
            return []
        evidence: dict = {}
        if isinstance(node.get("address"), dict):
            locality = _first_text(node["address"].get("addressLocality"))
            if locality:
                evidence["address_locality"] = locality
        m = match_text_kind("org", name, text)
        m.evidence.update(evidence)
        return [m]

    def _address(self, node: dict, text: str) -> list[TypedMention]:
        out = []
        locality = _first_text(node.get("addressLocality"))
        if locality:
            out.append(match_text_kind("place", locality, text))
        country = _first_text(node.get("addressCountry"))
        if country:
            out.append(match_text_kind("place", country, text))
        return out

    def _contact_mentions(self, node: dict, text: str) -> list[TypedMention]:
        out = []
        raw_email = _first_text(node.get("email")) or ""
        if raw_email and "@" in raw_email:
            email = raw_email.removeprefix("mailto:").strip()
            if email:
                out.append(match_text_kind("email", email, text))
        phone = _first_text(node.get("telephone"))
        if phone and phone.strip("+ 0123456789-()"):
            out.append(match_text_kind("phone", phone, text))
        address = node.get("address")
        if isinstance(address, dict) and _first_text(address.get("addressLocality")):
            out.append(match_text_kind("place", _first_text(address["addressLocality"]), text))
        return out

    def _from_micro(self, micro: dict, text: str) -> list[TypedMention]:
        if not isinstance(micro, dict):
            return []
        props = micro.get("properties", {})
        if not isinstance(props, dict):
            return []
        name = props.get("name")
        if not name:
            return []
        kind = _micro_kind(micro.get("type"))
        if kind is None:
            return []
        m = match_text_kind(kind, name, text)
        if m.confidence == 1.0:
            return [m]
        return []

    def _from_meta(self, text: str) -> list[TypedMention]:
        out: list[TypedMention] = []
        try:
            tree = HTMLParser(text)
        except Exception:  # noqa: BLE001 - broken HTML => meta read is skipped
            return out
        author = _meta(tree, "name", "author")
        if author:
            out.append(
                TypedMention(
                    kind="person",
                    value=author,
                    offset=_offset_of(text, author),
                    end_offset=_offset_of(text, author) + len(author.encode("utf-8")),
                    extractor="structured",
                    source="structure",
                    confidence=1.0,
                    evidence={"meta_source": "meta.author"},
                )
            )
        og_title = _meta(tree, "property", "og:title")
        og_type = _meta(tree, "property", "og:type")
        first = _meta(tree, "property", "profile:first_name")
        last = _meta(tree, "property", "profile:last_name")
        if og_type == "profile" and (first or last):
            name = " ".join(x for x in (last, first) if x)
            if name:
                out.append(
                    TypedMention(
                        kind="person",
                        value=name,
                        offset=_offset_of(text, name),
                        end_offset=_offset_of(text, name) + len(name.encode("utf-8")),
                        extractor="structured",
                        source="structure",
                        confidence=1.0,
                        evidence={"meta_source": "og.profile"},
                    )
                )
        elif og_title:
            out.append(
                TypedMention(
                    kind="person",
                    value=og_title,
                    offset=_offset_of(text, og_title),
                    end_offset=_offset_of(text, og_title) + len(og_title.encode("utf-8")),
                    extractor="structured",
                    source="structure",
                    confidence=1.0,
                    evidence={"meta_source": "og.title"},
                )
            )
        return out


def _has_type(micro: dict, wanted: str) -> bool:
    return any(isinstance(t, dict) and t.get("type", "") == wanted for t in micro.get("type", []))


def _micro_kind(type_spec) -> str | None:
    """Map a microdata itemtype (string or dict form) to an entity kind.

    extruct returns ``{"type": "https://schema.org/Person", ...}``; the JSON-LD
    plant produces dict types. Both forms are accepted; unknown types → None
    (the mention is not guessed).
    """
    types = [type_spec] if isinstance(type_spec, str) else (
        type_spec if isinstance(type_spec, list) else []
    )
    for entry in types:
        label = entry.get("type") if isinstance(entry, dict) else str(entry)
        if label.endswith("Person"):
            return "person"
        if "Organization" in label:
            return "org"
        if label.endswith(("Place", "City")):
            return "place"
    return None


def _evidence_for(urls: list[str]) -> dict:
    if not urls:
        return {"sameAs": []}
    profiles = [u for u in urls if any(host in u for host in _PROFILE_HOSTS)]
    return {
        "sameAs": urls,
        "profile_urls": profiles,
    }


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_urls(value) -> list[str]:
    return [str(u) for u in _as_list(value) if isinstance(u, str) and u.startswith(("http", "tg://"))]


def _first_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return next((v for v in value if isinstance(v, str) and v.strip()), "")
    return ""


def _first_text_or(value) -> str:
    return _first_text(value)


def match_text_kind(kind: str, value: str, text: str) -> TypedMention:
    offset = _offset_of(text, value)
    return TypedMention(
        kind=kind,
        value=value,
        offset=offset,
        end_offset=offset + len(value.encode("utf-8")),
        extractor="structured",
        source="structure",
        confidence=1.0,
    )


def _offset_of(text: str, needle: str) -> int:
    idx = text.find(needle)
    if idx < 0:
        return 0
    return len(text[:idx].encode("utf-8"))


def _meta(tree, key, value: str) -> str:
    for node in tree.css(f"meta[{key}='{value}']"):
        content = node.attributes.get("content", "").strip()
        if content:
            return content
    return ""


def _to_text(artifact) -> str:
    return _to_bytes(artifact).decode("utf-8", errors="replace")


def _to_bytes(artifact) -> bytes:
    if isinstance(artifact, (bytes, bytearray)):
        return bytes(artifact)
    if isinstance(artifact, str):
        return artifact.encode("utf-8")
    return b""


def _dedup(mentions: list[TypedMention]) -> list[TypedMention]:
    seen: dict[tuple[str, str], TypedMention] = {}
    for m in sorted(mentions, key=lambda x: (x.offset, x.kind, x.value)):
        key = (m.kind, m.value)
        if key not in seen:
            seen[key] = m
    return [seen[k] for k in sorted(seen, key=lambda k: (seen[k].offset, seen[k].kind))]