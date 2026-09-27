"""Relation candidate: the extraction hypothesis that sits between a mention and a claim.

Feature 016 drew the chain ``Mention → Candidate → Assertion → Relation`` (FR-030) and
:class:`domain.evidence_lineage.HopKind` carries a ``CANDIDATE`` hop, but no object has ever
occupied it. Extraction produces typed mentions and then jumps straight to a
:class:`domain.relation_claim.RelationClaim`, so the thing that was actually extracted — the
hypothesis, its triggers, its guessed window and the regime it was read under — has nowhere to
live. This module is that missing layer, and it is deliberately thin.

**A candidate is not a claim.** A candidate says "this text *might* assert ``works_for`` between
these two mentions". A claim says "this relation holds, under this context, with this evidence".
The gap between the two is where every interesting failure lives: the wrong cue phrase, the
mention that resolved to the wrong person, the date inferred from the document header rather
than read in the sentence. A pipeline with no name for that gap can only either admit every
hypothesis or discard it at extraction time, and both destroy the disagreement later analysis
needs (I-3, FR-006). So the gap is named, frozen and stored.

Three consequences are enforced structurally rather than by convention, because a reader must be
unable to mistake a candidate for a claim:

* **No claim identity.** There is no ``relation_id`` and no ``logical_relation_id`` field. Those
  names only mean something after admission, and a candidate carrying one would be
  indistinguishable from a claim in every read path. :data:`CLAIM_ONLY_FIELDS` names the
  forbidden set and :func:`verify_candidate_field_partition` runs at import, so adding one by
  accident fails loudly instead of quietly blurring the two layers.
* **No validity window as fact.** ``valid_from`` / ``valid_to`` are forbidden at the top level.
  They exist only nested inside :class:`TemporalHypothesis`, which also records *how* the guess
  was reached, so promoting a guess into a fact at :meth:`RelationCandidate.to_claim` is a
  visible act rather than a field copy.
* **No grading, no history.** ``evidence_grade``, ``supersedes``, ``contradicts`` and
  ``revision_number`` are claim-layer facts. Grading is FR-025's work over resolved evidence,
  which does not exist yet, and a revision number presumes a claim chain that has not been
  written.

**One identity philosophy, two layers.** The split is exactly
:class:`domain.relation_claim.RelationClaim`'s, modelled on it deliberately so a reader who
knows the relation layer needs no second lesson:

* ``logical_candidate_id`` (``CAND-``) answers *which hypothesis this is* — the mention pair,
  the relation type, the role shape and the tenant. Every revision of one hypothesis shares it,
  so a re-read under a different extractor is recognisably the same hypothesis.
* ``candidate_id`` (``CNDR-``) answers *this reading of it* — that shape plus the regime, the
  extraction semantics, the guessed window, the spans, the evidence and the disposition. A
  different extractor version is a different candidate, and the field is in the id material so it
  cannot be forgotten.

Arity handling is delegated to :func:`domain.relation_identity.logical_material` rather than
reimplemented, so a candidate and the claim it becomes cannot drift on which order means the same
relation. Two deliberate divergences from ``RL-``/``RC-``: ``tenant_id`` is in the *logical*
material here, and ``candidate_status`` is in the *revision* material. Neither breaks the
logical/revision split — a tenant never changes across revisions of one hypothesis — and both are
required by the properties that matter here. Constitution IV forbids two tenants' hypotheses
bucketing under one key. And a disposition is a *finding about a reading*, not a lifecycle
transition on a fixed body of content: a candidate proposed and a candidate checked and found to
hold are different states of knowledge, and giving them one id would conflate them in every store
keyed on it. :meth:`RelationCandidate.with_status` drops the revision id for exactly that reason
and keeps the logical one, so "the same hypothesis, now rejected" stays one filter.

**A disagreement is data.** :class:`RelationCandidateSet` reports what was proposed over one
mention pair and refuses to choose. Readings that cannot both hold come back as a
:class:`CandidateConflict` with *both* candidates attached, and nothing in this module can drop
one. What is deliberately **not** a conflict matters as much: non-overlapping temporal hypotheses
(016 edge case — disjoint intervals are not a contradiction), and two different operators over
one pair, which are two true things rather than a disagreement. A pair holding several proposals
is *contested*, reported by :attr:`MentionPairGroup.is_contested`. The one genuine conflict this
layer can decide without an operator contract — a directed type asserted in both orientations —
is reported and *not* resolved, because symmetry is declared on
:class:`semantic.operators.RelationOperator` and is invisible from a candidate.

Fail-closed throughout (constitution IV): a candidate must carry a tenant, a ``context_ref``
(:class:`domain.evidence_context.EvidenceContext`, I-12) and a ``semantic_regime_ref``
(:class:`semantic.regime.SemanticRegime`, FR-014). The regime reference is required rather than
optional because :meth:`semantic.regime.SemanticRegime.uncommitted` makes "no instrument was in
play" an explicitly constructible value with an id — so there is no honest candidate without a
regime, and requiring it makes "which instruments read this" answerable at every layer rather than
only at the claim. Both are plain reference strings, not embedded copies: frames and regimes are
content-addressed and shared by reference (FR-018), so importing either type here would invite a
caller to embed one.

``extractor_version`` is identity-bearing but **not** required to be non-empty, because 016
US4-4 settles the empty case deliberately: an undeclared extractor version is
``UNDERDETERMINED``, not ``INVALID``, because the reading is uninterpretable rather than wrong and
is preserved either way. Refusing to construct it would be the opposite decision.

No I/O, no clock, no network, no model call. ``observed_at`` is supplied by the caller, so
replaying an extraction reproduces the same ids (constitution VII).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from domain.relation_claim import (
    EvidenceGrade,
    RelationClaim,
    RelationContractError,
    RelationRoleBinding,
    RelationStatus,
    check_role_bindings,
)
from domain.relation_identity import (
    RelationArityMode,
    canonical_material,
    digest128,
    logical_material,
    recompute_identity,
)
from domain.relation_schema import TemporalSemantics
from domain.temporal_worldline import DEFAULT_CONFIDENCE
from semantic.contracts import RelationRef


class ExtractionStrategy(StrEnum):
    """How a relation reading was extracted from mentions and surface text.

    Declared here, in the extraction layer, rather than next to the operator that
    consumes it. The record of *what fired* has to be writable by the extractor
    itself, and an extractor that had to import :mod:`semantic.operators` to name
    its own method would invert the dependency and pull the semantic layer into
    the foundation. :mod:`semantic.operators` imports this instead, so the edge
    runs semantic -> domain, as it should.
    """

    DEPENDENCY_PATTERN = "dependency_pattern"
    LEXICAL_PATTERN = "lexical_pattern"
    PROFILE_CONTEXT = "profile_context"
    DISTANT_SUPERVISION = "distant_supervision"
    RULE = "rule"
    WEAK_SUPERVISION = "weak_supervision"

#: Prefix of the *logical* candidate key — "which hypothesis this is", shared by every
#: revision of one hypothesis. Distinct from ``RL-``/``RC-`` so a candidate and a claim are
#: never confusable by a reader or by a log line.
LOGICAL_CANDIDATE_ID_PREFIX = "CAND-"

#: Prefix of the candidate *revision* id — "this reading of the hypothesis". The trailing
#: ``R`` keeps the two prefixes lexically distinct, so a truncated line can never alias one
#: onto the other and ``CNDR-`` is not ``CAND-`` plus a hex digit.
REVISION_CANDIDATE_ID_PREFIX = "CNDR-"


class CandidateStatus(StrEnum):
    """What happened to one reading of a hypothesis.

    Not a ladder, and deliberately given no :meth:`rank`, unlike
    :class:`semantic.contracts.SemanticStatus` or
    :class:`semantic.regime.SemanticCommitment`. There is no ordering to preserve here,
    because ``CONTRADICTED`` and ``REJECTED`` are not weaker than ``PROPOSE`` — they are
    answers to a different question, reached by checking rather than by looking harder. A
    ``rank`` would license a caller to read "supported" as "more proposed than rejected",
    which is true of neither.
    """

    PROPOSE = "propose"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    REJECTED = "rejected"


#: The only disposition that may cross into the claim layer.
#:
#: ``PROPOSE`` is excluded on purpose: it is the raw output of extraction, and admission is a
#: *decision* taken after the hypothesis has been checked. Letting a propose become a claim
#: makes admission a formality, which is the failure this layer exists to make visible.
#: ``CONTRADICTED`` and ``REJECTED`` are excluded because both are preserved candidates,
#: never deleted ones (I-3, FR-006) — they simply never become claims.
ADMISSIBLE_CANDIDATE_STATUSES: frozenset[CandidateStatus] = frozenset(
    {CandidateStatus.SUPPORTED}
)

#: Dispositions asserting that a checked reading *failed*. What makes a disposition
#: disagreement a disagreement: the same hypothesis both supported and ruled against.
CONTRADICTING_CANDIDATE_STATUSES: frozenset[CandidateStatus] = frozenset(
    {CandidateStatus.CONTRADICTED, CandidateStatus.REJECTED}
)


class CandidateContractError(ValueError):
    """A candidate cannot be constructed from these fields.

    A ``ValueError`` carrying the stable snake_case ``code`` the extraction layer reports, in
    the spirit of :class:`domain.relation_claim.RelationContractError` and
    :class:`domain.evidence_context.ContextContractError` so one caller can switch on any of
    them.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class CandidateNotAdmissible(CandidateContractError):
    """A candidate in a non-admissible disposition was asked to become a claim.

    A separate type rather than a bare :class:`CandidateContractError` because the caller
    usually wants to *catch* this one and route the candidate to review, while a genuine
    contract breach is a bug. The error names the status it was refused at, because "why was
    this not admitted" is the question an operator actually has, and answering it from the
    message alone would mean re-deriving the disposition machine at the call site.
    """

    def __init__(
        self,
        candidate_id: str,
        status: CandidateStatus,
        admissible: frozenset[CandidateStatus],
    ) -> None:
        self.candidate_id = candidate_id
        self.status = CandidateStatus(status)
        self.admissible_statuses = frozenset(CandidateStatus(s) for s in admissible)
        super().__init__(
            "candidate_not_admissible",
            f"candidate {candidate_id or '<unaddressed>'} is {self.status}; only "
            f"{sorted(str(s) for s in self.admissible_statuses)} may become a claim",
        )


class TemporalBasis(StrEnum):
    """How a temporal guess was reached — the honesty of a window, recorded with it.

    ``ABSENT`` is the load-bearing member. "The extractor found no date" is a finding an
    operator with ``REQUIRED_INTERVAL`` needs (016 US5 acceptance 2), so it is a value and
    not a missing field: :meth:`TemporalHypothesis.carries_window` tells the two apart, and
    an absent hypothesis never raises.
    """

    EXPLICIT = "explicit"
    DERIVED = "derived"
    ABSENT = "absent"


def _iso(value: Any) -> str | None:
    """One timestamp as canonical text (``None`` = honestly unknown)."""
    if value is None or value == "":
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


@dataclass(frozen=True)
class SpanRef:
    """Where in the source an extraction read something, as offsets — never as text (I-5).

    A span is a *location*, so its absence is a null: a candidate raised by
    ``PROFILE_CONTEXT`` or ``DISTANT_SUPERVISION`` genuinely has no surface trigger, and
    forcing one on it would be a fabricated citation. This is the opposite of
    :class:`TemporalHypothesis`, where the absence of a guess is itself the recorded
    finding — which is why one takes ``None`` and the other takes a value.

    Offsets are half-open ``[start, end)`` against ``segment_ref``, so a zero-length span is
    a legal empty match rather than an error: an extractor that matched an empty cue must be
    able to say so. ``mention_ref``, when set, names the mention whose surface this span is;
    when empty the span is the region *between* mentions, which is what a lexical trigger is.
    """

    segment_ref: str
    start: int
    end: int
    mention_ref: str = ""

    def __post_init__(self) -> None:
        if not self.segment_ref:
            raise CandidateContractError(
                "missing_segment_ref",
                "a span indexes into a segment; offsets with no segment are unresolvable",
            )
        if self.start < 0:
            raise CandidateContractError(
                "negative_offset", f"span start must be >= 0, got {self.start}"
            )
        if self.end < self.start:
            raise CandidateContractError(
                "inverted_span", f"span end {self.end} precedes start {self.start}"
            )

    @property
    def identity(self) -> tuple[str, int, int, str]:
        """The canonical order key, over what is resolvable rather than over a text offset."""
        return (self.segment_ref, self.start, self.end, self.mention_ref)

    @property
    def length(self) -> int:
        """Span width in characters; zero for a legal empty match."""
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_ref": self.segment_ref,
            "start": self.start,
            "end": self.end,
            "mention_ref": self.mention_ref,
        }


@dataclass(frozen=True)
class TemporalHypothesis:
    """A *guess* at when a relation held, plus the record of how the guess was reached.

    This is the only home a candidate's ``valid_from`` / ``valid_to`` may have. Promotion to
    a fact happens in :meth:`RelationCandidate.to_claim` and nowhere else, so "this window
    was inferred from the document date" stays attached to the moment it stops being a guess
    and becomes an assertion (I-3).

    ``basis=ABSENT`` with no window is the honest default and never raises. A window *on* an
    ``ABSENT`` hypothesis does raise, because a record that says "we did not guess" and
    carries a guess is self-contradicting and no reader could resolve it. ``DERIVED`` requires
    ``derived_from_ref`` for the same reason: a derivation with no stated source cannot be
    re-checked, and a temporal guess nobody can re-derive is the one most likely to be wrong.

    ``semantics`` is carried from the operator's :class:`domain.relation_schema.RelationSchema`
    so the expected reading of the window travels with it. It is a *guess* about semantics
    too: a lexical extractor that finds a bare year cannot know whether the operator wanted
    a point or an interval, and recording the operator's declared mode is more useful than
    inferring one.
    """

    valid_from: datetime | None = None
    valid_to: datetime | None = None
    semantics: TemporalSemantics = TemporalSemantics.OPTIONAL_INTERVAL
    basis: TemporalBasis = TemporalBasis.ABSENT
    derived_from_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantics", TemporalSemantics(self.semantics))
        object.__setattr__(self, "basis", TemporalBasis(self.basis))
        for name in ("valid_from", "valid_to"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, datetime):
                raise CandidateContractError(
                    "invalid_temporal_hypothesis",
                    f"{name} must be a datetime or None, got {value!r}",
                )
        if (
            self.valid_to is not None
            and self.valid_from is not None
            and self.valid_to < self.valid_from
        ):
            raise CandidateContractError(
                "inverted_hypothesis",
                f"hypothesised valid_to {self.valid_to.isoformat()} precedes "
                f"valid_from {self.valid_from.isoformat()}",
            )
        if self.basis is TemporalBasis.ABSENT and (self.valid_from or self.valid_to):
            raise CandidateContractError(
                "absent_hypothesis_with_window",
                "a hypothesis recorded as absent cannot carry a window; the basis is the "
                "record of whether a guess was made at all",
            )
        if self.basis is TemporalBasis.DERIVED and not self.derived_from_ref:
            raise CandidateContractError(
                "missing_derivation_source",
                "a derived temporal hypothesis must name what it was derived from",
            )

    @classmethod
    def absent(cls) -> TemporalHypothesis:
        """The hypothesis an extractor that found no date leaves behind.

        Named rather than left as a bare default so the common case reads as a decision at
        the call site, and so an operator with ``REQUIRED_INTERVAL`` can see that the window
        is missing because nothing was found rather than because nothing was recorded.
        """
        return cls()

    @classmethod
    def explicit(
        cls,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        *,
        semantics: TemporalSemantics = TemporalSemantics.OPTIONAL_INTERVAL,
    ) -> TemporalHypothesis:
        """A window read out of the text itself, with no inference behind it."""
        return cls(
            valid_from=valid_from,
            valid_to=valid_to,
            semantics=semantics,
            basis=TemporalBasis.EXPLICIT,
        )

    @classmethod
    def derived(
        cls,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        *,
        derived_from_ref: str,
        semantics: TemporalSemantics = TemporalSemantics.OPTIONAL_INTERVAL,
    ) -> TemporalHypothesis:
        """A window inferred from ``derived_from_ref`` — a document date, a co-occurrence
        window, an entity worldline — which is the case that most needs the citation."""
        return cls(
            valid_from=valid_from,
            valid_to=valid_to,
            semantics=semantics,
            basis=TemporalBasis.DERIVED,
            derived_from_ref=derived_from_ref,
        )

    def carries_window(self) -> bool:
        """Whether a window was guessed at all, as distinct from a window being absent."""
        return self.valid_from is not None or self.valid_to is not None

    def overlaps(self, other: TemporalHypothesis) -> bool:
        """Whether two hypotheses are *known* to describe overlapping spans.

        ``False`` when either side carries no window, and ``True`` for two open-ended
        windows, because two unbounded intervals always overlap and reporting that as a
        finding would be noise. Callers must read ``False`` as "no contradiction
        established", never as "disjoint": absence of a conflict is not evidence of
        compatibility.
        """
        if not self.carries_window() or not other.carries_window():
            return False
        starts = [m for m in (self.valid_from, other.valid_from) if m is not None]
        if not starts:
            return True
        ends = [m for m in (self.valid_to, other.valid_to) if m is not None]
        return max(starts) <= min(ends) if ends else True

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_from": _iso(self.valid_from),
            "valid_to": _iso(self.valid_to),
            "semantics": str(self.semantics),
            "basis": str(self.basis),
            "derived_from_ref": self.derived_from_ref,
        }


#: Fields a claim carries and a candidate must not. Enforced by
#: :func:`verify_candidate_field_partition` at import.
#:
#: Every entry is excluded for a stated reason, and the reasons are why the list exists:
#: each is a fact that only comes into being *after* admission.
#:
#: - ``relation_id`` / ``logical_relation_id`` / ``revision_number`` - claim identity, and
#:   the whole point of this layer is that a candidate has none.
#: - ``valid_from`` / ``valid_to`` - a window as fact. Both names exist *nested* in
#:   :class:`TemporalHypothesis`; the ban is on the top level, which is what keeps a
#:   promotion visible as an act in :meth:`RelationCandidate.to_claim`.
#: - ``assertion_refs`` / ``evidence_grade`` / ``source_independence_groups`` - grading is
#:   FR-025's work and runs on resolved evidence, which does not exist yet.
#: - ``supersedes`` / ``contradicts`` - links between *claims*. A disagreement between two
#:   candidates is reported by :class:`RelationCandidateSet` instead, because it is a
#:   disagreement between readings, not one relation's history.
#: - ``normalization_version`` / ``ontology_version`` - belong to the frame and the regime.
#:   A candidate carries the regime *reference*; copying the versions in would give one fact
#:   two homes and a second thing to drift.
#: - ``known_from`` / ``known_until`` / ``created_by`` / ``created_at`` - claim bookkeeping.
#:   A candidate has ``recorded_by`` and a caller-supplied ``observed_at`` instead.
CLAIM_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "relation_id",
        "logical_relation_id",
        "revision_number",
        "valid_from",
        "valid_to",
        "known_from",
        "known_until",
        "assertion_refs",
        "evidence_grade",
        "source_independence_groups",
        "supersedes",
        "contradicts",
        "normalization_version",
        "ontology_version",
        "created_by",
        "created_at",
    }
)

#: Fields deciding *which hypothesis this is*. Covered by
#: :meth:`RelationCandidate._logical_material` and entering ``logical_candidate_id``, so
#: every revision of one hypothesis shares them. ``schema_version`` is absent on purpose: it
#: is the *operator* version, so a hypothesis read under a newer operator contract is a new
#: reading of the same hypothesis, not a new hypothesis — exactly as ``RL-``/``RC-`` treat it.
CANDIDATE_LOGICAL_MATERIAL_FIELDS: frozenset[str] = frozenset(
    {
        "tenant_id",
        "relation_type",
        "arity_mode",
        "subject_mention_ref",
        "object_mention_ref",
        "role_assignments",
    }
)

#: Fields making a revision *itself*. A change here means a different reading of the same
#: hypothesis: a different extractor, a different regime, a different guessed window, or a
#: different disposition. All enter ``candidate_id``, so none can be edited into a candidate
#: without minting a new one.
CANDIDATE_REVISION_MATERIAL_FIELDS: frozenset[str] = frozenset(
    {
        "schema_version",
        "temporal_hypothesis",
        "observed_at",
        "context_ref",
        "semantic_regime_ref",
        "observation_refs",
        "evidence_refs",
        "extraction_method",
        "extractor_version",
        "extraction_rule_id",
        "trigger_span",
        "supporting_spans",
        "investigation_id",
        "recorded_by",
        "candidate_status",
    }
)

#: Fields a projection may legitimately restate. ``confidence`` alone, and for the same
#: reason as on a claim (FR-025): a re-scoring pass must not mint a new candidate, or every
#: ranking change forks the extraction record. Bounded and checked — two candidates sharing
#: a ``candidate_id`` may differ only here, and
#: :meth:`RelationCandidateSet.divergent_candidate_ids` reports any such pair.
CANDIDATE_MUTABLE_PROJECTION_FIELDS: frozenset[str] = frozenset({"confidence"})

#: Candidate fields the material does not emit under their own name, and the material keys
#: they stand for. ``relation_ref`` is addressed as its two parts so the operator identity
#: is legible in the canonical material without the caller re-deriving it from a nested
#: object — the same treatment ``role_bindings`` gets for the participants of an n-ary
#: claim. Declared rather than inferred so the partition checks can account for it.
DECOMPOSED_CANDIDATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {"relation_ref": ("relation_type", "schema_version")}
)


@dataclass(frozen=True)
class RelationCandidate:
    """One reading of one hypothesis that a relation holds between two *mentions*.

    Frozen, content-addressed and tenant-scoped. The endpoints are mention references and
    not entity references on purpose: the candidate has resolved nothing yet, and a
    candidate naming entities would have smuggled the resolution result in ahead of the
    decision to make it. :meth:`to_claim` is where mentions become admitted participants, and
    it takes them from the caller because the resolution happened after this record was
    written.

    Field order follows the same discipline as
    :class:`domain.relation_claim.RelationClaim`: what the hypothesis *is* first (the three
    required fields), then the reading around it, then the disposition, then the derived ids.
    Every collection is canonicalised on construction, so two candidates whose producer
    collected its refs in a different order are one candidate (I-11).
    """

    subject_mention_ref: str
    object_mention_ref: str
    relation_ref: RelationRef
    arity_mode: RelationArityMode = RelationArityMode.DIRECTED
    role_assignments: tuple[RelationRoleBinding, ...] = ()

    context_ref: str = ""
    semantic_regime_ref: str = ""

    trigger_span: SpanRef | None = None
    supporting_spans: tuple[SpanRef, ...] = ()

    extraction_method: ExtractionStrategy = ExtractionStrategy.LEXICAL_PATTERN
    extractor_version: str = ""
    extraction_rule_id: str = ""

    observation_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    temporal_hypothesis: TemporalHypothesis = TemporalHypothesis()
    candidate_status: CandidateStatus = CandidateStatus.PROPOSE
    confidence: float = DEFAULT_CONFIDENCE

    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    observed_at: datetime | None = None
    recorded_by: str = ""

    candidate_id: str = ""
    logical_candidate_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "arity_mode", RelationArityMode(self.arity_mode))
        object.__setattr__(
            self, "extraction_method", ExtractionStrategy(self.extraction_method)
        )
        object.__setattr__(self, "candidate_status", CandidateStatus(self.candidate_status))
        if not isinstance(self.relation_ref, RelationRef):
            raise CandidateContractError(
                "invalid_relation_ref",
                "relation_ref must be a semantic.contracts.RelationRef naming an operator "
                f"(relation_type, schema_version), got {type(self.relation_ref).__name__}",
            )
        if not isinstance(self.temporal_hypothesis, TemporalHypothesis):
            raise CandidateContractError(
                "invalid_temporal_hypothesis",
                "temporal_hypothesis must be a TemporalHypothesis; use "
                "TemporalHypothesis.absent() to record that no window was guessed, rather "
                "than None",
            )
        if self.trigger_span is not None and not isinstance(self.trigger_span, SpanRef):
            raise CandidateContractError(
                "invalid_trigger_span",
                f"trigger_span must be a SpanRef or None, got {type(self.trigger_span).__name__}",
            )
        for span in self.supporting_spans:
            if not isinstance(span, SpanRef):
                raise CandidateContractError(
                    "invalid_supporting_span",
                    f"supporting_spans must hold SpanRef values, got "
                    f"{type(span).__name__}",
                )

        if not self.subject_mention_ref or not self.object_mention_ref:
            raise CandidateContractError(
                "missing_mention_ref",
                "a candidate relates two mentions and needs both references",
            )
        if self.subject_mention_ref == self.object_mention_ref:
            raise CandidateContractError(
                "self_loop",
                f"{self.relation_ref.relation_type or 'relation'} proposes "
                f"{self.subject_mention_ref!r} in relation to itself",
            )
        if not self.relation_ref.relation_type:
            raise CandidateContractError(
                "missing_relation_type", "a candidate requires an operator relation_type"
            )
        if not self.context_ref:
            raise CandidateContractError(
                "missing_context_ref",
                "a candidate requires an evidence context ref (I-12, FR-007); the frame is "
                "shared by reference, never embedded",
            )
        if not self.semantic_regime_ref:
            raise CandidateContractError(
                "missing_semantic_regime_ref",
                "a candidate requires the ref of the SemanticRegime that interpreted it "
                "(FR-014); SemanticRegime.uncommitted() is the value for a hypothesis no "
                "instrument read",
            )
        if not self.tenant_id:
            raise CandidateContractError(
                "missing_tenant",
                "a candidate must be tenant-scoped (constitution IV)",
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise CandidateContractError(
                "confidence_out_of_range",
                f"confidence must be within [0.0, 1.0], got {self.confidence}",
            )

        if self.arity_mode is RelationArityMode.DIRECTED and self.role_assignments:
            raise CandidateContractError(
                "role_assignment_on_directed",
                "a directed relation takes its two members from the endpoints, not from role "
                "assignments; RelationClaim refuses this shape, so a candidate admitting it "
                "could never be promoted",
            )
        if self.arity_mode is RelationArityMode.NARY and len(self.role_assignments) < 2:
            raise CandidateContractError(
                "insufficient_role_assignments",
                f"an nary candidate needs at least two role assignments, got "
                f"{len(self.role_assignments)}",
            )
        try:
            check_role_bindings(self.role_assignments)
        except RelationContractError as exc:
            raise CandidateContractError(exc.code, exc.message) from exc

        object.__setattr__(
            self,
            "role_assignments",
            tuple(
                sorted(
                    self.role_assignments,
                    key=lambda b: (b.role, b.member_ref, b.member_class),
                )
            ),
        )
        object.__setattr__(
            self,
            "supporting_spans",
            tuple(sorted(set(self.supporting_spans), key=lambda span: span.identity)),
        )
        object.__setattr__(
            self, "observation_refs", tuple(sorted({str(r) for r in self.observation_refs}))
        )
        object.__setattr__(
            self, "evidence_refs", tuple(sorted({str(r) for r in self.evidence_refs}))
        )

    @property
    def relation_type(self) -> str:
        """The operator's relation type, read off the reference rather than restated."""
        return self.relation_ref.relation_type

    @property
    def schema_version(self) -> str:
        """The operator version in force when the reading was produced (FR-029)."""
        return self.relation_ref.schema_version

    @property
    def is_admissible(self) -> bool:
        """Whether this reading is in a disposition that may become a claim."""
        return self.candidate_status in ADMISSIBLE_CANDIDATE_STATUSES

    @property
    def is_contradicting(self) -> bool:
        """Whether this reading asserts a checked failure."""
        return self.candidate_status in CONTRADICTING_CANDIDATE_STATUSES

    @property
    def content_hash(self) -> str:
        """128-bit content address of every field except the ids (FR-005, I-11).

        Taken over the same serialised set :meth:`_material` publishes, so two readings
        differing only in ``confidence`` are byte-identical and a re-write is idempotent.
        """
        return digest128(canonical_material(self._material()))

    @property
    def _participants(self) -> tuple[str, ...]:
        """The members identity is taken over: the roles for ``NARY``, the pair otherwise.

        The same partition :func:`domain.relation_identity.recompute_identity` documents for
        a claim, so a candidate and the claim it becomes address the same shape.
        """
        if self.arity_mode is RelationArityMode.NARY:
            return tuple(binding.member_ref for binding in self.role_assignments)
        return (self.subject_mention_ref, self.object_mention_ref)

    @property
    def target_key(self) -> MentionPair:
        """The mention pair (or n-ary shape) this reading is about."""
        return MentionPair.of(self)

    def with_id(self) -> RelationCandidate:
        """A copy carrying its own content-addressed ids, both of them.

        Derivation is explicit rather than automatic in ``__post_init__`` so construction
        stays a plain value operation, matching :meth:`semantic.contracts.TypeAssertion.with_id`.
        Ids are *not* verified the way :class:`semantic.regime.SemanticRegime` verifies its
        own, and for the same reason a claim does not verify its own: identity validation is
        a layer (FR-022), so :func:`verify_candidate_identity` is what a store or a test
        calls, rather than construction refusing to load a stored row.
        """
        if self.candidate_id and self.logical_candidate_id:
            return self
        logical, revision = recompute_candidate_identity(self)
        return replace(self, logical_candidate_id=logical, candidate_id=revision)

    def with_status(self, status: CandidateStatus) -> RelationCandidate:
        """A reading of the same hypothesis carrying a different disposition.

        Note what this deliberately does *not* preserve: the ``candidate_id`` is dropped so a
        re-addressed reading is produced, because a disposition is a finding about the
        reading rather than a lifecycle transition on a fixed body of content. The
        ``logical_candidate_id`` is *not* dropped, so "the same hypothesis, now rejected" is
        one filter rather than a scan. Compare
        :data:`domain.relation_identity.MUTABLE_PROJECTION_FIELDS`, which excludes ``status``
        for a claim for exactly the opposite reason.
        """
        return replace(self, candidate_status=CandidateStatus(status), candidate_id="").with_id()

    def to_claim(
        self,
        *,
        subject_ref: str,
        object_ref: str,
        revision_number: int,
        claim_status: RelationStatus,
        evidence_grade: EvidenceGrade,
        tenant_id: str,
        role_bindings: Sequence[RelationRoleBinding] = (),
        assertion_refs: Sequence[str] = (),
        normalization_version: str = "",
        ontology_version: str = "",
        observed_at: datetime | None = None,
    ) -> RelationClaim:
        """Admit this reading as a :class:`domain.relation_claim.RelationClaim`.

        This is the *only* place a candidate becomes a claim and the only place a temporal
        guess is promoted to an asserted window, so identity is derived exactly once and the
        material is never transcribed a second time: the claim is built from the candidate's
        own fields, :func:`domain.relation_identity.recompute_identity` derives both ids
        from that claim, and the result is returned with them set. A caller cannot reach a
        claim whose ids disagree with its own contents.

        :raises CandidateNotAdmissible: unless the reading is in
            :data:`ADMISSIBLE_CANDIDATE_STATUSES`. Raised rather than returning ``None``,
            because a caller that ignores the return value must not be able to walk on with
            an unadmitted hypothesis.

        The keyword arguments are required exactly where the candidate genuinely cannot know
        the answer, and defaulted to the honest unknown where it can:

        * ``subject_ref`` / ``object_ref`` - the *resolved* participants. Required, and the
          single most load-bearing judgement in this module: a candidate names mentions, a
          claim names admitted participants, and resolution happened after this record was
          written. Substituting the mention refs here would put a mention into the claim's
          identity material and quietly break I-2.
        * ``revision_number`` - required. Defaulting it to ``1`` would invent a fact about the
          claim chain, and a second admission of the same relation would then collide.
        * ``claim_status`` / ``evidence_grade`` - the admitted disposition and the
          grade. Both are decisions or derivations made outside this layer, and grading in
          particular is FR-025's work over resolved evidence.
        * Evidence is **not** a parameter. An earlier signature required
          ``evidence_refs`` and then dropped it, because :class:`RelationClaim` has no
          field of that name -- so a caller could hand over its evidence set and receive a
          claim that silently carried none, and no signature would object. That is the
          worst shape an evidence parameter can have in a platform whose first principle
          is evidence before entity. The candidate's own ``observation_refs`` and
          ``evidence_refs`` now travel into the claim's ``observation_refs`` in order, and
          a caller's additional evidence is passed as ``observation_refs`` or
          ``assertion_refs`` -- both of which are identity material, so a claim that
          differs in its evidence is a different claim rather than a differently-labelled
          one. Evidence the caller wanted to keep but did not route into one of those two
          arguments is simply not on the claim, which is honest.
        * ``tenant_id`` - required, and cross-checked against this candidate's tenant. A
          mismatch raises rather than producing a claim in one tenant citing a candidate from
          another (constitution IV).
        * ``role_bindings`` - defaulted empty, which is correct for ``DIRECTED`` and
          ``UNDIRECTED`` and is refused by :class:`RelationClaim` for ``NARY``. The default is
          not an invention: an n-ary claim with no role bindings cannot be constructed, so an
          incomplete resolution fails closed at the claim boundary instead of being quietly
          accepted here.
        * ``normalization_version`` / ``ontology_version`` - defaulted empty, recording
          "unknown" rather than copying a value the caller may not have. An operator with an
          undeclared version is reported ``UNDERDETERMINED`` (016 US4-4), not rejected, so a
          truthful gap is recoverable and a fabricated one is not.
        * ``observed_at`` - defaults to this candidate's own ``observed_at``, a transcription
          of a caller-supplied value rather than an invention. Pass a value to record when
          admission happened rather than extraction.

        Everything else is transcribed from the candidate: the operator identity, the arity
        mode, the context and regime references, the observation refs, the extraction method
        and version, the rule id, the investigation and the author. ``source_independence_groups``
        is not among them: independence is computed across a claim set (FR-034) and is not
        knowable by one candidate in isolation.
        """
        if not self.is_admissible:
            raise CandidateNotAdmissible(
                self.candidate_id, self.candidate_status, ADMISSIBLE_CANDIDATE_STATUSES
            )
        if str(tenant_id) != self.tenant_id:
            raise CandidateContractError(
                "tenant_mismatch",
                f"candidate {self.candidate_id or '<unaddressed>'} belongs to tenant "
                f"{self.tenant_id!r} and cannot be admitted as {str(tenant_id)!r} "
                "(constitution IV)",
            )

        claim = RelationClaim(
            relation_id="",
            logical_relation_id="",
            revision_number=revision_number,
            relation_type=self.relation_type,
            arity_mode=self.arity_mode,
            subject_ref=subject_ref,
            object_ref=object_ref,
            role_bindings=tuple(role_bindings),
            valid_from=self.temporal_hypothesis.valid_from,
            valid_to=self.temporal_hypothesis.valid_to,
            observed_at=observed_at if observed_at is not None else self.observed_at,
            assertion_refs=tuple(assertion_refs),
            observation_refs=tuple(dict.fromkeys((*self.observation_refs, *self.evidence_refs))),
            context_ref=self.context_ref,
            extraction_version=self.extractor_version,
            normalization_version=normalization_version,
            ontology_version=ontology_version,
            schema_version=self.schema_version,
            status=RelationStatus(claim_status),
            confidence=self.confidence,
            evidence_grade=EvidenceGrade(evidence_grade),
            tenant_id=str(tenant_id),
            investigation_id=self.investigation_id,
            created_by=self.recorded_by,
        )
        logical, revision = recompute_identity(claim)
        return replace(claim, logical_relation_id=logical, relation_id=revision)

    def _logical_material(self) -> dict[str, Any]:
        """The material of *which hypothesis this is*, shared by every revision.

        Delegates the arity shape to :func:`domain.relation_identity.logical_material` so the
        two layers canonicalise participants identically — sorted+deduped for ``UNDIRECTED``,
        order-preserving for ``DIRECTED``, role pairs for ``NARY`` — and then adds
        ``tenant_id``, which ``RL-`` deliberately omits. The divergence is a considered one
        and costs nothing structurally: a tenant never changes across revisions of one
        hypothesis, so the logical/revision split is unaffected, while omitting it would let
        two tenants' hypotheses bucket under one key, which constitution IV forbids.
        """
        return {
            **logical_material(
                self.arity_mode,
                self.relation_type,
                self._participants,
                self.role_assignments,
            ),
            "tenant_id": self.tenant_id,
        }

    def _revision_material(self, logical_candidate_id: str) -> dict[str, Any]:
        """The material of *this reading*, keyed by the logical id.

        The temporal window enters here as a nested hypothesis, all four of its fields, so a
        change of guessed span, of how the guess was reached, or of the declared semantics all
        mint a new ``candidate_id`` while leaving the logical key alone. The logical id is a
        parameter rather than read off the record so that derivation cannot recurse through
        :meth:`with_id` on an unaddressed candidate.
        """
        return {
            "logical_candidate_id": logical_candidate_id,
            "schema_version": self.schema_version,
            "temporal_hypothesis": self.temporal_hypothesis.to_dict(),
            "observed_at": _iso(self.observed_at),
            "context_ref": self.context_ref,
            "semantic_regime_ref": self.semantic_regime_ref,
            "observation_refs": list(self.observation_refs),
            "evidence_refs": list(self.evidence_refs),
            "extraction_method": str(self.extraction_method),
            "extractor_version": self.extractor_version,
            "extraction_rule_id": self.extraction_rule_id,
            "trigger_span": None if self.trigger_span is None else self.trigger_span.to_dict(),
            "supporting_spans": [span.to_dict() for span in self.supporting_spans],
            "investigation_id": self.investigation_id,
            "recorded_by": self.recorded_by,
            "candidate_status": str(self.candidate_status),
        }

    def _material(self) -> dict[str, Any]:
        """The serialised field set the content hash is taken over (FR-005)."""
        return {
            "tenant_id": self.tenant_id,
            "subject_mention_ref": self.subject_mention_ref,
            "object_mention_ref": self.object_mention_ref,
            "relation_type": self.relation_type,
            "schema_version": self.schema_version,
            "arity_mode": str(self.arity_mode),
            "role_assignments": [binding.to_dict() for binding in self.role_assignments],
            "context_ref": self.context_ref,
            "semantic_regime_ref": self.semantic_regime_ref,
            "trigger_span": None if self.trigger_span is None else self.trigger_span.to_dict(),
            "supporting_spans": [span.to_dict() for span in self.supporting_spans],
            "extraction_method": str(self.extraction_method),
            "extractor_version": self.extractor_version,
            "extraction_rule_id": self.extraction_rule_id,
            "observation_refs": list(self.observation_refs),
            "evidence_refs": list(self.evidence_refs),
            "temporal_hypothesis": self.temporal_hypothesis.to_dict(),
            "candidate_status": str(self.candidate_status),
            "confidence": self.confidence,
            "investigation_id": self.investigation_id,
            "observed_at": _iso(self.observed_at),
            "recorded_by": self.recorded_by,
        }


def recompute_candidate_identity(candidate: RelationCandidate) -> tuple[str, str]:
    """Re-derive ``(logical_candidate_id, candidate_id)`` from a candidate's own fields.

    The identity layer's counterpart to
    :func:`domain.relation_identity.recompute_identity`, and the only id-producing path this
    module exposes. Pure, so a tampering store, a replay and a test all reach the same answer
    and can therefore disagree loudly (FR-011, FR-022).
    """
    logical = LOGICAL_CANDIDATE_ID_PREFIX + digest128(
        canonical_material(candidate._logical_material())
    )
    material = candidate._revision_material(logical)
    for key in ("observation_refs", "evidence_refs"):
        material[key] = sorted(material[key])
    return logical, REVISION_CANDIDATE_ID_PREFIX + digest128(canonical_material(material))


def verify_candidate_identity(candidate: RelationCandidate) -> None:
    """Fail unless the carried ids are the ones the candidate's own content addresses.

    The tamper check a store runs on load, mirroring how the identity layer of
    :mod:`domain.relation_identity` re-derives and compares rather than trusting a stored id.
    Refuses only the *addressed* case; an unaddressed candidate is simply not yet addressed
    and is not an error, because :meth:`RelationCandidate.with_id` is how a candidate becomes
    addressable.
    """
    if not candidate.candidate_id and not candidate.logical_candidate_id:
        return
    logical, revision = recompute_candidate_identity(candidate)
    if logical != candidate.logical_candidate_id or revision != candidate.candidate_id:
        raise CandidateContractError(
            "candidate_id_mismatch",
            f"candidate carries ({candidate.logical_candidate_id!r}, "
            f"{candidate.candidate_id!r}) but its own content addresses to ({logical!r}, "
            f"{revision!r}); a content address is verified, never trusted",
        )


def verify_candidate_material_partition(candidate: RelationCandidate) -> None:
    """Fail if any candidate field is unclassified, or classified twice.

    The candidate-layer counterpart of
    :func:`domain.relation_identity.verify_material_partition`, for the same reason: the
    partition decays silently otherwise. Someone adds a field, it lands in no set, and it is
    quietly excluded from identity — the exact bug the relation layer was corrected for, one
    new field at a time. The classes are exhaustive and mutually exclusive:

    * :data:`CANDIDATE_LOGICAL_MATERIAL_FIELDS` - which hypothesis this is;
    * :data:`CANDIDATE_REVISION_MATERIAL_FIELDS` - which reading of it;
    * :data:`CANDIDATE_MUTABLE_PROJECTION_FIELDS` - restatable without a new candidate;
    * the two derived id fields, which are outputs rather than inputs.
    """
    material = candidate._material()
    derived = {"candidate_id", "logical_candidate_id"}
    identity = CANDIDATE_LOGICAL_MATERIAL_FIELDS | CANDIDATE_REVISION_MATERIAL_FIELDS
    classified = identity | CANDIDATE_MUTABLE_PROJECTION_FIELDS | derived
    unclassified = sorted(set(material) - classified)
    if unclassified:
        raise CandidateContractError(
            "unclassified_candidate_field",
            "RelationCandidate material is neither identity material nor declared mutable "
            f"projection metadata: {unclassified}. Add each to "
            "CANDIDATE_LOGICAL_MATERIAL_FIELDS, CANDIDATE_REVISION_MATERIAL_FIELDS or "
            "CANDIDATE_MUTABLE_PROJECTION_FIELDS in domain.relation_candidate so the "
            "partition stays total",
        )
    for left, right, label in (
        (CANDIDATE_LOGICAL_MATERIAL_FIELDS, CANDIDATE_REVISION_MATERIAL_FIELDS, "identity"),
        (identity, CANDIDATE_MUTABLE_PROJECTION_FIELDS, "identity and mutable"),
    ):
        overlap = sorted(left & right)
        if overlap:
            raise CandidateContractError(
                "field_classified_twice",
                f"fields classified as both {label} material: {overlap}",
            )
    declared = identity | CANDIDATE_MUTABLE_PROJECTION_FIELDS
    decomposed = {part for parts in DECOMPOSED_CANDIDATE_FIELDS.values() for part in parts}
    never_emitted = sorted(declared - set(material) - decomposed)
    if never_emitted:  # pragma: no cover - the material emits every declared field
        raise CandidateContractError(
            "candidate_field_never_addressed",
            f"fields are classified as material the canonical material never emits: "
            f"{never_emitted}",
        )
    missing = sorted(
        CANDIDATE_REVISION_MATERIAL_FIELDS
        - set(candidate._revision_material(candidate.logical_candidate_id))
    )
    if missing:  # pragma: no cover - the revision material emits every declared field
        raise CandidateContractError(
            "revision_material_incomplete",
            "CANDIDATE_REVISION_MATERIAL_FIELDS declares fields the revision material does "
            f"not emit: {missing}",
        )


def verify_candidate_field_partition() -> None:
    """Fail if a claim-only field has appeared on the candidate, or a field is unaccounted for.

    Called once at import, because "a candidate is not a claim" has to be true of the *type*
    and not merely of this file's prose. A field named ``valid_from`` or ``relation_id``
    would make a candidate readable as a claim in every consumer that treats field names as
    the contract, and that failure mode — a reviewer trusting a window that is really a guess
    — is silent, which is why it is checked mechanically rather than by review.
    """
    present = {field.name for field in fields(RelationCandidate)}
    leaked = sorted(present & CLAIM_ONLY_FIELDS)
    if leaked:
        raise CandidateContractError(
            "claim_only_field_on_candidate",
            f"a candidate must not carry {leaked}: those are claim-layer facts that only "
            "exist after admission. A validity window belongs nested in "
            "temporal_hypothesis, and the claim's own ids are not a candidate's to hold",
        )
    derived = {"candidate_id", "logical_candidate_id"}
    classified = (
        CANDIDATE_LOGICAL_MATERIAL_FIELDS
        | CANDIDATE_REVISION_MATERIAL_FIELDS
        | CANDIDATE_MUTABLE_PROJECTION_FIELDS
    )
    unaccounted = sorted(present - classified - derived - set(DECOMPOSED_CANDIDATE_FIELDS))
    if unaccounted:
        raise CandidateContractError(
            "unclassified_candidate_field",
            f"RelationCandidate fields are neither identity material, declared mutable "
            f"projection metadata, nor decomposed: {unaccounted}. Add each to "
            "CANDIDATE_LOGICAL_MATERIAL_FIELDS, CANDIDATE_REVISION_MATERIAL_FIELDS or "
            "CANDIDATE_MUTABLE_PROJECTION_FIELDS, or to DECOMPOSED_CANDIDATE_FIELDS if it "
            "is addressed under other names, so the partition stays total",
        )
    for left, right, label in (
        (CANDIDATE_LOGICAL_MATERIAL_FIELDS, CANDIDATE_REVISION_MATERIAL_FIELDS, "identity"),
        (CANDIDATE_MUTABLE_PROJECTION_FIELDS, CANDIDATE_LOGICAL_MATERIAL_FIELDS, "logical"),
        (CANDIDATE_MUTABLE_PROJECTION_FIELDS, CANDIDATE_REVISION_MATERIAL_FIELDS, "revision"),
    ):
        overlap = sorted(left & right)
        if overlap:
            raise CandidateContractError(
                "field_classified_twice",
                f"fields classified as both {label} material: {overlap}",
            )


verify_candidate_field_partition()


@dataclass(frozen=True)
class MentionPair:
    """The mentions one reading is about, canonicalised per arity mode.

    The bucket key of :class:`RelationCandidateSet`. Orientation follows the same rule as
    identity: sorted for ``UNDIRECTED``, order-preserving for ``DIRECTED``. For ``NARY`` the
    two fields are the entry-point pair while :attr:`role_signature` keeps distinct role
    shapes apart — an n-ary hypothesis has no pair, it has a shape, and flattening it onto a
    pair would merge ``Employment{person, org}`` with ``Employment{person, org, role}``.
    """

    arity_mode: RelationArityMode
    subject_mention_ref: str
    object_mention_ref: str
    role_signature: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "arity_mode", RelationArityMode(self.arity_mode))

    @classmethod
    def of(cls, candidate: RelationCandidate) -> MentionPair:
        """The pair key a candidate belongs to, derived from it and never transcribed."""
        signature = ""
        if candidate.arity_mode is RelationArityMode.NARY:
            signature = digest128(
                canonical_material(
                    [[b.role, b.member_ref] for b in candidate.role_assignments]
                )
            )
        return cls(
            arity_mode=candidate.arity_mode,
            subject_mention_ref=candidate.subject_mention_ref,
            object_mention_ref=candidate.object_mention_ref,
            role_signature=signature,
        )

    @property
    def identity(self) -> tuple[str, str, str, str]:
        """The canonical key: sorted for ``UNDIRECTED``, ordered for the rest."""
        first, second = self.subject_mention_ref, self.object_mention_ref
        if self.arity_mode is RelationArityMode.UNDIRECTED:
            first, second = sorted((first, second))
        return (first, second, str(self.arity_mode), self.role_signature)

    @property
    def members(self) -> tuple[str, str]:
        """The order-normalised member pair, for reporting rather than for identity."""
        low, high = sorted((self.subject_mention_ref, self.object_mention_ref))
        return (low, high)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arity_mode": str(self.arity_mode),
            "subject_mention_ref": self.subject_mention_ref,
            "object_mention_ref": self.object_mention_ref,
            "role_signature": self.role_signature,
        }


@dataclass(frozen=True)
class MentionPairGroup:
    """Every reading proposed over one mention pair, in the one deterministic order."""

    pair: MentionPair
    candidates: tuple[RelationCandidate, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidates", tuple(sorted(self.candidates, key=_candidate_order))
        )

    @property
    def statuses(self) -> tuple[CandidateStatus, ...]:
        """Every disposition present, in deterministic order; more than one is a signal."""
        return tuple(sorted({c.candidate_status for c in self.candidates}, key=str))

    @property
    def readings(self) -> tuple[str, ...]:
        """The distinct logical keys proposed here; more than one is a contested pair."""
        return tuple(sorted({c.logical_candidate_id for c in self.candidates}))

    @property
    def is_contested(self) -> bool:
        """Whether this pair holds more than one distinct hypothesis or disposition."""
        return len(self.readings) > 1 or len(self.statuses) > 1

    def admissible(self) -> tuple[RelationCandidate, ...]:
        """Only the readings that may become claims."""
        return tuple(c for c in self.candidates if c.is_admissible)


class CandidateConflictKind(StrEnum):
    """What kind of disagreement a :class:`CandidateConflict` reports.

    Two kinds are reported and the exclusions are as load-bearing as the inclusions.
    Disjoint temporal hypotheses over one pair are **not** a conflict (016 edge case:
    disjoint intervals are not a contradiction). Two different operators over one pair are
    **not** a conflict: ``A works_for B`` and ``A founded B`` are two true things, and
    labelling them a disagreement would be a heuristic resolving in place of a decision.
    A pair holding three proposals, or one reading scored twice, is *contested* — reported
    by :attr:`MentionPairGroup.is_contested`, which is not a contradiction.
    """

    DISPOSITION_DISAGREEMENT = "disposition_disagreement"
    INVERTED_READING = "inverted_reading"


@dataclass(frozen=True)
class CandidateConflict:
    """Readings over one member pair that cannot all hold. Both always survive (I-3, FR-006).

    ``candidates`` is every reading involved — never a winner, never a subset. There is no
    field on this object a caller could use to pick, and that is deliberate: resolving a
    conflict is an admission decision with an owner, taken elsewhere, and a type that made it
    easy to do it here would eventually have it done here.
    """

    kind: CandidateConflictKind
    members: tuple[str, str]
    candidates: tuple[RelationCandidate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", CandidateConflictKind(self.kind))
        object.__setattr__(
            self, "candidates", tuple(sorted(self.candidates, key=_candidate_order))
        )

    @property
    def readings(self) -> tuple[str, ...]:
        """The distinct logical hypotheses involved, in deterministic order."""
        return tuple(sorted({c.logical_candidate_id for c in self.candidates}))

    @property
    def statuses(self) -> tuple[CandidateStatus, ...]:
        return tuple(sorted({c.candidate_status for c in self.candidates}, key=str))


def _candidate_order(candidate: RelationCandidate) -> tuple[str, str, str]:
    """The one total order every enumeration in this module uses.

    A function of content alone — both ids are content addresses — so the order does not
    depend on the order a producer collected its candidates in, and two processes replaying
    the same extractions see the same sequence. ``content_hash`` is the tiebreak, so two
    readings that somehow share both ids still order deterministically.
    """
    return (candidate.logical_candidate_id, candidate.candidate_id, candidate.content_hash)


@dataclass(frozen=True)
class RelationCandidateSet:
    """A group of readings, and the only place that asks what they disagree about.

    A read-side value: it groups, orders and reports, and it has no method that drops,
    merges or resolves anything. Contradiction *reasoning* is out of scope for 016 and this
    module does not begin it — the contribution is that the disagreement is reachable and
    named, so a later layer can rank it on the record rather than inferring that one existed.

    Nothing is deduplicated. An idempotent re-write appears twice rather than silently
    collapsing, and :meth:`divergent_candidate_ids` distinguishes a re-write (one
    ``content_hash`` per id) from a lost update (several) — the same bounded, checked residual
    that :func:`domain.relation_identity.detect_content_divergence` reports for claims.
    """

    candidates: tuple[RelationCandidate, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidates", tuple(sorted(self.candidates, key=_candidate_order))
        )

    def __iter__(self) -> Iterator[RelationCandidate]:
        return iter(self.candidates)

    def __len__(self) -> int:
        return len(self.candidates)

    def __bool__(self) -> bool:
        return bool(self.candidates)

    def __contains__(self, candidate_id: object) -> bool:
        return any(c.candidate_id == candidate_id for c in self.candidates)

    def ordered(self) -> tuple[RelationCandidate, ...]:
        """Every reading in :func:`_candidate_order` — the one order callers may rely on."""
        return self.candidates

    def by_pair(self) -> tuple[MentionPairGroup, ...]:
        """Every distinct mention pair, in deterministic key order, with its readings.

        The answer to "what was proposed between these two mentions", which is the question a
        candidate layer exists to make answerable before anything is admitted.
        """
        pairs: dict[tuple[str, str, str, str], MentionPair] = {}
        members: dict[tuple[str, str, str, str], list[RelationCandidate]] = {}
        for candidate in self.candidates:
            pair = candidate.target_key
            key = pair.identity
            pairs.setdefault(key, pair)
            members.setdefault(key, []).append(candidate)
        return tuple(
            MentionPairGroup(pair=pairs[key], candidates=tuple(members[key]))
            for key in sorted(members)
        )

    def for_pair(self, pair: MentionPair) -> tuple[RelationCandidate, ...]:
        """Every reading over exactly ``pair``, in the one deterministic order."""
        return tuple(c for c in self.candidates if c.target_key == pair)

    def for_mentions(
        self,
        subject_mention_ref: str,
        object_mention_ref: str,
        arity_mode: RelationArityMode = RelationArityMode.DIRECTED,
    ) -> tuple[RelationCandidate, ...]:
        """Shorthand for :meth:`for_pair`; the pair key is derived, never transcribed."""
        pair = MentionPair(
            arity_mode=arity_mode,
            subject_mention_ref=subject_mention_ref,
            object_mention_ref=object_mention_ref,
        )
        return self.for_pair(pair)

    def with_status(self, status: CandidateStatus) -> RelationCandidateSet:
        """A set holding only the readings in one disposition, order preserved."""
        wanted = CandidateStatus(status)
        return RelationCandidateSet(
            candidates=tuple(c for c in self.candidates if c.candidate_status is wanted)
        )

    @property
    def admissible(self) -> tuple[RelationCandidate, ...]:
        """The readings :meth:`RelationCandidate.to_claim` would accept."""
        return tuple(c for c in self.candidates if c.is_admissible)

    def by_logical_candidate_id(self, logical_candidate_id: str) -> tuple[RelationCandidate, ...]:
        """Every revision of one hypothesis — the answer to "what did we make of this?"."""
        return tuple(c for c in self.candidates if c.logical_candidate_id == logical_candidate_id)

    def contradictory(self) -> tuple[CandidateConflict, ...]:
        """Every genuine disagreement, deterministically ordered. Nothing is resolved.

        Reported, never repaired, and never filtered: both sides of every conflict stay in
        :attr:`candidates` and both are attached to the conflict, so a caller that wants a
        decision has to make one explicitly (I-3, FR-006).
        """
        found: list[CandidateConflict] = []
        for group in self.by_pair():
            found.extend(_disposition_conflicts(group))
        found.extend(_inverted_conflicts(self.candidates))
        return tuple(
            sorted(
                found,
                key=lambda conflict: (
                    conflict.members,
                    str(conflict.kind),
                    conflict.readings,
                ),
            )
        )

    def divergent_candidate_ids(self) -> tuple[str, ...]:
        """Ids whose readings disagree on a mutable projection field only.

        Not an integrity break — ``confidence`` is declared mutable precisely so a
        re-scoring pass can restate it — but two candidates under one id is usually a lost
        update, and that is worth seeing rather than having the later write silently win.

        Two benign instances are reported here and the caller should recognise both, because
        a false alarm on a conflict report is how a real one gets ignored. A re-scoring
        pass changing only ``confidence``, which is what the declaration is for. And an
        ``UNDIRECTED`` reading recorded twice with its mentions in opposite order: the
        logical and revision ids are equal by construction, while ``content_hash`` is not,
        because the content hash is taken over the *serialised* field set and that one keeps
        the order the producer supplied. :class:`domain.relation_claim.RelationClaim` has
        the identical residual and
        :func:`domain.relation_identity.detect_content_divergence` names
        ``subject_ref``/``object_ref`` for it, so the two layers agree rather than drift.
        """
        buckets: dict[str, set[str]] = {}
        for candidate in self.candidates:
            buckets.setdefault(candidate.candidate_id, set()).add(candidate.content_hash)
        return tuple(sorted(cid for cid, hashes in buckets.items() if len(hashes) > 1))


def _disposition_conflicts(group: MentionPairGroup) -> tuple[CandidateConflict, ...]:
    """Readings of one hypothesis that both supported it and ruled against it.

    Grouped by ``logical_candidate_id`` rather than by mention pair, so a supported reading
    and a rejected reading of the *same* extraction are recognised as a conflict about one
    thing. Two readings with different logical ids over the same pair are a contested pair,
    which :attr:`MentionPairGroup.is_contested` reports — they are not a contradiction, and
    calling them one would be a heuristic standing in for an admission decision.
    """
    by_logical: dict[str, list[RelationCandidate]] = {}
    for candidate in group.candidates:
        by_logical.setdefault(candidate.logical_candidate_id, []).append(candidate)

    conflicts: list[CandidateConflict] = []
    for logical in sorted(by_logical):
        readings = by_logical[logical]
        supported = [c for c in readings if c.candidate_status is CandidateStatus.SUPPORTED]
        ruled_against = [c for c in readings if c.is_contradicting]
        if supported and ruled_against:
            conflicts.append(
                CandidateConflict(
                    kind=CandidateConflictKind.DISPOSITION_DISAGREEMENT,
                    members=group.pair.members,
                    candidates=tuple([*supported, *ruled_against]),
                )
            )
    return tuple(conflicts)


def _inverted_conflicts(
    candidates: Sequence[RelationCandidate],
) -> tuple[CandidateConflict, ...]:
    """One directed type asserted in both orientations over one member pair.

    Reported and deliberately **not** resolved. Whether a relation is symmetric is declared on
    the operator (:attr:`semantic.operators.RelationOperator.symmetric`) and is invisible from
    a candidate, so one candidate asserting ``A works_for B`` and another asserting
    ``B works_for A`` is a disagreement the platform must be able to *see* and an admission
    decision must be entitled to settle — not something the grouping layer settles by keeping
    whichever orientation happened to sort first.

    Only ``DIRECTED`` readings are considered, and only within one operator identity: two
    different relation types over the same members are two relations, and an undirected type
    is not inverted by construction.
    """
    buckets: dict[tuple[tuple[str, str], tuple[str, str]], list[RelationCandidate]] = {}
    for candidate in candidates:
        if candidate.arity_mode is not RelationArityMode.DIRECTED:
            continue
        low, high = sorted(
            (candidate.subject_mention_ref, candidate.object_mention_ref)
        )
        key = (candidate.relation_ref.identity, (low, high))
        buckets.setdefault(key, []).append(candidate)

    conflicts: list[CandidateConflict] = []
    for key in sorted(buckets):
        readings = buckets[key]
        orientations = {(c.subject_mention_ref, c.object_mention_ref) for c in readings}
        if len(orientations) > 1:
            conflicts.append(
                CandidateConflict(
                    kind=CandidateConflictKind.INVERTED_READING,
                    members=key[1],
                    candidates=tuple(readings),
                )
            )
    return tuple(conflicts)


__all__ = [
    "ADMISSIBLE_CANDIDATE_STATUSES",
    "CANDIDATE_LOGICAL_MATERIAL_FIELDS",
    "CANDIDATE_MUTABLE_PROJECTION_FIELDS",
    "CANDIDATE_REVISION_MATERIAL_FIELDS",
    "CLAIM_ONLY_FIELDS",
    "CONTRADICTING_CANDIDATE_STATUSES",
    "DECOMPOSED_CANDIDATE_FIELDS",
    "LOGICAL_CANDIDATE_ID_PREFIX",
    "REVISION_CANDIDATE_ID_PREFIX",
    "CandidateConflict",
    "CandidateConflictKind",
    "CandidateContractError",
    "CandidateNotAdmissible",
    "CandidateStatus",
    "MentionPair",
    "MentionPairGroup",
    "RelationCandidate",
    "RelationCandidateSet",
    "SpanRef",
    "TemporalBasis",
    "TemporalHypothesis",
    "recompute_candidate_identity",
    "verify_candidate_field_partition",
    "verify_candidate_identity",
    "verify_candidate_material_partition",
]
