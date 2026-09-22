"""Typed mention + extraction result models (spec 007, data-model.md).

``TypedMention`` extends the registry's minimal ``Mention`` with the full
deterministic-extraction contract: byte offsets, extractor id, language hint,
honest ``source`` tier, `normalized` canonical form / transform chain,
``evidence`` attributes (sameAs / profile_urls / contact_hashes / coords /
co_occurrence) and the producing dictionary's version stamp (FR-8).

Invariants (data-model.md): mentions are data+evidence only — never resolved
entities (I-2); nothing here uses wall-clock time, randomness or the network.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

# Honest degradation tiers: structure > coords/context > morph > pattern (FR-4).
# Higher value = more reliable source. Pattern-only matches keep ``source=pattern``
# and a reduced confidence but are never dropped.
SOURCE_ORDER: dict[str, int] = {
    "structure": 4,
    "coords": 3,
    "context": 3,
    "morph": 2,
    "dictionary": 2,
    "pattern": 1,
}


@dataclass
class NormalizedName:
    """Canonical form + transform chain for name mentions (data-model.md)."""

    canonical: str
    latin: str | None = None
    given: str | None = None
    family: str | None = None
    patronymic: str | None = None
    transforms: list[str] = field(default_factory=list)
    hypothesis: bool = False


@dataclass
class TypedMention:
    """A deterministic entity mention extracted from one artifact."""

    kind: str
    value: str
    offset: int = 0
    end_offset: int = 0
    extractor: str = ""
    lang: str | None = None
    source: str = "pattern"
    confidence: float = 1.0
    normalized: NormalizedName | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    dictionary: str | None = None
    lang_pack: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Deterministic dict form: keys sorted, sub-models flattened."""
        out: dict[str, Any] = {
            "kind": self.kind,
            "value": self.value,
            "offset": self.offset,
            "end_offset": self.end_offset,
            "extractor": self.extractor,
            "lang": self.lang,
            "source": self.source,
            "confidence": self.confidence,
            "evidence": _sorted_dict(self.evidence if self.evidence else {}),
        }
        if self.dictionary is not None:
            out["dictionary"] = self.dictionary
        if self.lang_pack is not None:
            out["lang_pack"] = self.lang_pack
        if self.normalized is not None:
            out["normalized"] = dataclasses.asdict(self.normalized)
        return _sorted_dict(out)


@dataclass
class ExtractionResult:
    """The output lane result for one artifact (data-model.md)."""

    artifact_sha: str
    content_type: str
    segments: list[Any] = field(default_factory=list)
    mentions: list[TypedMention] = field(default_factory=list)
    quarantined: bool = False
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _sorted_dict(
            {
                "artifact_sha": self.artifact_sha,
                "content_type": self.content_type,
                "quarantined": self.quarantined,
                "reason": self.reason,
                "segments": [
                    {
                        "text": getattr(s, "text", str(s)),
                        "offset": getattr(s, "offset", 0),
                        "kind": getattr(s, "kind", "text"),
                        "lang": getattr(s, "lang_hint", None),
                        "meta": _sorted_dict(getattr(s, "meta", {})),
                    }
                    for s in self.segments
                ],
                "mentions": [m.to_dict() for m in self.mentions],
            }
        )


def _sorted_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Deterministic nested dict sort: sorted keys, no duplicate values."""
    return {
        k: (_sorted_dict(v) if isinstance(v, dict) else v) for k, v in sorted(data.items())
    }