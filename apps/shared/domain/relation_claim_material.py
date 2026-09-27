"""Claim material: the unadmitted value, and the three operations around it.

Feature 018, T013 / T014 / T015 / T016, D3 / D5, FR-010 ... FR-013, SC-6 / SC-7.

**The defect this module exists to close.** Before 018, :meth:`domain.relation_candidate.
RelationCandidate.to_claim` built a :class:`domain.relation_claim.RelationClaim` *and* admitted
it in one act, refusing unless the reading was already ``SUPPORTED``. The running path was
therefore ``CLAIM -> VALIDATION -> ADMISSION``: :class:`semantic.validation.LayeredValidator`
inspected an object that had already been admitted, and the word "claim" denoted a potential
assertion, an immutable value and an admitted assertion simultaneously (FR-012). A validator that
can only ever see admitted claims cannot examine a hypothesis, which is exactly what a
task-scoped consumer needs later.

**One value, three states, three names.**

======================  ==================================  ==============================
state                   name                               produced by
======================  ==================================  ==============================
a potential assertion   :class:`RelationClaimMaterial`     :func:`build`
an examination          :class:`semantic.contracts.\\        :func:`validate`
                        ValidationReport`
an admitted assertion   :class:`domain.relation_claim.\\     :func:`admit`
                        RelationClaim`
======================  ==================================  ==============================

No name appears twice in that table, and no function returns a value from a different row. That
is the whole of SC-7, and it is checkable by reading the three signatures rather than by reading
prose.

**"Unadmitted" is structural, not documentary.** The obvious cheap way to do this is to give
``RelationClaim`` a flag called ``admitted`` and set it to ``False`` here. This module does the
opposite and takes the distinction apart in the type:

* :class:`RelationClaimMaterial` has **no ``status`` field at all**, and no ``known_from``,
  ``known_until``, ``supersedes``, ``contradicts`` or ``created_at`` either. Those six are
  exactly the fields that only come into being *after* something is admitted, and they are named
  in :data:`COMMITTED_ONLY_FIELDS`. :func:`verify_material_field_partition` runs at import and
  fails if one of them is ever added, so "a material cannot be in the graph" is a property of
  the class rather than a promise in this docstring.
* It is **not** a subclass of :class:`RelationClaim` and holds no claim instance, so
  ``isinstance(material, RelationClaim)`` is ``False`` and every API in the platform that
  requires a committed claim refuses it. :func:`require_committed` is the typed refusal for the
  case where that would otherwise be an ``AttributeError`` at some later read.
* The state is still *nameable*, via the derived read-only
  :attr:`RelationClaimMaterial.material_state` returning :class:`MaterialState.UNADMITTED` - a
  one-member enum whose value is not a :class:`domain.relation_claim.RelationStatus` value, so a
  report or a log line can say what the object is without borrowing the committed vocabulary. It
  is a property and not a field, so no caller can construct an admitted material.

**Material is the same kind of object, minus the commitment.** :class:`RelationClaim.__post_init__`
is not weakened, skipped or relaxed here. Every material constructs a transient
:class:`RelationClaim` mirror of its own fields (see :meth:`RelationClaimMaterial._contract_claim`),
so the full contract - context ref required, directed arity forbids role bindings, n-ary demands
them, inverted validity refused, tenant and revision range checked - runs on material exactly as
it runs on a claim, and a :class:`domain.relation_claim.RelationContractError` from a shape
breach is the *same* error a claim would have raised. The mirror exists for a second reason as
well: :func:`domain.relation_identity.recompute_identity` takes a ``RelationClaim``, and FR-011
requires the material's ids to be derivable before anything is admitted, so the mirror is how
they are derived.

**The identity invariant.** ``status``, ``confidence``, ``evidence_grade``, ``known_from``,
``known_until``, ``supersedes``, ``contradicts`` and ``created_at`` are all in
:data:`domain.relation_identity.MUTABLE_PROJECTION_FIELDS` - they are excluded from identity
deliberately. Every field that *is* identity material is present on the material, by the same
import-time check. The consequence is load-bearing and is asserted in :func:`admit` rather than
assumed:

.. code-block:: text

    admit(material, report).relation_id == material.relation_id
    admit(material, report).logical_relation_id == material.logical_relation_id

Admission is therefore not an identity event. The ids are settled at :func:`build`, are quotable
on the material, are what a :class:`~semantic.contracts.ValidationReport` targets, and survive
admission unchanged - so a report written against material is a report written against the claim
that will exist, and a store can key on the id before the row does.

**Admission is the only committing step, and it only refuses.** :func:`admit` is the sole
producer of a :class:`RelationClaim` in this module, and it produces one only when the reading's
disposition is admissible *and* the operator's own policy does not exclude it. It reads the
report and never writes to it, deletes from it, or re-derives it; it reads the material and never
mutates it (the material is frozen and :func:`admit` only reads its fields). A finding therefore
informs admission without ever being able to create, rewrite or remove a claim (FR-013) - and
under the default :attr:`~semantic.operators.DomainRangePolicy.WARN` an adverse finding is
recorded and admission proceeds, which is 017's "a failure can be a finding and not a deletion"
carried across the new boundary.

**No I/O, no clock, no network, no LLM.** ``observed_at``, ``created_at`` and every other
timestamp are supplied by the caller, so replaying an admission reproduces the same ids
(constitution VI, VII).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from domain.evidence_context import EvidenceContext
from domain.relation_candidate import (
    ADMISSIBLE_CANDIDATE_STATUSES,
    CandidateContractError,
    CandidateNotAdmissible,
    CandidateStatus,
    RelationCandidate,
)
from domain.relation_claim import (
    DEFAULT_CONFIDENCE,
    EvidenceGrade,
    RelationClaim,
    RelationRoleBinding,
    RelationStatus,
)
from domain.relation_identity import (
    IDENTITY_MATERIAL_FIELDS,
    LOGICAL_IDENTITY_MATERIAL_FIELDS,
    RelationArityMode,
    canonical_material,
    digest128,
    recompute_identity,
)
from semantic.contracts import (
    TypeAssertion,
    ValidationFinding,
    ValidationReport,
    ValidationStage,
)
from semantic.operators import RelationOperator
from semantic.profiles import ProfileResolution
from semantic.regime import SemanticRegime
from semantic.validation import (
    MAX_GRAPH_NODES,
    STAGE_ORDER,
    LayeredValidator,
    MaterialisationDecision,
    decide_materialisation,
)

__all__ = [
    "COMMITTED_ONLY_FIELDS",
    "AdmissionBlocked",
    "MaterialContractError",
    "MaterialNotAdmitted",
    "MaterialState",
    "RelationClaimMaterial",
    "admit",
    "build",
    "replace_claim_ids",
    "require_committed",
    "unvalidated_report",
    "validate",
    "verify_material_field_partition",
    "verify_material_identity",
]


def _iso(value: Any) -> str | None:
    """One timestamp as canonical text (``None`` = honestly unknown)."""
    if value is None or value == "":
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


class MaterialContractError(ValueError):
    """Material cannot be built or refused from these fields.

    A ``ValueError`` carrying the stable snake_case ``code``, in the spirit of
    :class:`domain.relation_claim.RelationContractError` and
    :class:`domain.relation_candidate.CandidateContractError` so one caller can switch on any of
    the three. Shape breaches of a *claim* are deliberately **not** reported through this type:
    they surface as :class:`domain.relation_claim.RelationContractError` from the contract
    mirror, because a material that breaks a claim's rules has broken the same rule and reporting
    it under a second error type would give one breach two spellings.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class MaterialNotAdmitted(MaterialContractError):
    """A value was required to be a committed claim and is not one.

    Raised by :func:`require_committed`, which is what a consumer calls when the *only* thing it
    can do with the value is read it out of the graph. The distinction it protects is FR-012's:
    a material is examinable and quotable and must never be read as though it were admitted, and
    an ``AttributeError`` several layers away from the mistake is not a refusal anyone can act
    on. The message names what was actually supplied, because "expected a claim" without
    "received material ``RC-…``" sends the reader looking in the wrong place.
    """

    def __init__(self, value: object, required_for: str) -> None:
        self.received_type = type(value).__name__
        super().__init__(
            "material_where_claim_required",
            f"{required_for} requires a committed RelationClaim, but a "
            f"{self.received_type} was supplied"
            + (f" (relation_id={value.relation_id!r})" if hasattr(value, "relation_id") else ""),
        )


class AdmissionBlocked(MaterialContractError):
    """Admission refused because an adverse finding met a blocking operator policy.

    The refusal is *scoped*, and the recorded fields say so: :attr:`decision` is a
    :class:`semantic.validation.MaterialisationDecision`, which states that this operator does
    not admit this material into **its own** view, and :attr:`blocking_findings` names every
    finding that motivated it. Nothing was deleted and the material is untouched - it is still
    quotable, still reportable, and another operator with a different policy reaches a different
    and equally correct answer about the same value (FR-013, 017 SC-4).

    Distinct from :class:`domain.relation_candidate.CandidateNotAdmissible`, which is about the
    *extraction disposition* and is raised unchanged so the deprecated
    :meth:`domain.relation_candidate.RelationCandidate.to_claim` keeps the exception type its
    callers already catch.
    """

    def __init__(
        self,
        material: RelationClaimMaterial,
        decision: MaterialisationDecision,
        blocking_findings: Sequence[ValidationFinding],
    ) -> None:
        self.relation_id = material.relation_id
        self.candidate_id = material.candidate_id
        self.decision = decision
        self.blocking_findings = tuple(blocking_findings)
        named = "; ".join(
            f"{finding.stage}/{finding.verdict}/{finding.code}"
            for finding in self.blocking_findings
        )
        super().__init__(
            "admission_blocked",
            f"material {material.relation_id} was not admitted: operator "
            f"{decision.operator_ref or '<undeclared>'} declares domain_range="
            f"{decision.policy} and {decision.scope_statement}. Blocking findings: {named}",
        )


class MaterialState(StrEnum):
    """The one state a :class:`RelationClaimMaterial` can be in.

    A single member, and the enum exists so a report, a log line or a store row can *name* the
    state without borrowing :class:`domain.relation_claim.RelationStatus`. None of these values is
    a ``RelationStatus`` value, so comparing the two strings is a mismatch rather than a
    plausible-looking equality.

    There is no member for ``ACTIVE``, ``SUPERSEDED``, ``RETRACTED``, ``CONTRADICTED`` or
    ``QUARANTINED`` because all five mean "this is in the graph", and material is not. Nor is
    there one for ``known_from`` / ``known_until`` / ``supersedes`` / ``contradicts`` /
    ``created_at``: those facts are written by :func:`admit` and do not exist before it.
    """

    UNADMITTED = "unadmitted"


#: Fields a :class:`RelationClaimMaterial` must never carry, checked at import by
#: :func:`verify_material_field_partition`.
#:
#: Each is a fact about a relation **in the graph**, and every one of them is absent for a stated
#: reason rather than by omission:
#:
#: - ``status`` - "which lifecycle state this claim is in". This is the load-bearing entry: it is
#:   the field whose presence says "this is committed", so its absence on material is what makes
#:   a material structurally unadmittable rather than merely labelled so.
#: - ``known_from`` / ``known_until`` - the knowledge axis, stamped when the platform learned of
#:   the assertion. A material's observation time is the extraction's ``observed_at``, which is a
#:   different axis (constitution V).
#: - ``supersedes`` / ``contradicts`` - links to *committed claims*. They cannot be resolved
#:   before admission because a claim that superseded or contradicted this reading does not exist
#:   yet; :func:`admit` accepts them for exactly that reason.
#: - ``created_at`` - wall clock of the write. A material has no write, and including a clock
#:   here would make a replayed admission mint a different record (constitution VII).
COMMITTED_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "known_from",
        "known_until",
        "supersedes",
        "contradicts",
        "created_at",
    }
)

#: Material fields whose value the contract mirror canonicalises, adopted on construction so a
#: material and the claim it becomes agree on ordering without two copies of the sort.
_CANONICALISED_FIELDS: tuple[str, ...] = (
    "role_bindings",
    "assertion_refs",
    "observation_refs",
    "source_independence_groups",
)


@dataclass(frozen=True)
class RelationClaimMaterial:
    """A candidate's resolved reading, complete enough to validate and not yet admitted.

    Frozen, tenant-scoped and self-consistent: construction derives both ids from the value's own
    contents through :func:`domain.relation_identity.recompute_identity`, so a material cannot
    exist carrying an id that disagrees with it, and :func:`verify_material_identity` re-derives
    and compares for a store that loads rows rather than builds them.

    The field list is :class:`domain.relation_claim.RelationClaim`'s field list minus
    :data:`COMMITTED_ONLY_FIELDS`, plus the three fields that say which reading this material
    came from (:attr:`candidate_id`, :attr:`logical_candidate_id`, :attr:`candidate_status`).
    Those three are what makes the refusal in :func:`admit` traceable to an extraction
    disposition rather than to an opaque boolean, and what keeps
    ``RelationClaim -> RelationCandidate`` walkable (SC-14). They are *not* identity material: an
    admitted claim's ids are unaffected by them, which is what lets a material be examined before
    anyone decided to admit it.

    Read-only lifecycle state is exposed as :attr:`material_state`, derived rather than stored, so
    it cannot be set and cannot hold a :class:`domain.relation_claim.RelationStatus` value.
    """

    relation_id: str = ""
    logical_relation_id: str = ""
    revision_number: int = 1
    relation_type: str = ""
    arity_mode: RelationArityMode = RelationArityMode.DIRECTED
    subject_ref: str = ""
    object_ref: str = ""
    role_bindings: tuple[RelationRoleBinding, ...] = ()

    valid_from: datetime | None = None
    valid_to: datetime | None = None
    observed_at: datetime | None = None
    published_at: datetime | None = None

    assertion_refs: tuple[str, ...] = ()
    observation_refs: tuple[str, ...] = ()
    context_ref: str = ""

    source_independence_groups: tuple[tuple[str, ...], ...] = ()
    extraction_version: str = ""
    normalization_version: str = ""
    ontology_version: str = ""
    schema_version: str = ""

    confidence: float = DEFAULT_CONFIDENCE
    evidence_grade: EvidenceGrade = EvidenceGrade.UNGRADED
    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    created_by: str = ""

    candidate_id: str = ""
    logical_candidate_id: str = ""
    candidate_status: CandidateStatus = CandidateStatus.PROPOSE

    def __post_init__(self) -> None:
        object.__setattr__(self, "arity_mode", RelationArityMode(self.arity_mode))
        object.__setattr__(self, "evidence_grade", EvidenceGrade(self.evidence_grade))
        object.__setattr__(self, "candidate_status", CandidateStatus(self.candidate_status))

        contract = self._contract_claim()
        for name in _CANONICALISED_FIELDS:
            object.__setattr__(self, name, getattr(contract, name))

        logical, revision = recompute_identity(contract)
        for carried, derived, label in (
            (self.logical_relation_id, logical, "logical_relation_id"),
            (self.relation_id, revision, "relation_id"),
        ):
            if carried and carried != derived:
                raise MaterialContractError(
                    "material_id_mismatch",
                    f"material carries {label}={carried!r} but its own content addresses to "
                    f"{derived!r}; a content address is derived, never trusted",
                )
        object.__setattr__(self, "logical_relation_id", logical)
        object.__setattr__(self, "relation_id", revision)

    @property
    def material_state(self) -> MaterialState:
        """Always :attr:`MaterialState.UNADMITTED`; derived, so it cannot be set otherwise."""
        return MaterialState.UNADMITTED

    @property
    def is_committed(self) -> bool:
        """Always ``False``.

        A hard-wired answer rather than a derived one, for the same reason
        :attr:`semantic.validation.MaterialisationDecision.is_adverse` is: the question has only
        one answer for this type, and a derived flag is a field someone could later make depend on
        something. It exists so a caller can ask without an ``isinstance`` check; the structural
        guarantee is that this class is not a :class:`domain.relation_claim.RelationClaim`.
        """
        return False

    @property
    def independent_source_count(self) -> int:
        """How many source families stand behind this reading (FR-034).

        Not the publication count, and never derived from it: one independence group with three
        publications is one source syndicated three times (constitution IV).
        """
        return len(self.source_independence_groups)

    @property
    def publication_count(self) -> int:
        """How many observations were published, kept apart from
        :attr:`independent_source_count`."""
        return len(self.observation_refs)

    @property
    def content_hash(self) -> str:
        """128-bit content address of every field except the two derived ids (FR-005, I-11).

        Taken over the same serialised set :meth:`to_dict` publishes, so two materials differing
        only in the order a producer collected their refs are one material, and re-running
        :func:`build` is idempotent rather than a second reading.
        """
        return digest128(canonical_material(self._material()))

    def is_active_at(self, ts: datetime) -> bool:
        """Whether the *hypothesised* window covers ``ts`` (half-open at both ends).

        Named for the temporal question it answers and not for a lifecycle state: on a material
        this asks when the reading claims things held, which is a fact about the hypothesis, not
        a statement that anything is in the graph.
        """
        starts = self.valid_from is None or self.valid_from <= ts
        ends = self.valid_to is None or ts < self.valid_to
        return bool(starts and ends)

    def to_dict(self) -> dict[str, Any]:
        """The full material record, refs only, plus its content hash (I-5).

        Deliberately emits no ``status`` and none of the other
        :data:`COMMITTED_ONLY_FIELDS`, so a serialised material cannot be replayed into a
        committed row by a store that maps fields by name.
        """
        return {**self._material(), "content_hash": self.content_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RelationClaimMaterial:
        """Rebuild a material from its own record; missing keys take the defaults.

        Any ``status`` or other :data:`COMMITTED_ONLY_FIELDS` key in ``payload`` is ignored rather
        than honoured, and :meth:`__post_init__` re-derives the ids and refuses a record whose
        carried ids do not follow from its contents, so a tampered or hand-edited row cannot be
        loaded as a consistent material.
        """
        data = {key: value for key, value in payload.items() if key not in COMMITTED_ONLY_FIELDS}
        data.pop("content_hash", None)
        return cls(
            relation_id=str(data.get("relation_id", "")),
            logical_relation_id=str(data.get("logical_relation_id", "")),
            revision_number=int(data.get("revision_number", 1)),
            relation_type=str(data.get("relation_type", "")),
            arity_mode=str(data.get("arity_mode", "directed")),
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
            confidence=float(data.get("confidence", DEFAULT_CONFIDENCE)),
            evidence_grade=EvidenceGrade(data.get("evidence_grade", EvidenceGrade.UNGRADED)),
            tenant_id=str(data.get("tenant_id", "default-tenant")),
            investigation_id=str(data.get("investigation_id", "")),
            created_by=str(data.get("created_by", "")),
            candidate_id=str(data.get("candidate_id", "")),
            logical_candidate_id=str(data.get("logical_candidate_id", "")),
            candidate_status=CandidateStatus(data.get("candidate_status", CandidateStatus.PROPOSE)),
        )

    def _contract_claim(self) -> RelationClaim:
        """A transient :class:`RelationClaim` mirror of this value, for the contract and the ids.

        Two jobs, and no third:

        1. **The contract.** :meth:`RelationClaim.__post_init__` is not weakened, mirrored or
           re-implemented here - it is *run*, on a claim whose fields are this material's fields.
           A material therefore refuses exactly the shapes a claim refuses, with the same
           :class:`domain.relation_claim.RelationContractError`.
        2. **The ids.** :func:`domain.relation_identity.recompute_identity` takes a
           ``RelationClaim`` and FR-011 requires the material's ids to be derivable before
           anything is admitted, so the mirror is what they are derived from.

        The mirror carries the dataclass default ``status`` and the committed-only fields at their
        defaults, and is discarded on return. That costs nothing: every one of them is in
        :data:`domain.relation_identity.MUTABLE_PROJECTION_FIELDS`, so none enters identity and
        the ids derived here are byte-identical to the ids :func:`admit` will produce.
        """
        return RelationClaim(
            relation_id="",
            logical_relation_id="",
            revision_number=self.revision_number,
            relation_type=self.relation_type,
            arity_mode=self.arity_mode,
            subject_ref=self.subject_ref,
            object_ref=self.object_ref,
            candidate_id=self.candidate_id,
            role_bindings=self.role_bindings,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            observed_at=self.observed_at,
            published_at=self.published_at,
            assertion_refs=self.assertion_refs,
            observation_refs=self.observation_refs,
            context_ref=self.context_ref,
            source_independence_groups=self.source_independence_groups,
            extraction_version=self.extraction_version,
            normalization_version=self.normalization_version,
            ontology_version=self.ontology_version,
            schema_version=self.schema_version,
            confidence=self.confidence,
            evidence_grade=self.evidence_grade,
            tenant_id=self.tenant_id,
            investigation_id=self.investigation_id,
            created_by=self.created_by,
        )

    def _material(self) -> dict[str, Any]:
        """The serialised field set the content hash is taken over (FR-005)."""
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
            "confidence": self.confidence,
            "evidence_grade": str(self.evidence_grade),
            "tenant_id": self.tenant_id,
            "investigation_id": self.investigation_id,
            "created_by": self.created_by,
            "candidate_id": self.candidate_id,
            "logical_candidate_id": self.logical_candidate_id,
            "candidate_status": str(self.candidate_status),
        }


def _moment(value: Any) -> datetime | None:
    """Parse a stored timestamp back, accepting a ``datetime`` unchanged."""
    if value is None or value == "":
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def verify_material_identity(material: RelationClaimMaterial) -> None:
    """Fail unless the carried ids are the ones the material's own content addresses.

    The tamper check a store runs on load, mirroring
    :func:`domain.relation_identity.detect_identity_forgery` and
    :func:`domain.relation_candidate.verify_candidate_identity`. Id derivation already happened in
    :meth:`RelationClaimMaterial.__post_init__`, so this is a re-derivation and comparison for a
    row that arrived from elsewhere - never a trust decision.
    """
    logical, revision = recompute_identity(material._contract_claim())
    if logical != material.logical_relation_id or revision != material.relation_id:
        raise MaterialContractError(
            "material_id_mismatch",
            f"material carries ({material.logical_relation_id!r}, {material.relation_id!r}) but "
            f"its own content addresses to ({logical!r}, {revision!r}); a content address is "
            "verified, never trusted",
        )


def verify_material_field_partition() -> None:
    """Fail if a committed-only field appears on material, or a claim field is unaccounted for.

    Called once at import, because "a material is not a claim" has to be true of the *type* and
    not merely of this file's prose - the failure mode is silent, and a reviewer who trusts a
    ``status`` that is really a material marker has been misled by a docstring. The partition is
    checked in both directions:

    * every name in :data:`COMMITTED_ONLY_FIELDS` is absent from the dataclass;
    * every :class:`domain.relation_claim.RelationClaim` field is either carried by material or
      declared committed-only, so nothing can be dropped without being accounted for;
    * every claim identity field is carried, which is the mechanical form of the identity
      invariant documented on this module - :func:`admit` asserts it at runtime as well.
    """
    present = {field.name for field in fields(RelationClaimMaterial)}
    leaked = sorted(present & COMMITTED_ONLY_FIELDS)
    if leaked:
        raise MaterialContractError(
            "committed_only_field_on_material",
            f"a material must not carry {leaked}: those are facts about a relation in the graph "
            "and come into being at admission, which is exactly what material is not. Write them "
            "on the argument of domain.relation_claim_material.admit instead",
        )
    claim_fields = {field.name for field in fields(RelationClaim)}
    unaccounted = sorted(claim_fields - present - COMMITTED_ONLY_FIELDS)
    if unaccounted:
        raise MaterialContractError(
            "unclassified_claim_field",
            f"RelationClaim fields that material neither carries nor declares committed-only: "
            f"{unaccounted}. Add each to the material or to COMMITTED_ONLY_FIELDS so the "
            "partition stays total",
        )
    missing = sorted((LOGICAL_IDENTITY_MATERIAL_FIELDS | IDENTITY_MATERIAL_FIELDS) - present)
    if missing:
        raise MaterialContractError(
            "identity_field_absent_from_material",
            f"material does not carry the claim identity fields {missing}, so its ids could not "
            "be derived before admission and admit would have to mint a different relation",
        )


verify_material_field_partition()


def build(
    candidate: RelationCandidate,
    *,
    subject_ref: str,
    object_ref: str,
    revision_number: int,
    evidence_grade: EvidenceGrade,
    tenant_id: str,
    role_bindings: Sequence[RelationRoleBinding] = (),
    assertion_refs: Sequence[str] = (),
    source_independence_groups: Sequence[Sequence[str]] = (),
    normalization_version: str = "",
    ontology_version: str = "",
    observed_at: datetime | None = None,
) -> RelationClaimMaterial:
    """Turn one candidate reading into an unadmitted, validatable value (FR-010, operation 1).

    Construction only. It takes no report, consults no policy, and its return type is not a
    :class:`domain.relation_claim.RelationClaim` - there is no path from here to a committed claim
    even in principle, which is what makes the next two operations separately callable.

    **The disposition is not consulted.** A ``PROPOSE`` reading builds into material exactly as a
    ``SUPPORTED`` one does, and the difference is expressed only in
    :attr:`RelationClaimMaterial.candidate_status` - a field :func:`admit` reads and
    :func:`validate` ignores. That is FR-011: a material which no admission would ever accept has
    to stay examinable, quotable and reportable, and it cannot be if construction is the gate.
    The guard is real, it is a genuine safety property, and it lives at
    :func:`admit` - which is why the deprecated
    :meth:`domain.relation_candidate.RelationCandidate.to_claim` still raises
    :class:`domain.relation_candidate.CandidateNotAdmissible` for a non-``SUPPORTED`` reading.
    A hypothesis nobody may admit is a thing to report on, not a thing to refuse to name.

    The keyword arguments are the same ones
    :meth:`domain.relation_candidate.RelationCandidate.to_claim` has always taken, and each is
    required exactly where the candidate genuinely cannot know the answer:

    * ``subject_ref`` / ``object_ref`` - the *resolved* participants. Required, and the single
      most load-bearing judgement here: a candidate names mentions, material names participants,
      and resolution happened after the candidate was written. Substituting the mention refs
      would put a mention into the claim's identity material and quietly break I-2.
    * ``revision_number`` - required. Defaulting it to ``1`` would invent a fact about the claim
      chain and a second admission of the same relation would collide.
    * ``evidence_grade`` - a derivation made outside this layer; grading is FR-025's work over
      resolved evidence, and it is not identity material, so a re-grade does not fork the
      relation.
    * ``tenant_id`` - required and cross-checked against the candidate's tenant, fail-closed
      (constitution IV). Raised as :class:`domain.relation_candidate.CandidateContractError`
      with code ``tenant_mismatch``, unchanged from ``to_claim``.
    * ``role_bindings`` - defaulted empty, correct for ``DIRECTED`` and ``UNDIRECTED`` and refused
      by the contract for ``NARY``. Not an invention: an n-ary material with no role bindings
      cannot be constructed, so an incomplete resolution fails closed here rather than being
      quietly accepted.
    * ``normalization_version`` / ``ontology_version`` - defaulted empty, recording "unknown"
      rather than copying a value the caller may not have. An operator with an undeclared version
      is reported ``UNDERDETERMINED`` (016 US4-4), not rejected, so a truthful gap is recoverable.
    * ``observed_at`` - defaults to the candidate's own ``observed_at``, a transcription of a
      caller-supplied value rather than an invention. Pass one to record when the reading was
      built rather than when it was extracted.
    * ``source_independence_groups`` - defaulted empty, which is a truthful "nothing independent
      backs this yet". Independence is computed across a claim set (FR-034) and cannot be derived
      from one candidate, and it is identity material, so two materials differing in what
      independently backs them are two relations.
    * ``assertion_refs`` - the resolved typing claims, which is what makes the material's identity
      material name the typing its participants rest on and the lineage chain walkable.

    Everything else is transcribed from the candidate: the operator identity, the arity mode, the
    context reference, the observation and evidence refs, the extraction method and version, the
    confidence, the investigation and the author.
    """
    if str(tenant_id) != candidate.tenant_id:
        raise CandidateContractError(
            "tenant_mismatch",
            f"candidate {candidate.candidate_id or '<unaddressed>'} belongs to tenant "
            f"{candidate.tenant_id!r} and cannot be built as {str(tenant_id)!r} "
            "(constitution IV)",
        )
    return RelationClaimMaterial(
        revision_number=revision_number,
        relation_type=candidate.relation_type,
        arity_mode=candidate.arity_mode,
        subject_ref=subject_ref,
        object_ref=object_ref,
        role_bindings=tuple(role_bindings),
        valid_from=candidate.temporal_hypothesis.valid_from,
        valid_to=candidate.temporal_hypothesis.valid_to,
        observed_at=observed_at if observed_at is not None else candidate.observed_at,
        assertion_refs=tuple(assertion_refs),
        observation_refs=tuple(
            dict.fromkeys((*candidate.observation_refs, *candidate.evidence_refs))
        ),
        context_ref=candidate.context_ref,
        source_independence_groups=tuple(
            tuple(sorted({str(ref) for ref in group if str(ref).strip()}))
            for group in source_independence_groups
            if tuple(str(ref) for ref in group)
        ),
        extraction_version=candidate.extractor_version,
        normalization_version=normalization_version,
        ontology_version=ontology_version,
        schema_version=candidate.schema_version,
        confidence=candidate.confidence,
        evidence_grade=evidence_grade,
        tenant_id=str(tenant_id),
        investigation_id=candidate.investigation_id,
        created_by=candidate.recorded_by,
        candidate_id=candidate.candidate_id,
        logical_candidate_id=candidate.logical_candidate_id,
        candidate_status=candidate.candidate_status,
    )


def validate(
    material: RelationClaimMaterial,
    *,
    operators: Mapping[str, RelationOperator] | None = None,
    resolution: ProfileResolution | None = None,
    type_assertions: Mapping[str, Sequence[TypeAssertion]] | None = None,
    contexts: Mapping[str, EvidenceContext] | None = None,
    claims: Iterable[RelationClaim] = (),
    regime: SemanticRegime | None = None,
    stages: Iterable[ValidationStage] = STAGE_ORDER,
    max_graph_nodes: int = MAX_GRAPH_NODES,
) -> ValidationReport:
    """Grade a material without admitting it, and without being able to (FR-011, operation 2).

    A thin module-level entry over :class:`semantic.validation.LayeredValidator`, whose widened
    input is what makes this call possible at all. Three properties are worth stating because
    they are the ones a future change could quietly break:

    * **It admits nothing.** The return type is
      :class:`semantic.contracts.ValidationReport` - a record, not a claim - and no code path in
      this function constructs a :class:`domain.relation_claim.RelationClaim`. The one
      relationship this module has to a committed claim is :func:`admit`, and this function does
      not call it.
    * **It requires no admission.** A material is enough: no disposition is read, no report is
      consulted, and the value the validator reads off the subject is the material's own derived
      id, which is already the id the claim will have. A ``PROPOSE`` reading validates, and so
      does one whose operator is set to exclude it from its own view - those are two different
      questions and this function answers the first.
    * **It does not write to the material.** The validator is a reader (017's property one), the
      material is frozen, and nothing here assigns to it.

    Every keyword mirrors :class:`~semantic.validation.LayeredValidator`'s own constructor, so
    the delegation is visible in the signature rather than hidden in the body. The omissions keep
    their honest consequences rather than gaining defaults: no ``operator`` for the relation type
    is ``UNKNOWN``/``operator_not_declared`` and no ``resolution`` means the profile-dependent
    checks are skipped rather than assumed.

    A committed claim is deliberately *not* accepted here - it is not this operation's subject -
    and is re-validated through :meth:`semantic.validation.LayeredValidator.evaluate` directly, so
    that the name ``validate`` keeps meaning the middle state of the lifecycle (SC-7).
    """
    return LayeredValidator(
        operators=operators,
        resolution=resolution,
        type_assertions=type_assertions,
        contexts=contexts,
        claims=claims,
        regime=regime,
        max_graph_nodes=max_graph_nodes,
    ).evaluate(material, stages=stages)


def admit(
    material: RelationClaimMaterial,
    report: ValidationReport,
    *,
    operator: RelationOperator | None = None,
    claim_status: RelationStatus = RelationStatus.ACTIVE,
    created_at: datetime | None = None,
    known_from: datetime | None = None,
    known_until: datetime | None = None,
    supersedes: str = "",
    contradicts: Sequence[str] = (),
) -> RelationClaim:
    """The one operation that commits (FR-010 operation 3, FR-013).

    The only producer of a :class:`domain.relation_claim.RelationClaim` in this module, and the
    only place a material stops being one. Two refusals, both typed, both naming their reason:

    * :class:`domain.relation_candidate.CandidateNotAdmissible` when the reading the material
      came from is not in :data:`domain.relation_candidate.ADMISSIBLE_CANDIDATE_STATUSES`. The
      disposition guard lives here rather than in :func:`build` so a hypothesis that may never be
      admitted can still be built, validated, quoted and reported - and it is raised as the
      *existing* type, so the deprecated ``to_claim`` keeps the exception its callers catch.
    * :class:`AdmissionBlocked` when the report carries an adverse finding **and** the operator's
      own :attr:`~semantic.operators.DomainRangePolicy` treats such a violation as blocking, which
      is :attr:`~semantic.operators.DomainRangePolicy.EXCLUDE_FROM_VIEW` and nothing else.

    **Both halves of that second refusal are load-bearing, and neither alone would be right.**
    Under the default ``WARN`` an adverse finding is recorded and admission proceeds - 017's "a
    failure can be a finding and not a deletion" carried across the new boundary. And with no
    adverse finding there is nothing for the policy to act on: ``EXCLUDE_FROM_VIEW`` is scoped to
    *one operator's materialised view* of a *domain/range violation*, so honouring it as a veto on
    entering the graph would turn a projection decision into an admission gate and re-create the
    gate 017 exists to remove. :func:`semantic.validation.decide_materialisation` still answers
    the separate question "does this operator's view carry it", and that answer is unaffected -
    this function is not where a view is decided.

    The report must be *about this material*: ``target_ref`` equal to the material's own derived
    id and ``tenant_id`` equal to its tenant, both checked fail-closed before anything else
    (constitution IV). A report produced for a different reading is a report about different
    evidence, and admitting against it would attach this material's lifecycle to somebody else's
    findings.

    **It does not delete or rewrite the material.** The material is frozen, every field read here
    is read, and the returned claim is a *new* object: admission is not an edit of the
    hypothesis, it is the decision to hold a second value beside it. The report is consulted and
    discarded - it is neither stored on the claim nor used to alter it, because FR-013 forbids a
    finding from rewriting anything.

    **The ids do not move.** ``status``, ``known_from``, ``known_until``, ``supersedes``,
    ``contradicts``, ``created_at``, ``confidence`` and ``evidence_grade`` are all
    :data:`domain.relation_identity.MUTABLE_PROJECTION_FIELDS`, and every identity field is
    carried by the material (checked at import). So the claim's ids equal the material's, and
    that is asserted here rather than assumed - if a future field ever breaks the partition, this
    raises instead of quietly minting a second relation.
    """
    if report.target_ref and report.target_ref != material.relation_id:
        raise MaterialContractError(
            "report_target_mismatch",
            f"report {report.report_id or '<unaddressed>'} targets "
            f"{report.target_ref!r}, but the material is {material.relation_id!r}; a report "
            "about a different reading cannot decide this one's admission",
        )
    if report.tenant_id != material.tenant_id:
        raise MaterialContractError(
            "report_tenant_mismatch",
            f"report is from tenant {report.tenant_id!r} and the material belongs to "
            f"{material.tenant_id!r}; cross-tenant admission is refused fail-closed "
            "(constitution IV)",
        )
    if material.candidate_status not in ADMISSIBLE_CANDIDATE_STATUSES:
        raise CandidateNotAdmissible(
            material.candidate_id, material.candidate_status, ADMISSIBLE_CANDIDATE_STATUSES
        )

    adverse = report.adverse_findings()
    decision = decide_materialisation(operator, findings=adverse)
    if adverse and decision.refused:
        raise AdmissionBlocked(material, decision, adverse)

    claim = RelationClaim(
        relation_id="",
        logical_relation_id="",
        revision_number=material.revision_number,
        relation_type=material.relation_type,
        arity_mode=material.arity_mode,
        subject_ref=material.subject_ref,
        object_ref=material.object_ref,
        candidate_id=material.candidate_id,
        role_bindings=material.role_bindings,
        valid_from=material.valid_from,
        valid_to=material.valid_to,
        observed_at=material.observed_at,
        published_at=material.published_at,
        known_from=known_from,
        known_until=known_until,
        assertion_refs=material.assertion_refs,
        observation_refs=material.observation_refs,
        context_ref=material.context_ref,
        source_independence_groups=material.source_independence_groups,
        extraction_version=material.extraction_version,
        normalization_version=material.normalization_version,
        ontology_version=material.ontology_version,
        schema_version=material.schema_version,
        status=RelationStatus(claim_status),
        confidence=material.confidence,
        evidence_grade=material.evidence_grade,
        tenant_id=material.tenant_id,
        investigation_id=material.investigation_id,
        created_by=material.created_by,
        supersedes=supersedes,
        contradicts=tuple(contradicts),
        created_at=created_at,
    )
    logical, revision = recompute_identity(claim)
    if (logical, revision) != (material.logical_relation_id, material.relation_id):
        raise MaterialContractError(
            "admission_identity_drift",
            f"material {material.relation_id} addresses to "
            f"({material.logical_relation_id!r}, {material.relation_id!r}) but the claim built "
            f"from it addresses to ({logical!r}, {revision!r}); admission must not be an identity "
            "event",
        )
    return replace_claim_ids(claim, logical_relation_id=logical, relation_id=revision)


def replace_claim_ids(
    claim: RelationClaim, *, logical_relation_id: str, relation_id: str
) -> RelationClaim:
    """A copy of ``claim`` carrying the two derived ids, via :func:`dataclasses.replace`.

    Named rather than inlined so the "derive once, set once" discipline of
    :func:`domain.relation_identity` is visible at the call site, and so the derived ids are the
    only thing this module ever writes onto a claim.
    """
    return replace(claim, logical_relation_id=logical_relation_id, relation_id=relation_id)


def unvalidated_report(material: RelationClaimMaterial) -> ValidationReport:
    """The report for a material nothing validated: **zero findings**, all six stages unevaluated.

    Exists so the deprecated :meth:`domain.relation_candidate.RelationCandidate.to_claim` can be
    an honest composition of :func:`build` and :func:`admit` without inventing a validation
    result. An empty report is not a clean bill of health and is not read as one:
    :meth:`~semantic.contracts.ValidationReport.unevaluated_stages` returns all six stages,
    which is precisely true - nothing was evaluated.

    A report that recorded its own absence would have to be filed under one of the six stages,
    and that would make :meth:`~semantic.contracts.ValidationReport.unevaluated_stages` claim a
    stage had run. Silence plus the stage list says the same thing without lying about coverage.
    """
    return ValidationReport(tenant_id=material.tenant_id, target_ref=material.relation_id).with_id()


def require_committed(value: object, *, required_for: str = "this operation") -> RelationClaim:
    """Return ``value`` if it is a committed :class:`RelationClaim`, else refuse (FR-012).

    The typed boundary for consumers that can only read the graph - a projection, a store write, a
    lineage walk. Passing a :class:`RelationClaimMaterial` here raises
    :class:`MaterialNotAdmitted` naming the type actually received, rather than letting it travel
    into code that assumes a lifecycle it does not have and failing later on an unrelated field.

    Deliberately an ``isinstance`` test and not a structural one: a material is not a claim, it
    has no ``status``, and the only correct answer for "is this committed" is the type itself.
    """
    if not isinstance(value, RelationClaim):
        raise MaterialNotAdmitted(value, required_for)
    return value
