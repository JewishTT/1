"""Relation extraction with immutable provenance (deterministic, rule-based).

Mentions are isolated facts ("an email was seen here"); relations are the
claims an analyst actually reasons over ("this host *operates_in* this domain",
"this actor *exploits* this CVE"). This module bridges the two and attaches
provenance to every edge, so a relation can always be traced back to the exact
WARC record, the exact character span and the extractor that produced it.

Two relation families are derived, and both are honest about their strength:

``predicate`` relations
    A cue phrase in the text ("reported by", "exploits", "operates in") links the
    nearest typed mention before it to the nearest typed mention after it. The
    cue vocabulary is curated and closed — an unknown phrasing yields no edge
    rather than a guessed one.

``attribution`` relations
    Every typed mention is bound to the document it was read from. These edges
    are structural rather than semantic, carry lower confidence, and are what
    lets the admission lane attach an evidence ref to any claim downstream.

Provenance is a frozen value (:class:`DocumentContext` + :class:`Span`), so an
edge cannot be re-pointed at different evidence after the fact: tampering would
require constructing a new relation, which shows up as a different
``relation_id``. Relation ids are content-derived, so the same archive always
yields the same ids (I-11).

Refs only (I-5): relations carry identifiers, offsets and digests — never the
document text they were read from.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# Mention-kind groups. Predicates bind to these, so "exploits" accepts a
# vulnerability as its object but never an email address.
CONTACT_KINDS = frozenset({"email"})
ENDPOINT_KINDS = frozenset({"url", "domain", "ipv4", "gateway_ip"})
INFRA_KINDS = ENDPOINT_KINDS
VULN_KINDS = frozenset({"cve"})
HASH_KINDS = frozenset({"sha256", "md5", "strong_token"})
WALLET_KINDS = frozenset({"crypto_address"})

# Confidence per predicate family. A curated, closed vocabulary means these are
# stated constants rather than fitted weights — nothing here was learned.
PREDICATE_BASE_CONFIDENCE: dict[str, float] = {
    "exploits": 0.85,
    "affects": 0.8,
    "operates_in": 0.75,
    "reported_by": 0.75,
    "has_contact": 0.7,
    "owned_by": 0.7,
    "hacked_by": 0.7,
    "located_in": 0.65,
    "uses": 0.6,
    "references": 0.6,
    "part_of": 0.6,
    "linked_to": 0.55,
    "runs_on": 0.55,
    "pays_to": 0.6,
}

ATTRIBUTION_PREDICATE = "mentions"
ATTRIBUTION_CONFIDENCE = 0.5

@dataclass(frozen=True)
class DocumentContext:
    """The document an edge was read from — refs only, no payload (I-5)."""

    document_id: str
    record_id: str = ""
    source_uri: str = ""
    warc_date: str | None = None
    body_sha256: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "record_id": self.record_id,
            "source_uri": self.source_uri,
            "warc_date": self.warc_date,
            "body_sha256": self.body_sha256,
        }


@dataclass(frozen=True)
class Span:
    """A typed mention occurrence: what it is and exactly where it sat."""

    kind: str
    value: str
    start: int
    end: int
    extractor: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "value": self.value,
            "start": self.start,
            "end": self.end,
            "extractor": self.extractor,
        }


@dataclass(frozen=True)
class Relation:
    """One subject → predicate → object edge with its provenance."""

    relation_id: str
    predicate: str
    subject_kind: str
    subject_value: str
    object_kind: str
    object_value: str
    confidence: float
    context: DocumentContext
    spans: tuple[Span, ...] = ()
    evidence_id: str = ""

    @property
    def document_id(self) -> str:
        return self.context.document_id

    def to_dict(self) -> dict[str, object]:
        return {
            "relation_id": self.relation_id,
            "predicate": self.predicate,
            "subject_kind": self.subject_kind,
            "subject_value": self.subject_value,
            "object_kind": self.object_kind,
            "object_value": self.object_value,
            "confidence": self.confidence,
            "context": self.context.to_dict(),
            "spans": [s.to_dict() for s in self.spans],
            "evidence_id": self.evidence_id,
        }


# (cue phrase, predicate, allowed subject kinds, allowed object kinds).
# ``None`` means "any kind". Cues match case-insensitively on word boundaries,
# so a cue inside a URL or an address cannot fire.
_CUE_SPECS: tuple[tuple[str, str, frozenset[str] | None, frozenset[str] | None], ...] = (
    ("exploits", "exploits", None, VULN_KINDS),
    ("exploit", "exploits", None, VULN_KINDS),
    ("is affected by", "affects", VULN_KINDS, None),
    ("affects", "affects", VULN_KINDS, INFRA_KINDS),
    ("operates in", "operates_in", INFRA_KINDS, INFRA_KINDS),
    ("operates from", "operates_in", INFRA_KINDS, INFRA_KINDS),
    ("based in", "located_in", INFRA_KINDS, INFRA_KINDS),
    ("located in", "located_in", INFRA_KINDS, INFRA_KINDS),
    ("hosted in", "located_in", INFRA_KINDS, INFRA_KINDS),
    ("reported by", "reported_by", None, CONTACT_KINDS),
    ("reported", "reported_by", None, CONTACT_KINDS),
    ("contact", "has_contact", None, CONTACT_KINDS),
    ("email", "has_contact", None, CONTACT_KINDS),
    ("mailbox", "has_contact", None, CONTACT_KINDS),
    ("owned by", "owned_by", INFRA_KINDS, None),
    ("hacked by", "hacked_by", INFRA_KINDS, None),
    ("part of", "part_of", None, INFRA_KINDS),
    ("linked to", "linked_to", None, None),
    ("references", "references", None, INFRA_KINDS),
    ("cites", "references", None, INFRA_KINDS),
    ("uses", "uses", None, INFRA_KINDS),
    ("runs on", "runs_on", None, INFRA_KINDS),
    ("pays to", "pays_to", WALLET_KINDS, WALLET_KINDS),
)

# Longest cues first so "operates in" is preferred over any shorter overlap.
_CUE_PATTERNS: tuple[
    tuple[re.Pattern[str], str, frozenset[str] | None, frozenset[str] | None], ...
] = tuple(
    (re.compile(rf"(?<!\w){re.escape(cue)}(?!\w)", re.IGNORECASE), predicate, subj, obj)
    for cue, predicate, subj, obj in sorted(_CUE_SPECS, key=lambda spec: -len(spec[0]))
)

SUBJECT_DOCUMENT = "document"


def relation_id_for(
    predicate: str,
    subject_kind: str,
    subject_value: str,
    object_kind: str,
    object_value: str,
    document_id: str,
) -> str:
    """Content-derived relation id: same evidence → same id, always (I-11)."""
    stable = f"{document_id}|{subject_kind}|{subject_value}|{predicate}|{object_kind}|{object_value}"
    return "REL-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class _Candidate:
    """An in-flight edge before ids are assigned."""

    predicate: str
    subject_kind: str
    subject_value: str
    object_kind: str
    object_value: str
    confidence: float
    spans: tuple[Span, ...]
    order: int


def _span_of(mention) -> Span:
    start = int(getattr(mention, "offset", 0) or 0)
    value = str(getattr(mention, "value", ""))
    return Span(
        kind=str(getattr(mention, "kind", "")),
        value=value,
        start=start,
        end=start + len(value),
        extractor=str((getattr(mention, "attrs", None) or {}).get("extractor", "")),
    )


def _allowed(kinds: frozenset[str] | None, span: Span) -> bool:
    return kinds is None or span.kind in kinds


def _nearest_before(spans: list[Span], cue_start: int, window: int) -> Span | None:
    """Closest eligible span ending before the cue, within ``window`` chars."""
    best: Span | None = None
    for span in spans:
        if span.end <= cue_start <= span.end + window and (best is None or span.end > best.end):
            best = span
    return best


def _nearest_after(spans: list[Span], cue_end: int, window: int) -> Span | None:
    """Closest eligible span starting after the cue, within ``window`` chars."""
    best: Span | None = None
    for span in spans:
        if cue_end <= span.start <= cue_end + window and (best is None or span.start < best.start):
            best = span
    return best


class RelationExtractor:
    """Derive subject → predicate → object edges from text plus typed mentions.

    Deterministic and dependency-light: mentions are supplied by the caller (or
    taken from the pattern ``ExtractorRegistry``), and every decision is a table
    lookup or a nearest-neighbour scan over offsets. No model, no clock, no
    network.
    """

    def __init__(self, *, window: int = 120, include_attribution: bool = True) -> None:
        self.window = window
        self.include_attribution = include_attribution

    def extract(self, text: str, context: DocumentContext, mentions=None) -> list[Relation]:
        """Return the relations found in ``text``, deterministically ordered.

        Ordering is ``(first span start, predicate, subject, object)``, so the
        same text always yields the same list in the same order.
        """
        spans = self._spans(text, mentions)
        found: list[_Candidate] = []
        order = 0
        for pattern, predicate, subject_kinds, object_kinds in _CUE_PATTERNS:
            base = PREDICATE_BASE_CONFIDENCE.get(predicate, 0.5)
            for cue in pattern.finditer(text):
                subject = _nearest_before(spans, cue.start(), self.window)
                obj = _nearest_after(spans, cue.end(), self.window)
                if subject is None or obj is None:
                    continue
                if not _allowed(subject_kinds, subject) or not _allowed(object_kinds, obj):
                    continue
                if subject.value == obj.value and subject.kind == obj.kind:
                    # A cue flanked by a single mention is not a relation.
                    continue
                found.append(
                    _Candidate(
                        predicate=predicate,
                        subject_kind=subject.kind,
                        subject_value=subject.value,
                        object_kind=obj.kind,
                        object_value=obj.value,
                        confidence=_scored(base, cue.start(), cue.end(), subject, obj),
                        spans=(subject, obj),
                        order=order,
                    )
                )
                order += 1
        if self.include_attribution:
            found.extend(self._attributions(spans, context.document_id, order))
        return self._finalize(found, context)

    def _spans(self, text: str, mentions) -> list[Span]:
        if mentions is None:
            from extractors.registry import ExtractorRegistry

            mentions = ExtractorRegistry().extract(text)
        spans = [_span_of(m) for m in mentions]
        # Sort by position, then kind/value, so "nearest" is never ambiguous.
        return sorted(spans, key=lambda s: (s.start, s.end, s.kind, s.value))

    def _attributions(self, spans: list[Span], document_id: str, order: int) -> list[_Candidate]:
        return [
            _Candidate(
                predicate=ATTRIBUTION_PREDICATE,
                subject_kind=SUBJECT_DOCUMENT,
                subject_value=document_id,
                object_kind=span.kind,
                object_value=span.value,
                confidence=ATTRIBUTION_CONFIDENCE,
                spans=(span,),
                order=order + index,
            )
            for index, span in enumerate(spans)
        ]

    def _finalize(self, candidates: list[_Candidate], context: DocumentContext) -> list[Relation]:
        """Deduplicate identical edges, keeping every distinct span as provenance."""
        merged: dict[tuple[str, str, str, str, str], list[Span]] = {}
        best: dict[tuple[str, str, str, str, str], _Candidate] = {}
        for cand in candidates:
            key = (
                cand.predicate,
                cand.subject_kind,
                cand.subject_value,
                cand.object_kind,
                cand.object_value,
            )
            if key not in best or cand.confidence > best[key].confidence:
                best[key] = cand
            seen = merged.setdefault(key, [])
            for span in cand.spans:
                if span not in seen:
                    seen.append(span)

        relations = [
            Relation(
                relation_id=relation_id_for(
                    key[0], key[1], key[2], key[3], key[4], context.document_id
                ),
                predicate=key[0],
                subject_kind=key[1],
                subject_value=key[2],
                object_kind=key[3],
                object_value=key[4],
                confidence=round(best[key].confidence, 3),
                context=context,
                spans=tuple(sorted(merged[key], key=lambda s: (s.start, s.kind, s.value))),
            )
            for key in best
        ]
        return sorted(
            relations,
            key=lambda r: (
                r.spans[0].start if r.spans else 0,
                r.predicate,
                r.subject_value,
                r.object_value,
            ),
        )


def _scored(base: float, cue_start: int, cue_end: int, subject: Span, obj: Span) -> float:
    """Base confidence decayed by how far the endpoints sit from the cue.

    The *farther* endpoint governs, not the nearer one: a cue glued to one
    mention but 400 characters from the other is weak evidence, and taking the
    minimum distance would let the close endpoint mask that. The decay is
    bounded so confidence can never reach zero.
    """
    distance = max(cue_start - subject.end, obj.start - cue_end)
    decay = 1.0 - min(0.3, max(0, distance) / 400.0)
    return max(0.05, min(1.0, base * decay))
