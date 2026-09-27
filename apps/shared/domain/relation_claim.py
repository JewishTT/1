"""Relation claim: the first-class relation record (feature 016, T024).

Contract is ``specs/016-relation-evidence-graph-fabric/data-model.md`` section 4
with ``docs/adr/0023-relation-identity-and-arity.md`` and ``docs/adr/0024``.

A relation is a *claim*, never truth (I-3), and it is admitted only with an
evidence context (FR-007, I-12). Identity is two-level and lives in
:mod:`domain.relation_claim`'s sibling :mod:`domain.relation_identity`: every
revision of one relation shares ``logical_relation_id``, and distinct content
always takes a distinct ``relation_id``, so a correction is a revision rather
than an overwrite (FR-003, I-11).

Two counts are kept apart on purpose: ``publication_count`` is how many
observations were published, ``independent_source_count`` is how many source
families stand behind them. Two articles syndicating one press release is two
publications and one source, and conflating them would grade evidence on
volume. The counts are stored separately and no single number is computed from
them (constitution IV).

Construction rejects the ten breaches of ``data-model.md`` section 4.2 — each
with a stable snake_case ``code`` — so a malformed claim cannot exist to be
stored, and the context/identity layers re-derive rather than trust.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from domain.relation_identity import (
    RelationArityMode,
    canonical_material,
    digest128,
)
from domain.temporal_worldline import DEFAULT_CONFIDENCE


class RelationContractError(ValueError):
    """A claim cannot be constructed from these fields.

    A ``ValueError`` (as ``data-model.md`` specifies) carrying the stable
    snake_case ``code`` the validation layer reports, in the spirit of
    ``domain.ConstraintViolation`` so one caller can switch on either.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class RelationStatus(StrEnum):
    """Lifecycle of one revision. A non-active revision is kept, never deleted."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    CONTRADICTED = "contradicted"
    QUARANTINED = "quarantined"


class EvidenceGrade(StrEnum):
    """Evidence grade as a label — never as a number fused from its parts.

    - STRONG: two or more independent sources, complete context;
    - MODERATE: one independent source, or degraded completeness;
    - WEAK: a single observation, or partial context;
    - UNGRADED: no grade could be computed (honest, I-3).
    """

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNGRADED = "ungraded"


def _iso(value: Any) -> str | None:
    """One timestamp as canonical text (``None`` = honestly unknown)."""
    if value is None or value == "":
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _moment(value: Any) -> datetime | None:
    """Parse a stored timestamp back, accepting a ``datetime`` unchanged."""
    if value is None or value == "":
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


@dataclass(frozen=True)
class RelationRoleBinding:
    """One named participant of a relation (``person``, ``organization``, …).

    ``member_class`` is the *declared* class; whether it is permitted is the
    semantic layer's call, not construction's.
    """

    role: str
    member_ref: str
    member_class: str = ""

    def __post_init__(self) -> None:
        if not self.role:
            raise RelationContractError("empty_role", "role binding requires a role name")

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "member_ref": self.member_ref, "member_class": self.member_class}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RelationRoleBinding:
        return cls(
            role=str(payload["role"]),
            member_ref=str(payload["member_ref"]),
            member_class=str(payload.get("member_class", "")),
        )


def check_role_bindings(
    role_bindings: Sequence[RelationRoleBinding],
    *,
    allow_repeated_member: bool = False,
) -> None:
    """Enforce the binding rules of ``data-model.md`` section 3.

    A role name must be non-empty, one role may not bind two members, and one
    member may not occupy two roles unless the schema declares
    ``allow_repeated_member=True``. Claims call this with the strict default;
    the schema registry passes its own flag when it admits a self-referential
    shape.
    """
    by_role: dict[str, str] = {}
    by_member: dict[str, str] = {}
    for binding in role_bindings:
        if not binding.role:
            raise RelationContractError("empty_role", "role binding requires a role name")
        if binding.role in by_role:
            raise RelationContractError(
                "duplicate_role",
                f"role {binding.role!r} binds two members: "
                f"{by_role[binding.role]!r} and {binding.member_ref!r}",
            )
        by_role[binding.role] = binding.member_ref
        held = by_member.get(binding.member_ref)
        if held is not None and not allow_repeated_member:
            raise RelationContractError(
                "duplicate_member",
                f"member {binding.member_ref!r} occupies two roles: {held!r} and {binding.role!r}",
            )
        by_member[binding.member_ref] = binding.role


@dataclass(frozen=True)
class RelationClaim:
    """One revision of one relation, with its evidence and provenance.

    Field order follows ``data-model.md`` section 4.2 exactly, because it is
    also the order the store, the event payload and the serialised content hash
    read. Reference collections are canonicalised on construction, so two
    claims that differ only in the order a producer collected their refs are one
    claim (I-11).
    """

    relation_id: str
    logical_relation_id: str
    revision_number: int
    relation_type: str
    arity_mode: RelationArityMode
    subject_ref: str
    object_ref: str
    role_bindings: tuple[RelationRoleBinding, ...] = ()

    valid_from: datetime | None = None
    valid_to: datetime | None = None
    observed_at: datetime | None = None
    published_at: datetime | None = None
    known_from: datetime | None = None
    known_until: datetime | None = None

    assertion_refs: tuple[str, ...] = ()
    observation_refs: tuple[str, ...] = ()
    context_ref: str = ""

    source_independence_groups: tuple[tuple[str, ...], ...] = ()
    extraction_version: str = ""
    normalization_version: str = ""
    ontology_version: str = ""
    schema_version: str = ""

    status: RelationStatus = RelationStatus.ACTIVE
    confidence: float = DEFAULT_CONFIDENCE
    evidence_grade: EvidenceGrade = EvidenceGrade.UNGRADED
    tenant_id: str = "default-tenant"
    investigation_id: str = ""

    created_by: str = ""
    supersedes: str = ""
    contradicts: tuple[str, ...] = ()
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arity_mode", RelationArityMode(self.arity_mode))
        object.__setattr__(self, "status", RelationStatus(self.status))
        object.__setattr__(self, "evidence_grade", EvidenceGrade(self.evidence_grade))

        if self.subject_ref == self.object_ref:
            raise RelationContractError(
                "self_loop",
                f"{self.relation_type or 'relation'} relates {self.subject_ref!r} to itself",
            )
        if not self.relation_type:
            raise RelationContractError("missing_relation_type", "relation requires a type")
        if not self.context_ref:
            raise RelationContractError(
                "missing_context_ref",
                "relation requires an evidence context ref (I-12, FR-007)",
            )
        if self.arity_mode is RelationArityMode.NARY and len(self.role_bindings) < 2:
            raise RelationContractError(
                "insufficient_members",
                f"nary relation needs at least two members, got {len(self.role_bindings)}",
            )
        nary = self.arity_mode is RelationArityMode.NARY
        members = [binding.member_ref for binding in self.role_bindings]
        if nary and len(set(members)) != len(members):
            raise RelationContractError(
                "duplicate_member",
                f"nary members must be distinct after role canonicalisation: {members}",
            )
        if self.arity_mode is RelationArityMode.DIRECTED and self.role_bindings:
            raise RelationContractError(
                "role_binding_on_directed",
                "directed relations take no role bindings; the endpoints are the members",
            )
        check_role_bindings(self.role_bindings)
        if (
            self.valid_to is not None
            and self.valid_from is not None
            and self.valid_to < self.valid_from
        ):
            raise RelationContractError(
                "inverted_validity",
                f"valid_to {self.valid_to.isoformat()} precedes "
                f"valid_from {self.valid_from.isoformat()}",
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise RelationContractError(
                "confidence_out_of_range",
                f"confidence must be within [0.0, 1.0], got {self.confidence}",
            )
        if self.revision_number < 1:
            raise RelationContractError(
                "invalid_revision_number",
                f"revision_number must be >= 1, got {self.revision_number}",
            )
        if self.supersedes and self.supersedes == self.relation_id:
            raise RelationContractError(
                "self_supersession",
                f"relation {self.relation_id} cannot supersede itself",
            )

        object.__setattr__(
            self,
            "role_bindings",
            tuple(
                sorted(self.role_bindings, key=lambda binding: (binding.role, binding.member_ref))
            ),
        )
        object.__setattr__(self, "assertion_refs", tuple(sorted(set(self.assertion_refs))))
        object.__setattr__(self, "observation_refs", tuple(sorted(set(self.observation_refs))))
        object.__setattr__(self, "contradicts", tuple(sorted(set(self.contradicts))))
        object.__setattr__(
            self,
            "source_independence_groups",
            tuple(sorted({tuple(sorted(set(group))) for group in self.source_independence_groups})),
        )

    @property
    def content_hash(self) -> str:
        """128-bit content address of every field except this hash (FR-005, I-11).

        Computed over the same serialised set ``to_dict`` publishes, so two
        claims with identical content are byte-identical and a re-write is
        idempotent rather than a second relation.
        """
        return digest128(canonical_material(self._material()))

    @property
    def independent_source_count(self) -> int:
        """How many source families stand behind the claim (FR-034).

        Deliberately not the publication count: repeated publication is not
        corroboration, and the two are stored separately (constitution IV).
        """
        return len(self.source_independence_groups)

    @property
    def publication_count(self) -> int:
        """How many observations were published for the claim.

        Kept apart from :attr:`independent_source_count` — never conflated.
        """
        return len(self.observation_refs)

    def is_active_at(self, ts: datetime) -> bool:
        """Whether the validity window covers ``ts`` (half-open at both ends)."""
        starts = self.valid_from is None or self.valid_from <= ts
        ends = self.valid_to is None or ts < self.valid_to
        return bool(starts and ends)

    def to_dict(self) -> dict[str, Any]:
        """The full claim record, refs only, plus its content hash (I-5)."""
        return {**self._material(), "content_hash": self.content_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RelationClaim:
        """Rebuild a claim from its own record; missing keys take the defaults."""
        data = dict(payload)
        data.pop("content_hash", None)
        return cls(
            relation_id=str(data["relation_id"]),
            logical_relation_id=str(data["logical_relation_id"]),
            revision_number=int(data.get("revision_number", 1)),
            relation_type=str(data.get("relation_type", "")),
            arity_mode=RelationArityMode(data.get("arity_mode", RelationArityMode.DIRECTED)),
            subject_ref=str(data.get("subject_ref", "")),
            object_ref=str(data.get("object_ref", "")),
            role_bindings=tuple(
                RelationRoleBinding.from_dict(binding)
                for binding in data.get("role_bindings") or ()
            ),
            valid_from=_moment(data.get("valid_from")),
            valid_to=_moment(data.get("valid_to")),
            observed_at=_moment(data.get("observed_at")),
            published_at=_moment(data.get("published_at")),
            known_from=_moment(data.get("known_from")),
            known_until=_moment(data.get("known_until")),
            assertion_refs=tuple(str(ref) for ref in data.get("assertion_refs") or ()),
            observation_refs=tuple(str(ref) for ref in data.get("observation_refs") or ()),
            context_ref=str(data.get("context_ref", "")),
            source_independence_groups=tuple(
                tuple(str(ref) for ref in group)
                for group in data.get("source_independence_groups") or ()
            ),
            extraction_version=str(data.get("extraction_version", "")),
            normalization_version=str(data.get("normalization_version", "")),
            ontology_version=str(data.get("ontology_version", "")),
            schema_version=str(data.get("schema_version", "")),
            status=RelationStatus(data.get("status", RelationStatus.ACTIVE)),
            confidence=float(data.get("confidence", DEFAULT_CONFIDENCE)),
            evidence_grade=EvidenceGrade(data.get("evidence_grade", EvidenceGrade.UNGRADED)),
            tenant_id=str(data.get("tenant_id", "default-tenant")),
            investigation_id=str(data.get("investigation_id", "")),
            created_by=str(data.get("created_by", "")),
            supersedes=str(data.get("supersedes", "")),
            contradicts=tuple(str(ref) for ref in data.get("contradicts") or ()),
            created_at=_moment(data.get("created_at")),
        )

    def _material(self) -> dict[str, Any]:
        """The serialised field set identity and ``content_hash`` are taken over."""
        return {
            "relation_id": self.relation_id,
            "logical_relation_id": self.logical_relation_id,
            "revision_number": self.revision_number,
            "relation_type": self.relation_type,
            "arity_mode": str(self.arity_mode),
            "subject_ref": self.subject_ref,
            "object_ref": self.object_ref,
            "role_bindings": [binding.to_dict() for binding in self.role_bindings],
            "valid_from": _iso(self.valid_from),
            "valid_to": _iso(self.valid_to),
            "observed_at": _iso(self.observed_at),
            "published_at": _iso(self.published_at),
            "known_from": _iso(self.known_from),
            "known_until": _iso(self.known_until),
            "assertion_refs": list(self.assertion_refs),
            "observation_refs": list(self.observation_refs),
            "context_ref": self.context_ref,
            "source_independence_groups": [
                list(group) for group in self.source_independence_groups
            ],
            "extraction_version": self.extraction_version,
            "normalization_version": self.normalization_version,
            "ontology_version": self.ontology_version,
            "schema_version": self.schema_version,
            "status": str(self.status),
            "confidence": self.confidence,
            "evidence_grade": str(self.evidence_grade),
            "tenant_id": self.tenant_id,
            "investigation_id": self.investigation_id,
            "created_by": self.created_by,
            "supersedes": self.supersedes,
            "contradicts": list(self.contradicts),
            "created_at": _iso(self.created_at),
        }


@dataclass(frozen=True)
class RelationRevision:
    """The ordered revision chain of one relation; the last element is current."""

    logical_relation_id: str
    revisions: tuple[RelationClaim, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "revisions",
            tuple(sorted(self.revisions, key=lambda claim: claim.revision_number)),
        )

    @property
    def current(self) -> RelationClaim | None:
        """The latest revision, or ``None`` for an empty chain (honest, I-3)."""
        return self.revisions[-1] if self.revisions else None

    @property
    def revision_numbers(self) -> tuple[int, ...]:
        return tuple(claim.revision_number for claim in self.revisions)


def revisions_of(claims: Iterable[RelationClaim], logical_relation_id: str) -> RelationRevision:
    """The revision chain of one relation, ordered by ``revision_number``.

    Every revision of one relation shares ``logical_relation_id``, so "all
    versions of this relation" is a single filter rather than a scan (ADR-0023).
    """
    matching = [claim for claim in claims if claim.logical_relation_id == logical_relation_id]
    return RelationRevision(logical_relation_id=logical_relation_id, revisions=tuple(matching))


__all__ = [
    "DEFAULT_CONFIDENCE",
    "EvidenceGrade",
    "RelationClaim",
    "RelationContractError",
    "RelationRevision",
    "RelationRoleBinding",
    "RelationStatus",
    "check_role_bindings",
    "revisions_of",
]
