"""Semantic contracts: the only vocabulary the core domain may share with ontologies.

Feature 017 (FR-005). The whole point of this module is what it deliberately
does **not** contain: no SKOS, SSSOM, SHACL, OAK or LinkML type appears here, and
none may be re-exported from :mod:`semantic`. The core domain speaks
:class:`SemanticRef`, :class:`RelationRef` and :class:`ValidationReport` and
nothing else, so an external vocabulary can be attached to the graph without ever
becoming the graph's language.

Two ideas carry the feature and are encoded structurally rather than by comment:

* **Open world.** A :class:`TypeAssertion` may name a type that no profile, pack
  or ontology declares. Nothing in this module validates a type against an
  allowlist, because there is no allowlist. Unknown is a first-class value.
* **Monotonic commitment.** :class:`SemanticStatus` is a ladder that only ever
  moves upward, and a :class:`TypeAssertion` is immutable and content-addressed.
  Asserting a stronger type adds a row; it never rewrites or removes the weaker
  one it was derived from (FR-004).

Validation is graded rather than boolean because "I could not evaluate this" and
"this is wrong" are different answers with different consequences, and collapsing
them is how platforms end up silently deleting real evidence. :class:`Verdict`
therefore has five states, and only ``INVALID`` and ``CONFLICTING`` ever indicate a
problem (FR-011).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from domain.relation_identity import digest128

__all__ = [
    "LOGICAL_ASSERTION_ID_PREFIX",
    "REVISION_ASSERTION_ID_PREFIX",
    "RelationRef",
    "SemanticRef",
    "SemanticStatus",
    "TypeAssertion",
    "TypeAssertionRevision",
    "TypeScope",
    "ValidationFinding",
    "ValidationReport",
    "ValidationStage",
    "Verdict",
    "content_key",
    "is_adverse",
    "type_assertion_revisions",
]

#: Prefix of "which typing claim this is" - shared by every revision of one
#: claim, mirroring ``RL-``/``RC-`` in :mod:`domain.relation_identity`. Distinct so a
#: typing claim is never confusable with a relation claim in a log line or a store.
LOGICAL_ASSERTION_ID_PREFIX = "TA-"

#: Prefix of "which revision of that typing claim this is".
REVISION_ASSERTION_ID_PREFIX = "TAR-"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def content_key(payload: Any) -> str:
    """Order-insensitive identity for a semantic payload, as 128-bit truncated SHA-256.

    Reuses the feature 016 identity convention (``domain.relation_identity``) so
    semantic objects and relational objects are addressed the same way in one
    graph instead of growing a second hashing dialect.
    """
    return digest128(_canonical(payload))


class SemanticRef(StrEnum):
    """How a semantic term is being referenced, never *what* it means.

    The value space is deliberately open: a caller may pass any string, and this
    enum classifies how to *treat* the reference. An unrecognised scheme is not
    an error (FR-001) - it is a new scheme, and the resolver declines to expand
    it rather than guessing.
    """

    INTERNAL = "internal"
    PROFILE = "profile"
    SKOS = "skos"
    EXTERNAL = "external"
    LOCAL = "local"
    UNRESOLVED = "unresolved"


class TypeScope(StrEnum):
    """Which layer of typing an assertion belongs to (FR-003).

    All four apply to one entity simultaneously and none overwrites another, so
    an entity can be ``core:Entity`` (observed), ``web:WebProfile`` (context),
    ``local:Influencer`` (a local hypothesis) and ``schema:Person`` (mapped) at
    the same time.
    """

    OBSERVED = "observed"
    INFERRED = "inferred"
    MAPPED = "mapped"
    CONTEXT = "context"


class SemanticStatus(StrEnum):
    """The commitment ladder: observed -> extracted -> inferred -> mapped -> validated -> resolved.

    Ordering is real and monotonic (FR-018). :meth:`rank` makes it machine
    checkable so a store can refuse a *downgrade* - a later, weaker claim cannot
    erase a stronger one that was already recorded. It can still coexist with it.
    """

    OBSERVED = "observed"
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    MAPPED = "mapped"
    VALIDATED = "validated"
    RESOLVED = "resolved"

    def rank(self) -> int:
        """Position on the ladder; higher is a stronger commitment."""
        return _STATUS_RANK[self]

    def at_least(self, other: SemanticStatus) -> bool:
        return self.rank() >= SemanticStatus(other).rank()

    def promoted_to(self, other: SemanticStatus) -> SemanticStatus | None:
        """The stronger of the two statuses, or ``None`` if that would be a downgrade."""
        candidate = SemanticStatus(other)
        return candidate if candidate.rank() > self.rank() else None


_STATUS_RANK: dict[SemanticStatus, int] = {
    SemanticStatus.OBSERVED: 0,
    SemanticStatus.EXTRACTED: 1,
    SemanticStatus.INFERRED: 2,
    SemanticStatus.MAPPED: 3,
    SemanticStatus.VALIDATED: 4,
    SemanticStatus.RESOLVED: 5,
}


class Verdict(StrEnum):
    """Graded validation outcome (FR-011).

    ``INVALID`` means contradicted and ``CONFLICTING`` means sources disagree.
    ``UNKNOWN`` and ``UNSUPPORTED`` mean the platform could not evaluate the
    claim: no rule covers it, or a required capability is unavailable. Both are
    explicitly **not** failures, which is what lets a missing SHACL library
    degrade safely instead of blocking a write.
    """

    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"


ADVERSE_VERDICTS = frozenset({Verdict.INVALID, Verdict.CONFLICTING})


def is_adverse(verdict: Verdict) -> bool:
    """True only for verdicts that indicate an actual problem.

    The single most important predicate in this module: it is what stops an
    *unevaluable* check from being reported as a failure, and it is the only
    thing a caller needs to decide whether to raise a finding (FR-012).
    """
    return Verdict(verdict) in ADVERSE_VERDICTS


class ValidationStage(StrEnum):
    """The fixed order validation runs in (FR-011).

    Each stage is independently evaluable, so an ``UNKNOWN`` at ``SEMANTIC``
    does not prevent ``TEMPORAL`` from still being checked and reported.
    """

    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    TEMPORAL = "temporal"
    PROVENANCE = "provenance"
    CROSS_SOURCE = "cross_source"
    GRAPH_LEVEL = "graph_level"

    def rank(self) -> int:
        return _STAGE_RANK[self]


_STAGE_RANK: dict[ValidationStage, int] = {
    ValidationStage.STRUCTURAL: 0,
    ValidationStage.SEMANTIC: 1,
    ValidationStage.TEMPORAL: 2,
    ValidationStage.PROVENANCE: 3,
    ValidationStage.CROSS_SOURCE: 4,
    ValidationStage.GRAPH_LEVEL: 5,
}


@dataclass(frozen=True)
class TypeAssertion:
    """One immutable, evidence-bearing typing claim about an entity, in two levels.

    This is the replacement for a single categorical ``Entity.schema_name``
    (FR-003). It is a *claim* about a type, carrying its own scope, status,
    context and evidence, so the same entity can hold several at once and each
    can be audited independently.

    Identity is deliberately two-level, mirroring :class:`domain.relation_claim.RelationClaim`
    rather than inventing a second versioning philosophy for the semantic layer:

    * ``logical_type_assertion_id`` answers *which typing claim this is* --
      (tenant, entity, type, scope). Every revision of that claim shares it, so
      "all states of this typing" is one lookup rather than a scan.
    * ``type_assertion_id`` answers *which revision* -- a content address over the
      whole claim including status, evidence, context, source and hypothesis.

    The earlier version of this class documented two things that contradicted each
    other: that it was "immutable and content-addressed", and that a higher-status
    assertion "updates rather than duplicates". Those are only consistent under a
    two-level id, which is why it has one. A promotion is now a new revision under
    the same logical claim, so the weaker earlier state is still on record
    (FR-004) and "immutable" and "no duplicates" both hold.

    ``raw_surface`` and ``hypothesis`` are what make FR-004 real rather than
    aspirational: the ladder from raw text to a mapped concept is reconstructable
    from this record alone, so a later mapping never has to overwrite anything to
    be recorded.
    """

    type_assertion_id: str = ""
    logical_type_assertion_id: str = ""
    tenant_id: str = "default-tenant"

    entity_ref: str = ""
    type_ref: str = ""
    type_scheme: SemanticRef = SemanticRef.INTERNAL

    scope: TypeScope = TypeScope.OBSERVED
    status: SemanticStatus = SemanticStatus.OBSERVED

    raw_surface: str = ""
    hypothesis: str = ""

    source_ref: str = ""
    extractor_ref: str = ""
    context_ref: str = ""
    profile_ref: str = ""
    mapping_ref: str = ""

    evidence_refs: tuple[str, ...] = ()

    valid_from: datetime | None = None
    valid_to: datetime | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type_scheme", SemanticRef(self.type_scheme))
        object.__setattr__(self, "scope", TypeScope(self.scope))
        object.__setattr__(self, "status", SemanticStatus(self.status))
        refs = {str(r) for r in self.evidence_refs}
        object.__setattr__(self, "evidence_refs", tuple(sorted(refs)))

    @property
    def logical_identity(self) -> tuple[str, str, str, str]:
        """(tenant, entity, type, scope) - which typing claim this is.

        Status is excluded on purpose: a promotion is a new *revision* of the same
        claim, not a new claim. Different scopes are different claims and both
        survive, which is what lets one entity be observed, inferred, mapped and
        context-typed at the same time (FR-003).
        """
        return (self.tenant_id, self.entity_ref, self.type_ref, str(self.scope))

    def logical_key(self) -> str:
        """Content address of :attr:`logical_identity`, shared by every revision."""
        return LOGICAL_ASSERTION_ID_PREFIX + content_key(list(self.logical_identity))

    def content_key(self) -> str:
        """Order-insensitive digest of the full revision, including its evidence."""
        return content_key(
            {
                "tenant": self.tenant_id,
                "entity": self.entity_ref,
                "type": self.type_ref,
                "scheme": str(self.type_scheme),
                "scope": str(self.scope),
                "status": str(self.status),
                "raw_surface": self.raw_surface,
                "hypothesis": self.hypothesis,
                "source": self.source_ref,
                "extractor": self.extractor_ref,
                "context": self.context_ref,
                "profile": self.profile_ref,
                "mapping": self.mapping_ref,
                "evidence": list(self.evidence_refs),
                "valid_from": str(self.valid_from) if self.valid_from else None,
                "valid_to": str(self.valid_to) if self.valid_to else None,
                "observed_at": str(self.observed_at) if self.observed_at else None,
            }
        )

    def with_id(self) -> TypeAssertion:
        """A copy carrying both content-addressed ids.

        Derivation is explicit rather than automatic in ``__post_init__`` so that
        construction stays a plain value operation. It matters because the two
        levels answer different questions: a promotion keeps the logical id and
        mints a new revision id, and a caller can see that happen rather than
        discovering rows that differ in a way they did not intend.
        """
        if self.type_assertion_id and self.logical_type_assertion_id:
            return self
        return replace(
            self,
            type_assertion_id=self.type_assertion_id or REVISION_ASSERTION_ID_PREFIX
            + self.content_key(),
            logical_type_assertion_id=self.logical_type_assertion_id or self.logical_key(),
        )

    def promoted(self, status: SemanticStatus) -> TypeAssertion:
        """A stronger version of this same claim, or the same object if not stronger.

        Returns ``self`` unchanged when the requested status is not an upgrade, so
        a caller can apply a promotion unconditionally without ever performing a
        destructive downgrade (FR-004).
        """
        stronger = self.status.promoted_to(status)
        if stronger is None:
            return self
        return replace(
            self,
            status=stronger,
            type_assertion_id="",
            logical_type_assertion_id="",
        )

    def carries_semantic_commitment(self) -> bool:
        """False for a mention recorded with no semantic interpretation yet.

        An assertion may exist with a raw surface and no type at all. That is a
        legitimate state, not a gap (FR-014): the context records the regime the
        assertion was interpreted under, and "we did not interpret it" is a
        recordable fact.
        """
        return bool(self.type_ref)


@dataclass(frozen=True)
class TypeAssertionRevision:
    """The revision chain of one typing claim, ordered by commitment strength.

    The semantic-layer counterpart of ``domain.relation_claim.RelationRevision``,
    and deliberately the same shape: one logical id, many revisions, the strongest
    last. A claim that was first observed and later mapped to an external concept
    has two revisions here, and both remain readable, which is the only way to
    answer "what did we believe about this entity at time T" (FR-018).
    """

    logical_type_assertion_id: str
    revisions: tuple[TypeAssertion, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "revisions",
            tuple(sorted(self.revisions, key=lambda rev: rev.status.rank())),
        )

    @property
    def current(self) -> TypeAssertion | None:
        """The strongest revision, or ``None`` for an empty chain (honest, not guessed)."""
        return self.revisions[-1] if self.revisions else None

    def ladder(self) -> tuple[SemanticStatus, ...]:
        """The commitment statuses present, weakest first."""
        return tuple(sorted({rev.status for rev in self.revisions}, key=lambda s: s.rank()))


def type_assertion_revisions(
    assertions: tuple[TypeAssertion, ...] | list[TypeAssertion],
    logical_type_assertion_id: str,
) -> TypeAssertionRevision:
    """Every revision of one typing claim, weakest commitment first."""
    matching = [
        assertion
        for assertion in assertions
        if assertion.logical_type_assertion_id == logical_type_assertion_id
        or assertion.logical_key() == logical_type_assertion_id
    ]
    return TypeAssertionRevision(
        logical_type_assertion_id=logical_type_assertion_id,
        revisions=tuple(matching),
    )


@dataclass(frozen=True)
class RelationRef:
    """A reference to a relation *operator*, never to a fixed relation ontology.

    The operator identity is ``(relation_type, schema_version)`` and that pair is
    all this type carries. There is deliberately no ``domain``, ``range`` or
    ``allowed_types`` field here: those are the operator's *contract* (bound in
    ``semantic.operators`` to the existing feature 016 ``RelationSchema``), and
    putting them on the reference would let a relation look well-typed before any
    contract was ever declared for it (FR-006).
    """

    relation_type: str
    schema_version: str = "1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_type", str(self.relation_type))
        object.__setattr__(self, "schema_version", str(self.schema_version))

    @property
    def identity(self) -> tuple[str, str]:
        return (self.relation_type, self.schema_version)

    def __str__(self) -> str:
        return f"{self.relation_type}@{self.schema_version}"


@dataclass(frozen=True)
class ValidationFinding:
    """A graded result attached to an assertion. It has no authority to delete (FR-012).

    Note what is absent: there is no ``severity`` field that a caller could map
    onto a rejection, and no ``fatal`` flag. The verdict is a statement about the
    check, and the finding travels *with* the assertion rather than gating it.
    """

    finding_id: str = ""
    tenant_id: str = "default-tenant"

    assertion_ref: str = ""
    stage: ValidationStage = ValidationStage.STRUCTURAL
    verdict: Verdict = Verdict.UNKNOWN

    code: str = ""
    message: str = ""
    constraint_ref: str = ""
    profile_ref: str = ""
    context_ref: str = ""
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", ValidationStage(self.stage))
        object.__setattr__(self, "verdict", Verdict(self.verdict))
        refs = {str(r) for r in self.evidence_refs}
        object.__setattr__(self, "evidence_refs", tuple(sorted(refs)))

    @property
    def is_adverse(self) -> bool:
        return is_adverse(self.verdict)

    def content_key(self) -> str:
        return content_key(
            {
                "tenant": self.tenant_id,
                "assertion": self.assertion_ref,
                "stage": str(self.stage),
                "verdict": str(self.verdict),
                "code": self.code,
                "constraint": self.constraint_ref,
                "evidence": list(self.evidence_refs),
            }
        )

    def with_id(self) -> ValidationFinding:
        """A copy carrying its own content-addressed ``finding_id``."""
        return replace(self, finding_id=self.content_key()) if not self.finding_id else self


@dataclass(frozen=True)
class ValidationReport:
    """The result of a layered validation pass, including passes that did not run.

    ``findings`` is ordered by stage rank so a consumer reads structural problems
    first, and the report is content-addressed so the same graph view validated
    under the same profile is provably the same report (constitution VII).
    """

    report_id: str = ""
    tenant_id: str = "default-tenant"

    target_ref: str = ""
    profile_ref: str = ""
    profile_version: str = ""
    mapping_set_version: str = ""

    findings: tuple[ValidationFinding, ...] = ()

    def __post_init__(self) -> None:
        ordered = sorted(
            self.findings,
            key=lambda f: (f.stage.rank(), f.finding_id or f.content_key()),
        )
        object.__setattr__(self, "findings", tuple(ordered))

    def at_stage(self, stage: ValidationStage) -> tuple[ValidationFinding, ...]:
        """Findings from one stage only, for a caller that evaluates stages itself."""
        wanted = ValidationStage(stage)
        return tuple(f for f in self.findings if f.stage is wanted)

    def verdict_for(self, stage: ValidationStage) -> Verdict:
        """The worst verdict at a stage, where *unevaluable* never counts as invalid.

        A stage with no findings is ``VALID`` only because nothing was checked -
        callers that care must use :meth:`unevaluated_stages` to tell the
        difference, which is why SC-9 needs both.
        """
        findings = self.at_stage(stage)
        if not findings:
            return Verdict.VALID
        for verdict in (Verdict.INVALID, Verdict.CONFLICTING, Verdict.UNKNOWN, Verdict.UNSUPPORTED):
            if any(f.verdict is verdict for f in findings):
                return verdict
        return Verdict.VALID

    def adverse_findings(self) -> tuple[ValidationFinding, ...]:
        """Only findings that indicate a real problem. Everything else is noise for alerting."""
        return tuple(f for f in self.findings if f.is_adverse)

    def unevaluated_stages(self) -> tuple[ValidationStage, ...]:
        """Stages that produced no finding at all - neither pass nor fail.

        This is the honest answer to "what did we not check?", and it is what stops
        a partial pass from being reported as full validation.
        """
        evaluated = {f.stage for f in self.findings}
        return tuple(s for s in ValidationStage if s not in evaluated)

    def content_key(self) -> str:
        return content_key(
            {
                "tenant": self.tenant_id,
                "target": self.target_ref,
                "profile": self.profile_ref,
                "profile_version": self.profile_version,
                "mapping_set": self.mapping_set_version,
                "findings": [f.content_key() for f in self.findings],
            }
        )

    def with_id(self) -> ValidationReport:
        """A copy carrying its own content-addressed ``report_id``."""
        return replace(self, report_id=self.content_key()) if not self.report_id else self
