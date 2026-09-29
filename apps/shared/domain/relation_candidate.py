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

* ``logical_candidate_id`` (``CAND-``) answers *which relational configuration this is* — the
  :class:`domain.predicate_signature.PredicateSignature`, the canonical argument slots, the
  participant configuration, the declared symmetry, the polarity, the arity shape and the tenant,
  and nothing else. It is derived by :func:`domain.predicate_signature.logical_candidate_id`, so
  the predicate term is a structural projection and never a raw surface, a mention-id text, a
  producer, a span, a confidence, a reference collection or an ontology mapping. Every revision of
  one configuration shares it, so a re-read under a different extractor — or under a different
  mapping vocabulary — is recognisably the same hypothesis.
* ``candidate_id`` (``CNDR-``) answers *this reading of it* — the logical id plus the mention
  references that were named, the role words and surface the observation used, the regime, the
  extraction semantics, the guessed window, the spans, the evidence and the disposition. A
  different extractor version is a different candidate, and the field is in the id material so it
  cannot be forgotten.

**A signature is required for a logical id, and its absence is the honest answer.** The contract is
``specs/021-entity-relation-extraction-finalization/data-model.md`` part 5.4: a candidate with
``predicate_signature is None`` gets ``logical_candidate_id = ""``, is addressable only by
``candidate_id``, and :func:`verify_candidate_identity` refuses to certify it with
``unaddressed_logical_identity``. There is deliberately no surface-keyed fallback term. That was
this module's own defect until now — ``_logical_material`` passed ``relation_surface`` into
``logical_material``'s ``relation_type`` parameter, so the words the observation used *were* the
predicate term — and reintroducing it under a "degraded" tag would be the same violation with a
version label on it, plus a second code path deriving ids, of which the second would be the wrong
one. It would also be unreachable: the only way to obtain a signature is to read a construction,
so a candidate carrying one has been read and an unread one has not.

Arity handling is delegated to :func:`domain.predicate_signature.canonical_participant_ordering`
rather than reimplemented, so no caller can introduce a second ordering. It is **not** delegated to
:func:`domain.relation_identity.logical_material`, which is the *claim* layer's shape: that one
sorts ``UNDIRECTED`` members by mention-id text through a ``set``, and takes ``NARY`` roles as free
text, so wiring it here would key a candidate on the id minter's format and on the vocabulary a
producer happened to use. Changing it there re-keys every stored ``RL-`` id and is a
claim-layer migration; see ``data-model.md`` part 4.7 and ``repair/A2-identity-subsystem.md`` U8.

Two deliberate divergences from ``RL-``/``RC-``: ``tenant_id`` is in the *logical* material here,
and ``candidate_status`` is in the *revision* material. Neither breaks the logical/revision split —
a tenant never changes across revisions of one hypothesis — and both are required by the properties
that matter here. Constitution IV forbids two tenants' hypotheses bucketing under one key. And a
disposition is a *finding about a reading*, not a lifecycle transition on a fixed body of content:
a candidate proposed and a candidate checked and found to hold are different states of knowledge,
and giving them one id would conflate them in every store keyed on it.
:meth:`RelationCandidate.with_status` drops the revision id for exactly that reason and keeps the
logical one, so "the same hypothesis, now rejected" stays one filter.

**Three epistemic states, three axes, and the candidate carries two of them.** ``ARBITRATION`` §3
forbids collapsing them, and this module is where that is enforced rather than where it is
described. ``PredicateHypothesis.resolution_state`` answers *what the vocabulary makes of the
predicate* and lives on the hypothesis. :attr:`RelationCandidate.assembly_state` answers *whether
the producers agreed on the shape of the reading* and lives on the candidate.
:attr:`CandidateStatus.CONTRADICTED` answers *whether the assertion was denied* and is the only one
of the three that means something about the world. ``CONFLICTING`` on the candidate is therefore
**not** ``CONTRADICTED`` on the status: "Acme acquired Beta" and "Acme did not acquire Beta" are
incompatible readings, neither denies the other, and a candidate assembled from the pair says
``PROPOSE`` with ``assembly_state = CONFLICTING``. See :class:`CandidateAssemblyState`.

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

from domain.predicate_hypothesis import PredicateHypothesis
from domain.predicate_signature import (
    ArgumentSlot,
    ParticipantBinding,
    Polarity,
    PredicateSignature,
    SignatureContractError,
    logical_candidate_material,
    stable_participant_fingerprint,
)
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

    #: Several producers read the same structure and their readings were assembled into
    #: one (feature 019, FR-032).
    #:
    #: Added because every existing member is a *single-producer* method and none of them
    #: can describe an assembled reading honestly. Recording ``LEXICAL_PATTERN`` on a
    #: candidate built from a table header, a hyperlink and a sentence would put a false
    #: account of how the reading was made into its **identity material** - so the
    #: falsehood would live in the content address rather than in a description, and a
    #: replay would reproduce it. ``RULE`` would be no better: no rule fired, and assembly
    #: is a different kind of thing from a rule.
    #:
    #: It names *how the reading was assembled*, not whether the producers agreed; that is
    #: what ``signal_refs`` and FR-034's independence count are for. A candidate assembled
    #: from a single producer is also ``ORCHESTRATED``, because it took the same code path -
    #: and the number of producers is already in the address.
    ORCHESTRATED = "orchestrated"

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


class CandidateAssemblyState(StrEnum):
    """How one reading stands against the *other* readings of the same participant configuration.

    **A separate axis from :class:`CandidateStatus`, and never merged with it.** ``ARBITRATION`` §3
    names three states that used to be one and must be three:

    ==================================  =============  ==========================================
    ==================================  ==============  ===============================
    state                               lives on        means
    ==================================  ==============  ===============================
    ``PredicateHypothesis.resolution_state``  the hypothesis  incompatible *semantic* readings
    :attr:`RelationCandidate.assembly_state`  the candidate  incompatible *structural* readings
    ``CandidateStatus.CONTRADICTED``    the candidate   the **assertion is denied**
    ==================================  ==============  ===============================

    So this enum says *whether the producers described one participant configuration in
    incompatible shapes* — arity, direction, polarity, and (once role slots become a reading-key
    component) slot occupancy. It says **nothing** about whether the relation holds, and
    ``CONFLICTING`` here is **not** ``CONTRADICTED`` there: "Acme acquired Beta" and "Acme did not
    acquire Beta" are incompatible readings, but neither of them *denies* the other, and a
    candidate built from the pair says ``PROPOSE`` with ``assembly_state = CONFLICTING`` rather
    than ``candidate_status = CONTRADICTED``. :class:`CandidateStatus` stays reserved for a
    positive reading set against an explicit denial, and widening it to carry a structural
    disagreement is exactly the dumping ground §3 forbids.

    **The members, and which of them assembly writes.** ``CONSISTENT`` is the ordinary state and the
    default: one reading, or several that agreed on every structural key.

    ``CONFLICTING`` is written by :func:`semantic_path.assembly.assemble` when a pair's readings
    disagree on a structural axis, and it goes on **every reading of that pair** — the disagreement
    is about the configuration, and which side of it a given reading sits on does not make that
    reading consistent. The other reading is preserved beside it, never dropped, so a reader sees
    both.

    ``AMBIGUOUS`` is declared and **not written by assembly**, and the reason is the whole point of
    the separation. Several *compatible* readings of one pair are two semantic claims about the
    world (``"CEO of"`` and ``"founder of"``) or one predicate with several defensible operator
    names, and both of those already have a home: the pair is reported contested, and the
    alternatives live on :attr:`predicate_hypothesis`'s ``alternative_refs`` with
    ``resolution_state = AMBIGUOUS``. Marking them here as well would be the second axis reporting
    the first axis's finding — a candidate that reads "ambiguous" for a reason that has nothing to
    do with its structure. It is here because a closed three-member vocabulary is what
    ``ARBITRATION`` §3 specifies and because a caller building a candidate by hand (a
    :class:`domain.predicate_hypothesis.PredicateHypothesis` producing a second reading of a
    surface it resolved itself) has to be able to say so.

    **Revision material, never logical material, and the reason is worth stating in full.** Whether
    a proposition is *hypothesised at all* is settled by the two mentions and the predicate
    signature; how the producers who read it agreed about its shape is a finding about the reading
    process, and a finding about a process is evidence. Two readings of one configuration that
    disagree about arity are **one** hypothesis with two ``candidate_id`` values — the same shape
    FR-039 gives predicate resolution, and the same reason a re-read by a second instrument must
    not fork the hypothesis into two. If ``assembly_state`` entered the logical material, a second
    producer disagreeing about a shape would mint a second ``logical_candidate_id``, and the
    disagreement this field exists to record would destroy the one thing the split exists to
    preserve.
    """

    CONSISTENT = "consistent"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"


#: The states that mean a structural disagreement was found, as a name rather than a literal
#: comparison. :attr:`RelationCandidate.is_structurally_contested` is the question callers
#: actually ask, and a one-member set is what keeps a fourth member from being added without
#: somebody deciding what it means.
CONFLICTING_ASSEMBLY_STATES: frozenset[CandidateAssemblyState] = frozenset(
    {CandidateAssemblyState.CONFLICTING}
)


#: The disposition set the *old* lifecycle called admissible, kept as a named assessment
#: rather than a gate (feature 019, CD-1).
#:
#: This is no longer consulted by admission. It is what
#: :meth:`RelationCandidateSet.supported` reports, and nothing more: a compatibility
#: projection for callers that still filter on a label.
#:
#: Why the change matters. The gate this replaces made ``SUPPORTED`` the precondition for
#: crossing into the claim layer, and ``PROPOSE`` was excluded "on purpose" - but the
#: exclusion only tested what a caller had *written on the reading*, not what the evidence
#: showed. A label is trivially writable, so the gate could be satisfied by assertion while
#: a genuinely unvalidated reading passed as checked. The real gate is
#: :func:`domain.relation_claim_material.validate` followed by
#: :func:`domain.relation_claim_material.admit`, which read the evidence and can refuse
#: independently of anything a caller says.
#:
#: What is preserved. ``PROPOSE`` readings are still fully first-class - they are what
#: extraction produces, they are never deleted (I-3, FR-006), and they reach the claim layer
#: through ``build``/``validate``/``admit`` on their own merits. Nothing that used to be
#: buildable became unbuildable; what changed is that the label stopped being the test.
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

#: Fields deciding *which relational configuration this is*. Covered by
#: :meth:`RelationCandidate._logical_material` and entering ``logical_candidate_id``, so every
#: revision of one configuration shares them. Exactly ``data-model.md`` part 5.1's seven material
#: keys, one candidate field each, with ``identity_schema`` supplied by the identity subsystem as
#: a constant rather than by a field:
#:
#: * ``predicate_signature`` is the **sole** predicate term. It was ``relation_surface`` here, and
#:   that was the defect this feature exists to remove: the words the observation used were the
#:   predicate term of a logical id, so ``"works for"`` and ``"Works For"`` could not meet.
#: * ``participants`` is the participant *configuration* — the canonical slot ordering and the
#:   realisation-invariant fingerprints. ``subject_mention_ref`` / ``object_mention_ref`` /
#:   ``role_assignments`` are **not** here and never may be: a mention-id *text* is a minting
#:   artefact (``data-model.md`` part 4.3), and ``RelationRoleBinding.role`` is free text, so
#:   ``purchaser`` vs ``buyer`` would fork the id. Both are revision material instead.
#: * ``commutative_slots`` is the declared symmetry marker, always present and never inferred from
#:   a missing or unknown direction (``data-model.md`` part 4.5).
#: * ``polarity`` is the structure of the assertion, and lives on the candidate rather than the
#:   signature for exactly that reason (``data-model.md`` part 1.1).
#: * ``arity_mode`` is a **checked redundancy**: ``logical_candidate_material`` derives it from the
#:   occupied slots and ``commutative_slots`` and refuses a declared value that disagrees
#:   (``data-model.md`` part 2.5 check 4). It is verified, never independently asserted.
#:
#: ``schema_version`` is absent on purpose: it is the *operator* version, so a hypothesis read
#: under a newer operator contract is a new reading of the same hypothesis, not a new hypothesis —
#: exactly as ``RL-``/``RC-`` treat it.
CANDIDATE_LOGICAL_MATERIAL_FIELDS: frozenset[str] = frozenset(
    {
        "tenant_id",
        "arity_mode",
        "predicate_signature",
        "participants",
        "commutative_slots",
        "polarity",
    }
)

#: Fields making a revision *itself*. A change here means a different reading of the same
#: configuration: a different mention, a different set of role words, a different surface, a
#: different mapping, a different extractor, a different regime, a different guessed window, or a
#: different disposition. All enter ``candidate_id``, so none can be edited into a candidate
#: without minting a new one.
#:
#: Five of these are here rather than in :data:`CANDIDATE_LOGICAL_MATERIAL_FIELDS` because they
#: are *evidence or referential*, and each moved for a stated reason:
#:
#: - ``relation_surface`` / ``predicate_hypothesis`` — the words the observation used, and what the
#:   vocabulary later made of them. A mapping is a later, versioned step; keying identity on it
#:   would give "originator of" a different logical id the moment a regime recognised it, splitting
#:   one hypothesis in two. So recognition shows up here as a new *reading* (``data-model.md``
#:   part 5.3 step 5).
#: - ``relation_type`` — the operator this candidate was mapped to. Same reason, and it is the
#:   documented head of the "mapping below identity" inversion this wave removes.
#: - ``subject_mention_ref`` / ``object_mention_ref`` / ``role_assignments`` — *which* mentions were
#:   read, and the free-text role words the observation used for them. They must stay addressable,
#:   so they are in ``candidate_id``: two readings over different mentions are different readings
#:   and may not collide. They are not in ``logical_candidate_id`` because identity is over the
#:   participant's realisation-invariant fingerprint, not over the id minter's text.
#: - ``assembly_state`` — whether the producers agreed on the **shape** of this reading. Here
#:   rather than in the logical material for the reason :class:`CandidateAssemblyState` gives in
#:   full: two readings that disagree about a participant configuration's arity are one hypothesis
#:   with two ``candidate_id`` values, and putting the verdict in the logical key would mint a
#:   second ``logical_candidate_id`` for the very disagreement the field records.
CANDIDATE_REVISION_MATERIAL_FIELDS: frozenset[str] = frozenset(
    {
        "schema_version",
        "relation_type",
        "relation_surface",
        "subject_mention_ref",
        "object_mention_ref",
        "role_assignments",
        "predicate_hypothesis",
        "temporal_hypothesis",
        "observed_at",
        "context_ref",
        "semantic_regime_ref",
        "observation_refs",
        "evidence_refs",
        "signal_refs",
        "extraction_method",
        "extractor_version",
        "extraction_rule_id",
        "trigger_span",
        "supporting_spans",
        "investigation_id",
        "recorded_by",
        "candidate_status",
        "assembly_state",
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
#:
#: Both parts are **revision** material. That is the whole of the change this wave made to
#: them: ``relation_type`` used to be logical material, i.e. the predicate term of a logical id,
#: which made a candidate's identity a function of the vocabulary the platform happened to have.
#: The operator is still legible in the record — in ``candidate_id`` — which is where a mapping
#: belongs (``data-model.md`` part 5.3 step 5).
DECOMPOSED_CANDIDATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {"relation_ref": ("relation_type", "schema_version")}
)

#: How each :data:`CANDIDATE_LOGICAL_MATERIAL_FIELDS` entry reaches the material
#: :func:`domain.predicate_signature.logical_candidate_material` builds. One field, one material
#: key, no exceptions — so the declared set and the emitted set can be reconciled mechanically
#: rather than by reading both and hoping. ``identity_schema`` is the seventh material key and is
#: deliberately *not* here: it is a constant owned by the identity subsystem
#: (``IDENTITY_SCHEMA_VERSION``), not a candidate field, and a version that lived on the candidate
#: would be the operator version in the identity term — the same defect as carrying ``relation_ref``
#: (``data-model.md`` part 1.1).
CANDIDATE_LOGICAL_MATERIAL_KEYS: Mapping[str, str] = MappingProxyType(
    {
        "tenant_id": "tenant_id",
        "arity_mode": "arity_mode",
        "predicate_signature": "predicate_signature",
        "participants": "participants",
        "commutative_slots": "commutative_slots",
        "polarity": "polarity",
    }
)

#: The one material key that is not a candidate field, named so the reconciliation above is
#: exact in both directions.
CANDIDATE_LOGICAL_MATERIAL_CONSTANT_KEYS: frozenset[str] = frozenset({"identity_schema"})


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
    relation_ref: RelationRef | None = None
    arity_mode: RelationArityMode = RelationArityMode.DIRECTED
    role_assignments: tuple[RelationRoleBinding, ...] = ()

    predicate_signature: PredicateSignature | None = None
    """The structural projection of the predicate realisation. **Required** for a
    ``logical_candidate_id``; ``None`` means the construction was never read, which is the honest
    state and not a gap to paper over with a surface.

    This is the sole predicate term of the logical id (``data-model.md`` part 5.1). It is derived
    *before* ontology mapping and is never re-derived from one, so swapping the whole mapping
    apparatus leaves every logical id byte-identical while a recognition shows up as a new
    ``candidate_id`` (part 5.3). The words the observation used are :attr:`relation_surface`, and
    they are evidence: ``"works for"`` and ``"Works For"`` reach one signature, so they reach one
    logical id, while both surfaces survive as two ``Text`` values on two records.
    """

    participants: tuple[ParticipantBinding, ...] = ()
    """The participant *configuration* the signature's slots are occupied by: one
    :class:`domain.predicate_signature.RoleBinding` plus the mention each fills it, per slot.

    Distinct from :attr:`subject_mention_ref` / :attr:`object_mention_ref` and from
    :attr:`role_assignments`, and the distinction is load-bearing rather than duplicative. The
    mention refs and the free-text roles are *what this reading named* — revision material, and
    citable. The participant bindings are *where each participant sat in the reading*, and the
    mention inside one is digested by :func:`stable_participant_fingerprint`, which excludes the
    mention-id text, the producer, the span, the type and the confidence on purpose
    (``data-model.md`` part 4.3). Two realisations of one configuration in two documents have two
    spans and two mention ids and one logical id.

    Construction refuses a set that disagrees with the refs about *which* mentions this reading is
    about, so the two can never become two truths. Empty is the ordinary state today: the only way
    to obtain a signature is to read a construction, and no producer in this repository parses one
    yet (``repair/A2-identity-subsystem.md`` D6.3 H1).
    """

    commutative_slots: frozenset[ArgumentSlot] = frozenset()
    """Declared symmetry, always present and never inferred (``data-model.md`` part 4.5).

    A ``frozenset()`` is the ordinary answer and is *not* a statement that the relation is
    directed — it is a statement that nobody declared it symmetric. Symmetry may only come from an
    explicit declared-symmetry contract: "do not infer symmetry merely because the extractor did
    not know direction" (brief section 53). It is identity-bearing because a symmetric and an
    asymmetric reading of one pair are different claims, and both are meant to stand.
    """

    polarity: Polarity = Polarity.ASSERTED
    """Whether the assertion stands, is denied, or is held open (``data-model.md`` part 9).

    It lives on the candidate and not on the signature, so ``acquire`` is one predicate under
    assertion and under denial — and it enters logical material, so "John did not acquire Acme" is
    a *different hypothesis* from "John acquired Acme" (brief section 109 case H). The default is
    ``ASSERTED`` because it is not a guess about the world: it says that nothing in this reading
    observed a denial, which is the state a positive reading is in. ``Polarity.UNCERTAIN`` is the
    explicit value for a held-open reading, and ``DENIED`` the explicit value for a negation.
    """

    predicate_hypothesis: PredicateHypothesis | None = None
    """How far the platform's vocabulary reaches on this relation.

    Optional :attr:`relation_ref` is the whole point (CD-6): a relation observed in the
    world whose type nobody declares must be representable, with its surface intact,
    rather than discarded or given an invented type.

    Left ``None`` when :attr:`relation_ref` plus :attr:`relation_surface` already say
    everything, and derived from them, so existing callers keep working unchanged.
    """

    relation_surface: str = ""
    """The words the observation used, kept whatever the platform understands of them.

    This is what makes an unresolved predicate readable rather than merely absent. A
    relation the platform cannot name still said *something* — "originator of", a table
    header, a link target — and losing that because the vocabulary had no entry would be
    losing the observation to the limits of the vocabulary (CD-7). It is also the field a
    later ``SemanticRegime`` reads to decide the same surface a different way.
    """

    context_ref: str = ""
    semantic_regime_ref: str = ""

    trigger_span: SpanRef | None = None
    supporting_spans: tuple[SpanRef, ...] = ()

    extraction_method: ExtractionStrategy = ExtractionStrategy.LEXICAL_PATTERN
    extractor_version: str = ""
    extraction_rule_id: str = ""

    observation_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    signal_refs: tuple[str, ...] = ()
    """The :class:`extractors.signals.signal.RelationSignal` observations this reading was
    assembled from (FR-032).

    **Revision material, not logical material, and the reason is worth stating.** Whether a
    relation is *hypothesised at all* is settled by the two mentions and the predicate
    surface; which observations back it is a separate fact that grows. So a second producer
    reporting the same relation does not create a second hypothesis - it creates a second
    *reading* of the first, under one ``logical_candidate_id``. That is the same shape as
    FR-039's predicate resolution, and it buys the same thing: a relation corroborated by
    three sources is visibly one hypothesis with three readings, rather than three
    hypotheses that happen to agree.

    It also makes the address depend on the evidence, which is what makes assembly
    deterministic under replay: two processes assembling the same set of signals derive the
    same ``candidate_id``, and a process that saw a different set of signals derives a
    different one. Neither can quietly produce a candidate that claims backing it does not
    have.

    Empty is legal and means what it says: a candidate constructed directly, by a caller or
    a later regime, that was not assembled from signals. The assembler never produces one
    (T032), but the type does not forbid it, because forbidding it here would make the
    predicate-resolution path - a regime producing a second reading of a surface it resolved
    itself - impossible to express.
    """

    temporal_hypothesis: TemporalHypothesis = TemporalHypothesis()
    candidate_status: CandidateStatus = CandidateStatus.PROPOSE
    assembly_state: CandidateAssemblyState = CandidateAssemblyState.CONSISTENT
    """Whether the producers that read this configuration agreed on its **shape** (ARBITRATION §3).

    Defaulted to :attr:`CandidateAssemblyState.CONSISTENT` because a candidate built by hand is a
    single reading and a single reading cannot disagree with itself; the assembler is what
    discovers a disagreement, by finding several readings of one pair. Kept adjacent to
    :attr:`candidate_status` because the two are the pair most easily confused, and the confusion is
    the defect this field was added to end.

    **Revision material, and never
    :attr:`~domain.relation_candidate.CandidateStatus.CONTRADICTED`.**
    Two readings of one configuration that disagree about arity share a ``logical_candidate_id``
    and differ in ``candidate_id`` — one hypothesis, two readings, and the disagreement is the
    evidence. See :class:`CandidateAssemblyState` for the full separation and why ``AMBIGUOUS`` is
    not written by assembly.
    """


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
        try:
            object.__setattr__(
                self, "assembly_state", CandidateAssemblyState(self.assembly_state)
            )
        except ValueError as exc:
            raise CandidateContractError(
                "invalid_assembly_state",
                "assembly_state must be a domain.relation_candidate.CandidateAssemblyState - "
                f"consistent, ambiguous or conflicting - got {self.assembly_state!r}. It is a "
                "closed three-member vocabulary rather than free text because it is the record of "
                "whether the producers agreed on the SHAPE of a reading, and a token nobody can "
                "read records nothing (ARBITRATION §3)",
            ) from exc
        if self.relation_ref is not None and not isinstance(self.relation_ref, RelationRef):
            raise CandidateContractError(
                "invalid_relation_ref",
                "relation_ref must be a semantic.contracts.RelationRef naming an operator "
                f"(relation_type, schema_version), or None; got "
                f"{type(self.relation_ref).__name__}"
                + (
                    f" of {self.relation_ref!r}. If that is a relation the vocabulary has no "
                    "entry for, pass it as relation_surface=... and leave relation_ref None - "
                    "an untyped relation is representable (CD-6) and keeps its words."
                    if isinstance(self.relation_ref, str)
                    else ""
                ),
            )
        object.__setattr__(self, "relation_surface", str(self.relation_surface or ""))
        if self.predicate_hypothesis is None:
            # The hypothesis is built from the *observed words only*. It used to fall back to
            # ``str(self.relation_ref.relation_type)``, which meant a candidate built with no
            # surface and a relation_ref got its predicate surface from the operator it was
            # mapped to - the mapping writing into the field identity keys on, and therefore
            # "mapping below identity" with the arrow reversed. The line was harmless to the old
            # material only because the old material keyed on the surface, so the two defects
            # hid each other: deleting the fallback without deleting the surface keying would
            # have silently changed every such id, and deleting the keying without deleting the
            # fallback would have left the identity a function of the vocabulary. Both are gone
            # in this commit (data-model.md part 7.1).
            #
            # A candidate with no surface and no signature is a candidate with no identity term.
            # That is the honest state, it is brief section 90's case, and it is *addressable*:
            # ``with_id`` still mints a ``candidate_id`` from the reading.
            object.__setattr__(
                self,
                "predicate_hypothesis",
                PredicateHypothesis(
                    relation_ref=self.relation_ref,
                    surface_form=self.relation_surface,
                ),
            )
        elif not isinstance(self.predicate_hypothesis, PredicateHypothesis):
            raise CandidateContractError(
                "invalid_predicate_hypothesis",
                "predicate_hypothesis must be a PredicateHypothesis, or None to derive one "
                f"from relation_ref and relation_surface, got "
                f"{type(self.predicate_hypothesis).__name__}",
            )
        elif self.relation_ref is not None and self.predicate_hypothesis.relation_ref is not None:
            if self.predicate_hypothesis.relation_ref != self.relation_ref:
                raise CandidateContractError(
                    "predicate_ref_disagrees_with_candidate",
                    f"relation_ref names {self.relation_ref}, but predicate_hypothesis names "
                    f"{self.predicate_hypothesis.relation_ref}; they are the same predicate and "
                    "must be stated once, consistently",
                )
        try:
            object.__setattr__(self, "polarity", Polarity(self.polarity))
        except ValueError as exc:
            raise CandidateContractError(
                "invalid_polarity",
                "polarity must be a domain.predicate_signature.Polararity - asserted, denied or "
                f"uncertain - got {self.polarity!r}. It is identity-bearing, so it is a closed "
                "vocabulary rather than free text (data-model.md part 9)",
            ) from exc
        if self.predicate_signature is not None and not isinstance(
            self.predicate_signature, PredicateSignature
        ):
            raise CandidateContractError(
                "invalid_predicate_signature",
                "predicate_signature must be a domain.predicate_signature.PredicateSignature, or "
                f"None for a reading whose construction was never read; got "
                f"{type(self.predicate_signature).__name__}. None is not a degraded mode - it is "
                "the state in which no logical_candidate_id is minted at all (data-model.md "
                "part 5.4).",
            )
        for participant in self.participants:
            if not isinstance(participant, ParticipantBinding):
                raise CandidateContractError(
                    "invalid_participant_binding",
                    "participants must hold domain.predicate_signature.ParticipantBinding values "
                    "- a RoleBinding plus the mention that fills it - got "
                    f"{type(participant).__name__}",
                )
        try:
            object.__setattr__(
                self,
                "commutative_slots",
                frozenset(
                    slot if isinstance(slot, ArgumentSlot) else ArgumentSlot(int(slot))
                    for slot in self.commutative_slots
                ),
            )
        except (TypeError, ValueError) as exc:
            raise CandidateContractError(
                "invalid_commutative_slot",
                "commutative_slots must hold structural ArgumentSlot values - the positions "
                "declared symmetric - and never free-text role names, got "
                f"{self.commutative_slots!r}",
            ) from exc
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
                f"{self.relation_surface or 'relation'} proposes "
                f"{self.subject_mention_ref!r} in relation to itself",
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
        self._verify_participants_name_the_same_mentions()

        # A *carried* address is checked against the derived one (feature 019, T037).
        #
        # Construction still does not compute ids it was not given - :meth:`with_id` remains
        # the explicit derivation, so building a candidate stays a plain value operation.
        # But when a caller does present an id, that id is a claim, and an unverified claim
        # about an address is the one thing I-1 cannot survive: a record edited after the
        # fact keeps its id, and every reference to it now points at content nobody recorded.
        #
        # This makes the platform uniform rather than novel. :class:`domain.
        # relation_claim_material.RelationClaimMaterial`, :class:`semantic.regime.
        # SemanticRegime` and :class:`domain.temporal_observation.
        # SourceTemporalObservation` all refuse a carried id that disagrees; the candidate
        # and the signal were the two that did not, and a constitutional property that two
        # types keep and two do not is not a property. The cost is one digest over a
        # candidate that arrived addressed, which it was going to pay in ``with_id`` anyway.
        if self.candidate_id or self.logical_candidate_id:
            derived_logical, derived_revision = recompute_candidate_identity(self)
            for carried, derived, label in (
                (self.logical_candidate_id, derived_logical, "logical_candidate_id"),
                (self.candidate_id, derived_revision, "candidate_id"),
            ):
                if carried and carried != derived:
                    raise CandidateContractError(
                        "candidate_id_mismatch",
                        f"candidate carries {label}={carried!r} but its own content "
                        f"addresses to {derived!r}; a content address is derived, never "
                        "trusted. Drop the field to have it computed, or fix the contents "
                        "that disagree with it",
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
        # ``signal_refs`` was the one reference collection left in caller order, and it is
        # revision material: it enters ``candidate_id``, so a producer that collected the same
        # signals in a different order minted a different address for the same reading. The
        # other four collections above were canonicalised here and this one was not, which left
        # replay determinism resting on ``semantic_path/assembly.py`` happening to sort at one
        # call site. Constitution Domain Invariant 12 (replay is a fixed point) is a property of
        # the type, not of a caller's diligence, so it is enforced here (data-model.md part 7.3,
        # FR-085).
        object.__setattr__(
            self, "signal_refs", tuple(sorted({str(r) for r in self.signal_refs if str(r).strip()}))
        )
        object.__setattr__(self, "participants", tuple(self.participants))

    @property
    def relation_type(self) -> str:
        """The operator's relation type, read off the reference rather than restated.

        Empty for an unresolved predicate, and empty is the honest answer: no operator was
        named, so there is no type to report. Callers that need to know *why* it is empty
        should read :attr:`predicate_hypothesis`, which distinguishes a surface nobody has
        typed from a reading with several defensible types.
        """
        return "" if self.relation_ref is None else self.relation_ref.relation_type

    @property
    def schema_version(self) -> str:
        """The operator version in force when the reading was produced (FR-029).

        Empty when no operator was named, for the same reason :attr:`relation_type` is.
        """
        return "" if self.relation_ref is None else self.relation_ref.schema_version

    @property
    def is_admissible(self) -> bool:
        """Whether this reading carries the ``SUPPORTED`` label. **Not** whether it may
        become a claim (feature 019, CD-1).

        The name is kept because callers read it, but the question it now answers is
        narrower and more honest than the one it used to: it reports a *disposition*,
        and a disposition is something a caller writes on a reading rather than something
        the evidence establishes. A reading with a ``PROPOSE`` label is not thereby
        inadmissible - it is simply unlabelled, and it reaches the claim layer through
        :func:`domain.relation_claim_material.build` / ``validate`` / ``admit`` on its
        evidence.

        To ask whether a reading can actually become a claim, ask admission:
        ``admit(build(...), validate(...))``. That answer is derived from evidence and
        can refuse; this one cannot.
        """
        return self.candidate_status in ADMISSIBLE_CANDIDATE_STATUSES

    @property
    def is_contradicting(self) -> bool:
        """Whether this reading asserts a checked failure."""
        return self.candidate_status in CONTRADICTING_CANDIDATE_STATUSES

    @property
    def is_structurally_contested(self) -> bool:
        """Whether a structural disagreement was recorded against this reading's configuration.

        The question callers ask about :attr:`assembly_state`, stated as a name so the verdict
        cannot be reached for by string comparison. **It is not
        :attr:`CandidateStatus.CONTRADICTED`** and reading it as that is the confusion
        ``ARBITRATION`` §3 exists to end: a structural disagreement is not a denial.
        """
        return self.assembly_state in CONFLICTING_ASSEMBLY_STATES

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
        """DEPRECATED (feature 019, CD-1) - retained for legacy callers, never a gate.

        **A disposition is no longer how a reading earns the right to become a claim.**
        The old contract made ``SUPPORTED`` the precondition: a caller set it, and
        ``to_claim`` demanded it. That made a *label* load-bearing, and a label is
        something a caller can simply write - so the gate tested what the caller believed
        rather than what the evidence showed, and a reading could be promoted by
        assertion. The real gate is
        :func:`~domain.relation_claim_material.validate` followed by
        :func:`~domain.relation_claim_material.admit`, which read the evidence and could
        refuse.

        So this method survives for callers that still ask for a differently-labelled
        reading, and :meth:`to_claim` survives for callers that still call it - but
        nothing in the production path sets a status in order to cross a boundary, and
        the path in ``semantic_path/execution.py`` no longer does either. Setting
        ``SUPPORTED`` here no longer buys anything, and calling
        :meth:`RelationCandidateSet.supported` no longer answers whether a reading is
        admissible.

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
        source_independence_groups: Sequence[Sequence[str]] = (),
        normalization_version: str = "",
        ontology_version: str = "",
        observed_at: datetime | None = None,
    ) -> RelationClaim:
        """DEPRECATED (feature 018, T016, FR-010) - use ``build``, ``validate`` then ``admit``.

        .. deprecated::
           This method fuses the two operations 018 split apart, and calling it means the
           hypothesis was never examined. It is retained only so the orchestrator and the 016
           suites keep working, and it will be re-pointed at the three-operation path rather than
           removed under a caller.

        **Why it is deprecated, precisely.** :func:`domain.relation_claim_material.build` now
        turns a reading into a
        :class:`domain.relation_claim_material.RelationClaimMaterial` and consults nothing -
        not the disposition, not a policy, not a report. :func:`domain.relation_claim_material.
        validate` then grades that material through
        :class:`semantic.validation.LayeredValidator`, which accepts unadmitted values
        (FR-011). Only :func:`domain.relation_claim_material.admit` commits. This method skips
        the middle step and hands :func:`~domain.relation_claim_material.admit` a report with
        **zero findings** - so nothing was validated and nothing says otherwise. That report is
        honest rather than a fabrication: an empty report reports no adverse finding, and
        :meth:`semantic.contracts.ValidationReport.unevaluated_stages` returns all six stages,
        which is exactly true. It is still the wrong thing to do, because the one question worth
        asking before a claim enters the graph is the one this path never asks.

        What did **not** change. The guard is intact: a non-``SUPPORTED`` reading still raises
        :class:`CandidateNotAdmissible`, because :func:`~domain.relation_claim_material.admit`
        reads the disposition and refuses - the guard moved, it did not weaken, and a caller that
        ignores the return value still cannot walk on with an unadmitted hypothesis. Identity is
        still derived exactly once: the material derives both ids at construction and
        :func:`~domain.relation_claim_material.admit` asserts they survive admission, so a caller
        cannot reach a claim whose ids disagree with its own contents. The
        :class:`domain.relation_claim.RelationContractError` raised for a malformed shape, the
        :class:`CandidateContractError` with code ``tenant_mismatch`` raised for a cross-tenant
        admission, and every field written are all unchanged.

        One ordering detail did shift, and only for a caller that is wrong twice at once. The
        tenant check now happens in :func:`~domain.relation_claim_material.build` and the
        disposition check in :func:`~domain.relation_claim_material.admit`, so a reading that is
        both non-``SUPPORTED`` *and* cross-tenant reports the tenant mismatch where it previously
        reported the disposition. Both refuse; only the label moved, and the tenant is the safer
        of the two to name first (constitution IV).

        The keyword arguments are unchanged, and each is required exactly where the candidate
        genuinely cannot know the answer. The parameter-by-parameter reasoning now lives on
        :func:`domain.relation_claim_material.build`, which is where the transcription happens;
        it is repeated here because this signature is still the one being called:

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

        * ``source_independence_groups`` - defaulted empty, and that default is a truthful
          "nothing independent backs this yet" rather than a gap. Independence is computed
          across a claim set (FR-034) and cannot be derived from one candidate alone, so it
          has to be supplied by whoever did the resolution. It was previously absent from
          this signature altogether, which meant every claim admitted this way carried
          ``independent_source_count == 0`` and the ``cross_source`` validation stage could
          only ever answer ``UNKNOWN`` -- the corroboration the resolver computes was
          computed and then discarded. Empty is the honest absence; a real group list is
          identity material, so two claims differing in what independently backs them are
          two claims.

        Everything else is transcribed from the candidate: the operator identity, the arity
        mode, the context and regime references, the observation refs, the extraction method
        and version, the rule id, the investigation and the author.

        **The ``SUPPORTED`` guard lives here, not in**
        :func:`~domain.relation_claim_material.admit`.
        Feature 019's CD-1 removed the disposition as a lifecycle gate, because a caller who
        wants into the claim layer can simply write ``SUPPORTED`` on a reading and the check
        would pass - it tested the caller's belief, not the evidence. ``admit`` now gates on
        the validation report, which is derived from evidence and can refuse a reading whose
        label says ``SUPPORTED``.

        This method keeps the guard anyway, and the reason is not that the gate was right. It
        is that this method's contract promised a non-``SUPPORTED`` reading would raise
        :class:`CandidateNotAdmissible`, and callers catch that exception and branch on it.
        A caller mid-migration would otherwise find its ``except CandidateNotAdmissible``
        silently dead - a real risk with no benefit, since the production path in
        ``semantic_path/execution.py`` calls ``build``/``validate``/``admit`` directly and
        never passes through here at all.

        So the guard moved, it did not weaken, and new code should not rely on it: relabelling
        a reading to get past a refusal is the behaviour this feature is removing.
        """
        from domain.relation_claim_material import admit, build, unvalidated_report

        if self.candidate_status not in ADMISSIBLE_CANDIDATE_STATUSES:
            raise CandidateNotAdmissible(
                self.candidate_id, self.candidate_status, ADMISSIBLE_CANDIDATE_STATUSES
            )

        material = build(
            self,
            subject_ref=subject_ref,
            object_ref=object_ref,
            revision_number=revision_number,
            evidence_grade=evidence_grade,
            tenant_id=tenant_id,
            role_bindings=role_bindings,
            assertion_refs=assertion_refs,
            source_independence_groups=source_independence_groups,
            normalization_version=normalization_version,
            ontology_version=ontology_version,
            observed_at=observed_at,
        )
        return admit(material, unvalidated_report(material), claim_status=claim_status)

    def _verify_participants_name_the_same_mentions(self) -> None:
        """Refuse a participant set that is not about the mentions this reading names.

        :attr:`participants` and (:attr:`subject_mention_ref`, :attr:`object_mention_ref` /
        :attr:`role_assignments`) are two views of one thing, and two views that can disagree
        are two sources of truth — the condition that produces
        ``candidate.relation_ref = A`` against ``predicate_hypothesis.relation_ref = B`` and the
        rest of that family. So the agreement is checked here rather than documented.

        The check is as strong as the mention record allows. ``stable_participant_fingerprint``
        deliberately digests no id (``data-model.md`` part 4.3), so a mention may carry no
        reference at all; in that case only the cardinality is checked, and the residual is stated
        rather than hidden. When the mentions *do* expose a reference — ``mention_ref`` or
        ``mention_id`` — the multisets must be equal, and for a ``DIRECTED`` reading the
        slot order must agree with the endpoint order as well, because for a directed binary
        relation the slots *are* the direction and a disagreement is a silent fork rather than a
        relabelling.
        """
        if not self.participants:
            return
        expected = self._participants
        if len(self.participants) != len(expected):
            raise CandidateContractError(
                "participant_count_disagrees_with_mentions",
                f"this reading names {len(expected)} mention(s) {list(expected)} but binds "
                f"{len(self.participants)} participant(s). The participant set is where each "
                "participant sat in the construction; the mention refs are which mentions were "
                "read. They are one fact stated twice and may not disagree",
            )
        refs = tuple(_mention_reference(participant.mention) for participant in self.participants)
        if not all(refs):
            return
        if sorted(refs) != sorted(expected):
            raise CandidateContractError(
                "participants_disagree_with_mention_refs",
                f"the participant set names mentions {sorted(refs)} but this reading's "
                f"endpoints are {sorted(expected)}; they are one fact stated twice",
            )
        if self.arity_mode is RelationArityMode.DIRECTED:
            by_slot = sorted(
                self.participants, key=lambda p: p.role.canonical_argument_slot.index
            )
            oriented = tuple(_mention_reference(item.mention) for item in by_slot)
            if oriented != tuple(expected):
                raise CandidateContractError(
                    "participant_slots_disagree_with_endpoint_order",
                    f"slot order names mentions {list(oriented)} but subject/object are "
                    f"{list(expected)}. For a directed relation the canonical argument slots ARE "
                    "the direction, so a disagreement here is a silent identity fork rather than "
                    "a relabelling",
                )

    def _logical_material(self) -> dict[str, Any] | None:
        """The material of *which relational configuration this is*, or ``None``.

        Delegates to :func:`domain.predicate_signature.logical_candidate_material` — the one
        function the identity subsystem admits — so there is exactly one ordering of
        participants, one arity derivation and one material shape, and a candidate cannot drift
        from the rule that defines it (``data-model.md`` part 4.2, part 5.1).

        **``None`` is the answer for an un-signatured candidate, not a failure to be worked
        around.** The signature is the sole predicate term; with none, ``logical_candidate_id``
        is ``""``, the candidate is addressable by ``candidate_id`` alone, and
        :func:`verify_candidate_identity` refuses to certify it with
        ``unaddressed_logical_identity``. The alternative — a surface-keyed fallback term — is
        FR-001's violation alive under a version tag, and it is what this method used to be:
        ``relation_surface`` was passed straight into ``logical_material``'s ``relation_type``
        parameter, so the words the observation used *were* the predicate term. A fallback would
        also mean two code paths deriving ids, of which the second would be the wrong one.

        ``arity_mode`` is passed as the **checked redundancy** part 2.5 check 4 asks for: the
        material derives it from the occupied slots and ``commutative_slots`` and refuses a
        declared value that disagrees, so a candidate whose declared shape contradicts its own
        bindings cannot mint an id.
        """
        if self.predicate_signature is None:
            return None
        try:
            return logical_candidate_material(
                self.predicate_signature,
                self.participants,
                tenant_id=self.tenant_id,
                polarity=self.polarity,
                commutative_slots=self.commutative_slots,
                arity_mode=self.arity_mode,
            )
        except SignatureContractError as exc:
            raise CandidateContractError(exc.code, exc.message) from exc

    def _revision_material(self, logical_candidate_id: str) -> dict[str, Any]:
        """The material of *this reading*, keyed by the logical id.

        The temporal window enters here as a nested hypothesis, all four of its fields, so a
        change of guessed span, of how the guess was reached, or of the declared semantics all
        mint a new ``candidate_id`` while leaving the logical key alone. The logical id is a
        parameter rather than read off the record so that derivation cannot recurse through
        :meth:`with_id` on an unaddressed candidate.

        The predicate enters the same way, and for a sharper reason: the *mapping* belongs to the
        revision rather than the logical key because a later ``SemanticRegime`` may resolve the
        same signature to a different operator. That is a new reading of one configuration, not a
        new configuration — and if the operator sat in the logical material, recognising it would
        silently mint a second candidate for one relation, which is precisely the inversion this
        module just removed. So the surface, the resolved operator type, the resolution state and
        every alternative enter here, and an unresolved predicate that later becomes a resolved
        one is visibly one candidate with two readings (``data-model.md`` part 5.3 step 5).

        The mention refs and the free-text role words enter here too, and that is a collision
        argument rather than a demotion: two readings that named different mentions, or that
        called one slot ``purchaser`` and the other ``buyer``, are different readings and must
        not share a ``candidate_id``. What they may not do is move a *logical* id — the
        participant's fingerprint already covers which mention it was.

        ``tenant_id`` enters **both** halves, and the reason is not redundancy. It is logical
        material because FR-002 and brief section 19 require it and because omitting it would
        let two tenants' configurations bucket under one key, which constitution IV forbids. But
        the revision address is derived from the logical id, so for a candidate with **no**
        signature the logical id is ``""`` and the tenant would reach no digest at all — two
        tenants' un-signatured readings would share one ``candidate_id``. That is not a rounding
        error in the constitution, it is the constitution. ``tenant_id`` is therefore emitted
        directly as well, so the revision address is tenant-scoped whether or not the reading
        carries a signature. For a signed candidate the value appears twice in the digest, which
        costs nothing: a digest over the same value twice is still a function of that value.
        """
        return {
            "logical_candidate_id": logical_candidate_id,
            "tenant_id": self.tenant_id,
            "schema_version": self.schema_version,
            "relation_type": self.relation_type,
            "relation_surface": self.relation_surface,
            "subject_mention_ref": self.subject_mention_ref,
            "object_mention_ref": self.object_mention_ref,
            "arity_mode": str(self.arity_mode),
            "role_assignments": [binding.to_dict() for binding in self.role_assignments],
            "predicate_hypothesis": self.predicate_hypothesis.content_key(),
            "temporal_hypothesis": self.temporal_hypothesis.to_dict(),
            "observed_at": _iso(self.observed_at),
            "context_ref": self.context_ref,
            "semantic_regime_ref": self.semantic_regime_ref,
            "observation_refs": list(self.observation_refs),
            "evidence_refs": list(self.evidence_refs),
            "signal_refs": list(self.signal_refs),
            "extraction_method": str(self.extraction_method),
            "extractor_version": self.extractor_version,
            "extraction_rule_id": self.extraction_rule_id,
            "trigger_span": None if self.trigger_span is None else self.trigger_span.to_dict(),
            "supporting_spans": [span.to_dict() for span in self.supporting_spans],
            "investigation_id": self.investigation_id,
            "recorded_by": self.recorded_by,
            "candidate_status": str(self.candidate_status),
            "assembly_state": str(self.assembly_state),
        }

    def _material(self) -> dict[str, Any]:
        """The serialised field set the content hash is taken over (FR-005).

        Complete by construction, and it has to be: :func:`verify_candidate_material_partition`
        fails when a field is classified as material that the material never emits, and that
        check was **not passing** before this wave — ``relation_surface``, ``signal_refs`` and
        ``predicate_hypothesis`` were all declared and none was emitted, so the function raised
        ``candidate_field_never_addressed`` and nothing in the repository called it to find out.
        A verifier nobody runs is a comment; a verifier that runs is the mechanism.

        A participant is serialised as its placement plus the identity material its fingerprint
        digests, and deliberately not as the whole mention record: the candidate holds a
        *reference* to a mention, not a copy of it, so the six fields the fingerprint reads are
        the whole of what this record holds about one (``data-model.md`` part 4.3). Any other
        field on the mention record is a fact about the mention, not about this reading.
        """
        return {
            "tenant_id": self.tenant_id,
            "subject_mention_ref": self.subject_mention_ref,
            "object_mention_ref": self.object_mention_ref,
            "relation_type": self.relation_type,
            "schema_version": self.schema_version,
            "arity_mode": str(self.arity_mode),
            "predicate_signature": (
                None if self.predicate_signature is None else self.predicate_signature.to_dict()
            ),
            "participants": [
                {**participant.role.to_dict(), "participant_fingerprint": fingerprint}
                for participant, fingerprint in (
                    (participant, stable_participant_fingerprint(participant.mention))
                    for participant in self.participants
                )
            ],
            "commutative_slots": sorted(slot.token for slot in self.commutative_slots),
            "polarity": str(self.polarity),
            "role_assignments": [binding.to_dict() for binding in self.role_assignments],
            "relation_surface": self.relation_surface,
            "predicate_hypothesis": self.predicate_hypothesis.content_key(),
            "context_ref": self.context_ref,
            "semantic_regime_ref": self.semantic_regime_ref,
            "trigger_span": None if self.trigger_span is None else self.trigger_span.to_dict(),
            "supporting_spans": [span.to_dict() for span in self.supporting_spans],
            "extraction_method": str(self.extraction_method),
            "extractor_version": self.extractor_version,
            "extraction_rule_id": self.extraction_rule_id,
            "observation_refs": list(self.observation_refs),
            "evidence_refs": list(self.evidence_refs),
            "signal_refs": list(self.signal_refs),
            "temporal_hypothesis": self.temporal_hypothesis.to_dict(),
            "candidate_status": str(self.candidate_status),
            "assembly_state": str(self.assembly_state),
            "confidence": self.confidence,
            "investigation_id": self.investigation_id,
            "observed_at": _iso(self.observed_at),
            "recorded_by": self.recorded_by,
        }


def _mention_reference(mention: object) -> str:
    """The mention's own reference if it publishes one, else ``""``.

    ``stable_participant_fingerprint`` deliberately digests no id, so a mention is not required
    to carry one and :class:`domain.predicate_signature.ResolvedMention` does not declare one.
    Reading it here is therefore best-effort by design, and the caller is written to say so: a
    mention that publishes nothing is checked for cardinality only, and the residual is documented
    on :meth:`RelationCandidate._verify_participants_name_the_same_mentions` rather than hidden.
    """
    for attribute in ("mention_ref", "mention_id"):
        value = getattr(mention, attribute, "")
        if value:
            return str(value)
    return ""


def recompute_candidate_identity(candidate: RelationCandidate) -> tuple[str, str]:
    """Re-derive ``(logical_candidate_id, candidate_id)`` from a candidate's own fields.

    The identity layer's counterpart to
    :func:`domain.relation_identity.recompute_identity`, and the only id-producing path this
    module exposes. Pure, so a tampering store, a replay and a test all reach the same answer
    and can therefore disagree loudly (FR-011, FR-022).

    The logical half is ``""`` for a candidate with no signature, and the revision half is still
    derived — keyed on that empty string, deterministically. So an un-signatured reading is
    addressable and reproducible; it simply has no logical identity to be addressed *by*, which
    is what ``verify_candidate_identity`` then refuses to certify.
    """
    material = candidate._logical_material()
    logical = (
        ""
        if material is None
        else LOGICAL_CANDIDATE_ID_PREFIX + digest128(canonical_material(material))
    )
    revision_material = candidate._revision_material(logical)
    for key in ("observation_refs", "evidence_refs", "signal_refs"):
        revision_material[key] = sorted(revision_material[key])
    revision = REVISION_CANDIDATE_ID_PREFIX + digest128(canonical_material(revision_material))
    return logical, revision


def verify_candidate_identity(candidate: RelationCandidate) -> None:
    """Fail unless the carried ids are the ones the candidate's own content addresses.

    The tamper check a store runs on load, mirroring how the identity layer of
    :mod:`domain.relation_identity` re-derives and compares rather than trusting a stored id.
    Refuses only the *addressed* case; an unaddressed candidate is simply not yet addressed
    and is not an error, because :meth:`RelationCandidate.with_id` is how a candidate becomes
    addressable.

    **An addressed candidate with no signature is refused**, with ``unaddressed_logical_identity``
    (``data-model.md`` part 5.4). The old behaviour here was to skip: ``with_id()`` had always
    produced a ``logical_candidate_id``, so the asymmetry between an unaddressed candidate (fine)
    and one whose logical half is missing (also fine) was never named. Naming it is the point —
    a store that certifies such a row is certifying an identity nobody can re-derive, and the
    alternative refusal a caller would reach for instead (falling back to the surface) is FR-001's
    violation with a version tag on it.
    """
    if not candidate.candidate_id and not candidate.logical_candidate_id:
        return
    logical, revision = recompute_candidate_identity(candidate)
    if not logical:
        raise CandidateContractError(
            "unaddressed_logical_identity",
            f"candidate {candidate.candidate_id or '<unaddressed>'} is addressed but carries "
            "no predicate_signature, so it has no logical_candidate_id to verify. "
            "logical_candidate_id requires a PredicateSignature; a candidate whose construction "
            "was never read is addressable by candidate_id alone, and a surface-keyed fallback "
            "identity is FORBIDDEN (FR-001, data-model.md part 5.4). Re-extract to supply a "
            "signature, or treat this row as un-signatured and replayable - never auto-deleted",
        )
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
        """The readings carrying the ``SUPPORTED`` label - a **compatibility
        projection**, not a lifecycle gate (feature 019, CD-1).

        It filters on :attr:`RelationCandidate.is_admissible`, which asks what label a
        reading bears. It does not ask whether any reading here can become a claim,
        because that is a question about evidence and this is a question about a string.

        Two consequences worth stating plainly. A ``PROPOSE`` reading is absent from this
        tuple and is not thereby refused - it reaches the claim layer through
        :func:`domain.relation_claim_material.build`, ``validate`` and ``admit``. And a
        reading in this tuple has earned nothing: it is a candidate that someone labelled.

        A caller that wants the real answer should call ``admit`` and handle the refusal.
        """
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
    "CANDIDATE_LOGICAL_MATERIAL_CONSTANT_KEYS",
    "CANDIDATE_LOGICAL_MATERIAL_FIELDS",
    "CANDIDATE_LOGICAL_MATERIAL_KEYS",
    "CANDIDATE_MUTABLE_PROJECTION_FIELDS",
    "CANDIDATE_REVISION_MATERIAL_FIELDS",
    "CLAIM_ONLY_FIELDS",
    "CONFLICTING_ASSEMBLY_STATES",
    "CONTRADICTING_CANDIDATE_STATUSES",
    "DECOMPOSED_CANDIDATE_FIELDS",
    "LOGICAL_CANDIDATE_ID_PREFIX",
    "REVISION_CANDIDATE_ID_PREFIX",
    "CandidateAssemblyState",
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
