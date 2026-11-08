"""Evidence-bearing observations of externally stated type terms (Feature 021, FR-035).

A TypeSignal records what one producer saw a source state about one mention. It is not a
TypeHypothesis, TypeAssertion, Entity, or admission decision. Cross-vocabulary proposals
remain TypeMappingCandidate values and require a separately recorded SemanticMapping before
they can be consumed as a mapped hypothesis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.relation_identity import canonical_material, digest128
from semantic.contracts import SemanticRef, content_key
from semantic.vocabularies import MatchPredicate, normalize_type_ref

TYPE_SIGNAL_ID_PREFIX = "TS-"


def _canonical_refs(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({normalize_type_ref(value) for value in values if normalize_type_ref(value)}))


@dataclass(frozen=True, slots=True)
class TypeMappingCandidate:
    """A proposed cross-vocabulary mapping; never a stored mapping or assertion."""
    source: str
    target: str
    match_type: MatchPredicate
    subject_scheme: SemanticRef = SemanticRef.EXTERNAL
    object_scheme: SemanticRef = SemanticRef.INTERNAL
    confidence: float = 0.0
    provenance: tuple[str, ...] = ()
    mapping_version: str = "1"
    created_by: str = ""
    evidence_refs: tuple[str, ...] = ()
    mapping_set_id: str = "type-mappings"
    mapping_set_version: str = "1"
    supersedes: tuple[str, ...] = ()
    mapping_candidate_ref: str = ""

    def __post_init__(self) -> None:
        source, target = normalize_type_ref(self.source), normalize_type_ref(self.target)
        if not source or not target:
            raise ValueError("type mapping candidate requires non-empty source and target refs")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "match_type", MatchPredicate(self.match_type))
        object.__setattr__(self, "subject_scheme", SemanticRef(self.subject_scheme))
        object.__setattr__(self, "object_scheme", SemanticRef(self.object_scheme))
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("type mapping candidate confidence must be in [0, 1]")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "provenance", _canonical_refs(tuple(self.provenance)))
        object.__setattr__(self, "evidence_refs", _canonical_refs(tuple(self.evidence_refs)))
        object.__setattr__(self, "supersedes", _canonical_refs(tuple(self.supersedes)))
        for name in ("mapping_version", "created_by", "mapping_set_id", "mapping_set_version"):
            value = str(getattr(self, name) or "").strip()
            if not value:
                raise ValueError(f"{name} is required on a type mapping candidate")
        derived_ref = self.content_key
        if self.mapping_candidate_ref and self.mapping_candidate_ref != derived_ref:
            raise ValueError("mapping_candidate_ref disagrees with the candidate content")
        object.__setattr__(self, "mapping_candidate_ref", derived_ref)

    def material(self) -> dict[str, Any]:
        return {
            "source": self.source, "target": self.target,
            "match_type": str(self.match_type),
            "subject_scheme": str(self.subject_scheme),
            "object_scheme": str(self.object_scheme),
            "confidence": self.confidence, "provenance": list(self.provenance),
            "mapping_version": self.mapping_version, "created_by": self.created_by,
            "evidence_refs": list(self.evidence_refs),
            "mapping_set_id": self.mapping_set_id,
            "mapping_set_version": self.mapping_set_version,
            "supersedes": list(self.supersedes),
        }

    @property
    def content_key(self) -> str:
        return content_key(self.material())

    def to_dict(self) -> dict[str, Any]:
        return {**self.material(),
                "mapping_candidate_ref": self.mapping_candidate_ref or self.content_key}


@dataclass(frozen=True, slots=True)
class TypeSignal:
    """One source-originated type statement about one already-addressed mention.

    Identity is derived from (tenant, producer, mention, source vocabulary, literal surface,
    structural path). Observation/evidence references and mapping candidates deliberately do
    not enter that identity: new provenance or a new mapping proposal revises interpretation
    of the same source observation, not the observation itself. source_vocab=None is the
    honest value for a detector that did not read a named external vocabulary.
    """
    source_vocab: str | None
    surface: str
    mention_ref: str
    structural_path: tuple[str, ...]
    observation_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    producer_ref: str
    tenant_id: str
    mapping_candidates: tuple[TypeMappingCandidate, ...] = ()
    signal_id: str = ""

    def __post_init__(self) -> None:
        source_vocab = normalize_type_ref(self.source_vocab) if self.source_vocab else None
        if source_vocab and source_vocab.casefold() in {"local", "internal", "regex", "ner"}:
            raise ValueError("source_vocab must be an external vocabulary or None; detector identity belongs in producer_ref")
        surface = str(self.surface or "")
        if not surface.strip():
            raise ValueError("TypeSignal surface must preserve a non-empty source term")
        mention_ref, producer_ref, tenant_id = (
            str(self.mention_ref or "").strip(),
            str(self.producer_ref or "").strip(),
            str(self.tenant_id or "").strip(),
        )
        if not mention_ref or not producer_ref or not tenant_id:
            raise ValueError("TypeSignal requires mention_ref, producer_ref and tenant_id")
        path = tuple(str(part) for part in self.structural_path)
        if not path or any(not part for part in path):
            raise ValueError("TypeSignal structural_path must name the source field path")
        candidates = tuple(self.mapping_candidates)
        if any(not isinstance(item, TypeMappingCandidate) for item in candidates):
            raise TypeError("mapping_candidates must contain TypeMappingCandidate values")
        object.__setattr__(self, "source_vocab", source_vocab)
        object.__setattr__(self, "surface", surface)
        object.__setattr__(self, "mention_ref", mention_ref)
        object.__setattr__(self, "producer_ref", producer_ref)
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "structural_path", path)
        object.__setattr__(self, "observation_refs", _canonical_refs(tuple(self.observation_refs)))
        object.__setattr__(self, "evidence_refs", _canonical_refs(tuple(self.evidence_refs)))
        object.__setattr__(self, "mapping_candidates",
                           tuple(sorted(candidates, key=lambda item: item.content_key)))
        derived = self.derived_signal_id()
        if self.signal_id and self.signal_id != derived:
            raise ValueError(f"TypeSignal signal_id {self.signal_id!r} disagrees with derived {derived!r}")
        object.__setattr__(self, "signal_id", derived)

    def identity_material(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id, "producer_ref": self.producer_ref,
            "mention_ref": self.mention_ref, "source_vocab": self.source_vocab,
            "surface": self.surface, "structural_path": list(self.structural_path),
        }

    def derived_signal_id(self) -> str:
        return TYPE_SIGNAL_ID_PREFIX + digest128(canonical_material(self.identity_material()))

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity_material(),
            "observation_refs": list(self.observation_refs),
            "evidence_refs": list(self.evidence_refs),
            "mapping_candidates": [item.to_dict() for item in self.mapping_candidates],
            "signal_id": self.signal_id, "schema_version": 1,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TypeSignal:
        candidates = tuple(
            TypeMappingCandidate(
                source=str(item["source"]), target=str(item["target"]),
                match_type=MatchPredicate(item["match_type"]),
                subject_scheme=SemanticRef(item.get("subject_scheme", SemanticRef.EXTERNAL)),
                object_scheme=SemanticRef(item.get("object_scheme", SemanticRef.INTERNAL)),
                confidence=float(item.get("confidence", 0.0)),
                provenance=tuple(item.get("provenance", ())),
                mapping_version=str(item.get("mapping_version", "1")),
                created_by=str(item.get("created_by", "unknown")),
                evidence_refs=tuple(item.get("evidence_refs", ())),
                mapping_set_id=str(item.get("mapping_set_id", "type-mappings")),
                mapping_set_version=str(item.get("mapping_set_version", "1")),
                supersedes=tuple(item.get("supersedes", ())),
                mapping_candidate_ref=str(item.get("mapping_candidate_ref", "")),
            )
            for item in payload.get("mapping_candidates", ())
        )
        return cls(
            source_vocab=payload.get("source_vocab"), surface=str(payload["surface"]),
            mention_ref=str(payload["mention_ref"]),
            structural_path=tuple(payload.get("structural_path", ())),
            observation_refs=tuple(payload.get("observation_refs", ())),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
            producer_ref=str(payload["producer_ref"]), tenant_id=str(payload["tenant_id"]),
            mapping_candidates=candidates, signal_id=str(payload.get("signal_id", "")),
        )


__all__ = ["TYPE_SIGNAL_ID_PREFIX", "TypeMappingCandidate", "TypeSignal"]
