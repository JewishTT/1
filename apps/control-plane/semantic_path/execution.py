"""The golden path: one executable, deterministic path through every existing layer.

Specs 016 + 017. Every abstraction those two features built already exists -
extractor registry, ``EvidenceContext``, ``TypeAssertion``, ``SemanticRegime``,
``RelationCandidate``, ``RelationOperator``, ``LayeredValidator``,
``MaterialisationDecision``, ``RelationClaim``, ``RelationStore``, ``GraphEdge``
projection, ``EvidenceGraph`` lineage, ``EntityWorldline`` - and almost none of them
were wired to each other. This module is the wire. It creates no shadow copy of any
of them: every step calls the real component and returns the real object, and no
step re-derives what a component already derives.

**What it is not.** Not a pipeline, a framework, a base class or a registry. One
explicit sequence of function calls over one sentence, in one file, that a reader
can follow top to bottom and see which component did what.

**Staged and inspectable.** :data:`STAGE_ORDER` names thirteen steps and
:func:`run_until` executes a prefix, returning an :class:`ExecutionResult` that
carries the *real* intermediate objects reached so far: the
:class:`extractors.registry.Mention` values, the ``SemanticRegime``, the
:class:`ResolutionBatch` and its ``ResolutionDecision`` values, the ``TypeAssertion``
values, the ``RelationCandidate``, the ``ValidationReport``, the ``RelationClaim``,
the ``GraphEdge``, the ``WorldlineEvent``. Nothing is flattened into a summary of
strings, because a summary is not inspectable. A stage that was not reached is
``None``, so "not run yet" and "ran and produced nothing" stay distinguishable.

**Resolution is real here, and the previous shape of this module was wrong.**
There used to be a ``BLOCKING`` stage whose ``subject_ref``/``object_ref`` were the
canonically-first survivors, and an ``entity_ref_for(tenant, mention)`` that minted
``ENT-`` from the *mention*. That made the mention the entity: one mention became
one entity by construction and a second mention could never join it. It is gone.
Stage 5 is now :class:`ResolutionStep`, which runs
:class:`semantic.resolution.MentionResolver` - normalization through the vocabulary
facade's alias expansion, blocking delegated to :mod:`semantic.blocking`, the four
compatibility layers with recorded reasons, the collective pass, and a two-level
decision. The only thing the orchestrator contributes is **honesty about the
verdict**: it refuses to build a claim about a participant it could not identify, and
says which mention and why, rather than substituting a synthetic entity ref.

**Determinism is structural.** No clock, no randomness, no network, no database,
no model. Every timestamp enters through :class:`ExecutionRequest` from the caller
and every identifier is a content address computed by the component that owns it.
The same request therefore yields byte-identical identifiers in a fresh process.

**Open world is visible, not merely permitted.** No step consults an allowlist. A
type reference no profile declares still produces a first-class ``TypeAssertion``
that flows through blocking, validation, admission, the store, the projection and
the worldline untouched, and the semantic stage reports ``not_declared_in_profile``
with verdict ``UNKNOWN`` - an unevaluable check, not a failure. A domain/range
contradiction produces a ``ValidationFinding`` *and* a materialised claim *and* a
projected edge, because ``decide_materialisation`` answers for one operator's view
and defaults to ``warn``. The path never refuses content.

**One reordering, and why it is forced.** The architect's stage list puts
``LayeredValidator`` and the admission decision *before*
``RelationCandidate.to_claim``. That order is not drivable as specified:
``LayeredValidator.evaluate`` takes a ``RelationClaim``, and
``RelationCandidate.to_claim`` *is* the admission act - it raises
``CandidateNotAdmissible`` unless the reading is ``SUPPORTED``. There is therefore
no moment at which a candidate can be validated but not yet admitted, and no way to
validate one without first building a claim. The order here is therefore
``RESOLUTION -> CLAIM -> VALIDATION -> ADMISSION -> STORE -> EDGE -> WORLDLINE``,
and the resulting finding is a design question for the next round: validation
should be able to run against a *candidate* shape, or ``to_claim`` should be split
into "build" and "admit" so a claim can exist, be validated, and still be refused.

**A second reordering, and why it is also forced.** ``TypeAssertion`` carries an
``entity_ref``, and the real resolver produces that ref - so the types cannot be
asserted before the entity exists. The regime moved ahead of them for a second
reason: the resolver's context layer compares the mention's ``regime_id`` against
the candidate's, and an unbuilt regime would make every such comparison
``UNEVALUATED``. Hence ``MENTIONS -> REGIME -> RESOLUTION -> TYPES``.

**The regime is now executed, not merely reported absent (018, D6 / FR-014...FR-016).**
The stage order above was forced by a defect: ``regime_id`` was written in memory
and persisted nowhere, so the compatibility layer's regime comparison returned
``UNEVALUATED`` on the golden path on every run - which the spec correctly called
"structurally present but not actually executed". The fix was to supply the input,
not to mute the report, and this module now does three things it did not:

* step 4 **writes** the regime it built through a
  :class:`semantic.regime_store.RegimeStore` and then **reads it back** before
  anything downstream sees it, so the value the path carries is the one that
  survived storage and not the one a local variable happened to hold;
* step 5 **reads it back again**, independently, and binds that stored address to
  both the mentions and the candidate universe, so the comparison the resolver
  performs has a real regime on both sides and answers
  ``regime_compatible`` rather than ``regime_unevaluated``;
* a regime that genuinely cannot be resolved is a **stated** ``UNRESOLVED`` with a
  reason and a count on the store, raised as ``regime_unresolved`` before any
  comparison runs. There is no ``regime_id=""`` fallback anywhere on this path, and
  no default regime is ever substituted: FR-016 is enforced by the absence of the
  code path rather than by a check.

**Where it lives, and why.** ``apps/shared/semantic/`` - not ``domain/``, which
FR-005 keeps free of semantic vocabulary and which holds base values rather than a
process, and not a new app. ``semantic/`` is already the 016/017 seam: it is where
``validation.py`` reaches from the operator contract to the claim and the frame.

**The two dependencies that invert layering, stated plainly.** This module imports
``extractors.registry`` and ``graph.relation_store``, so ``apps/shared`` gains
runtime import edges to ``apps/interpretation`` and ``apps/projection``, both of
which already depend on ``apps/shared``. That cycle is the price of wiring the slice
at all; the correct home is a composition-root app depending on all three, and this
module is written so that moving it there is a move plus one import rewrite. It is
stated here rather than hidden, because a reader who meets the edge in a traceback
deserves to find it already explained.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from domain.capture import Capture, CaptureTimeBasis
from domain.dynamics import StreamRecord
from domain.evidence_context import (
    ContextCompleteness,
    ContextTrustState,
    EvidenceContext,
    InMemoryContextResolver,
)
from domain.evidence_lineage import EvidenceGraph, EvidenceHop, HopKind, LineageTrace
from domain.mention_occurrence_index import (
    MentionOccurrence,
    MentionOccurrenceIndex,
    MentionOccurrenceKey,
    mint_mention_id,
    unbound_mention_id,
)
from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_candidate import (
    RelationCandidate,
    SpanRef,
    TemporalHypothesis,
)
from domain.relation_claim import (
    EvidenceGrade,
    RelationClaim,
    RelationRoleBinding,
    RelationStatus,
)
from domain.relation_claim_material import admit as admit_material
from domain.relation_claim_material import build as build_material
from domain.relation_claim_material import validate as validate_material
from domain.relation_identity import RelationArityMode, canonical_material, digest128
from domain.relation_participant import RelationParticipant
from domain.relation_schema import RelationSchema, TemporalSemantics
from domain.signal_basis import SignalBasis
from domain.temporal_observation import TemporalAxis
from domain.temporal_worldline import EntityWorldline, WorldlineEvent, build_worldline
from extractors.registry import DeterministicExtractorSet, Mention, SemanticHint
from extractors.relations import (
    RELATION_RULE_ID,
    RelationalReading,
    extract_relational_readings,
    register_relational_extractors,
)
from extractors.signals.mentions import bind_producer_signals
from extractors.signals.protocol import ExtractionScope, RelationSignalExtractor, run_producer
from extractors.signals.signal import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalKind,
)
from graph.abstraction import GraphEdge, GraphNode, HyperEdge, InMemoryGraphStore
from graph.relation_store import GraphProjectionBridge, InMemoryRelationStore
from semantic.blocking import (
    Candidate as BlockingCandidate,
)
from semantic.blocking import RelationRole
from semantic.contracts import (
    RelationRef,
    SemanticRef,
    SemanticStatus,
    TypeAssertion,
    TypeScope,
    ValidationReport,
)
from semantic.operators import RelationOperator, default_operator_for_schema
from semantic.profiles import ProfileRegistry, ProfileResolution, SemanticProfile
from semantic.regime import (
    DEFAULT_VALIDATION_PROFILE,
    SemanticCommitment,
    SemanticRegime,
    extend_context,
)
from semantic.regime_store import InMemoryRegimeStore, RegimeRecord, RegimeStore
from semantic.registry import ConceptSchemeBackend, SemanticRegistry
from semantic.resolution import (
    MentionResolver,
    ResolutionBatch,
    ResolutionCandidate,
    ResolutionDecision,
    ResolutionMention,
    ResolutionScope,
    ResolutionVerdict,
    resolution_scope_for,
)
from semantic.validation import (
    STAGE_ORDER as VALIDATION_STAGE_ORDER,
)
from semantic.validation import (
    LayeredValidator,
    MaterialisationDecision,
    StageOutcome,
)
from semantic.vocabularies import Concept, ConceptScheme

from semantic_path.assembly import AssemblyReport, assemble

__all__ = [
    "GOLDEN_SENTENCE",
    "REGIME_COMPATIBLE",
    "REGIME_MISMATCH",
    "REGIME_REASON_CODES",
    "REGIME_UNEVALUATED",
    "RELATION_RULE_ID",
    "STAGE_ORDER",
    "UNSET",
    "AdmissionStep",
    "CandidateStep",
    "ClaimStep",
    "ContextStep",
    "EdgeStep",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionStage",
    "LineageBundle",
    "MentionRecord",
    "MentionStep",
    "Observation",
    "ObservationStep",
    "RegimeResolution",
    "RegimeStep",
    "RegimeVerdict",
    "RelationalReading",
    "ResolutionStep",
    "SemanticExecutionError",
    "StoreStep",
    "TypeStep",
    "ValidationStep",
    "WorldlineStep",
    "backward_lineage",
    "base_profile",
    "capture_id_for",
    "chain_to_observation",
    "decoy_universe",
    "derived_from_observation",
    "deterministic_extractors",
    "forward_lineage",
    "golden_candidates",
    "golden_request",
    "golden_vocabulary",
    "mention_id_for",
    "regime_verdicts_for",
    "register_relational_extractors",
    "resolution_candidate_for",
    "run_golden_path",
    "run_until",
    "works_for_schema",
]

#: The one sentence the architect named, so nothing drifts onto a different fixture.
GOLDEN_SENTENCE = "John Smith became CEO of Acme in 2020."

_OBSERVATION_ID_PREFIX = "OBS-"
_EVENT_ID_PREFIX = "EVT-"
_CAPTURE_ID_PREFIX = "CAP-"
_ENTITY_ID_PREFIX = "ENT-"

EXTRACTION_SET_VERSION_PREFIX = "det-set-"

#: The extractor ref of the mention step's index scope. One name for "the deterministic
#: extractor set", and a constant rather than a per-record value so the set is one scope instead
#: of one scope per mention (see :func:`_occurrence_index`).
EXTRACTOR_SET_SCOPE_REF = "deterministic-extractor-set"

#: The three codes the resolver's context layer can record for a regime comparison, and
#: the only three this module treats as a regime verdict (FR-015).
#:
#: Re-declared rather than imported, for the reason the verdict strings in
#: :mod:`domain.entity_identity` are: the *codes* are what a durable record and a smoke
#: run key on, and they must be nameable without importing the machine. Nothing here
#: decides what a code means - the meaning is
#: :func:`semantic.resolution.analyse_candidate`'s, and it is unchanged by this module.
REGIME_COMPATIBLE = "regime_compatible"
REGIME_MISMATCH = "regime_mismatch"
REGIME_UNEVALUATED = "regime_unevaluated"

REGIME_REASON_CODES: frozenset[str] = frozenset(
    {REGIME_COMPATIBLE, REGIME_MISMATCH, REGIME_UNEVALUATED}
)


class SemanticExecutionError(RuntimeError):
    """A step could not be completed as the request configured it.

    Never a contract breach: a component's own refusal travels unchanged. This is
    for the cases where the *request* is not drivable - no mention of the requested
    kind, a blocking call that resolved nothing, an id named by a chain that is not
    on the lineage - and it carries the stable snake_case code the smoke run can
    switch on.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class ExecutionStage(StrEnum):
    """The fourteen steps, in the order they execute.

    The order is the point of the enum: it is what a reader follows, what a caller
    stops at, and what a diff is read against. :data:`STAGE_ORDER` is derived from
    the declaration order so the two cannot drift apart.

    ``SIGNALS`` is feature 019's and it sits **after** ``REGIME``, which is the position the
    dependencies actually force. A producer needs a frame and a regime before its signals
    are worth anything - FR-014 and FR-016 both say a reading must say what it was read in
    and interpreted under, and a signal that named a placeholder regime would satisfy the
    type and not the requirement. It sits *before* ``RESOLUTION`` because it names mentions:
    a producer sees surfaces, and reconciliation of those to entities is resolution's job
    with a ``ResolutionDecisionRecord`` behind it.

    It was originally placed between ``MENTIONS`` and ``REGIME``, on the reasoning that a
    producer cannot run before there are mentions. That is true and it is not sufficient:
    the earlier position forced a placeholder regime ref, and a placeholder that satisfies
    the type is worse than no value at all, because it is indistinguishable from a real one
    in every downstream read.
    """

    OBSERVATION = "observation"
    CONTEXT = "context"
    MENTIONS = "mentions"
    REGIME = "regime"
    SIGNALS = "signals"
    RESOLUTION = "resolution"
    TYPES = "types"
    CANDIDATE = "candidate"
    CLAIM = "claim"
    VALIDATION = "validation"
    ADMISSION = "admission"
    STORE = "store"
    EDGE = "edge"
    WORLDLINE = "worldline"

    def rank(self) -> int:
        return _STAGE_RANK[self]


_STAGE_RANK: dict[ExecutionStage, int] = {
    stage: index for index, stage in enumerate(ExecutionStage)
}

#: The fixed stage order. "Up to a stage" is an index into this.
STAGE_ORDER: tuple[ExecutionStage, ...] = tuple(ExecutionStage)

_SCHEME_BY_PREFIX: Mapping[str, SemanticRef] = MappingProxyType(
    {
        "core": SemanticRef.INTERNAL,
        "internal": SemanticRef.INTERNAL,
        "local": SemanticRef.LOCAL,
        "profile": SemanticRef.PROFILE,
        "skos": SemanticRef.SKOS,
    }
)


def _scheme_for(type_ref: str) -> SemanticRef:
    """How a type reference is being *referenced*, from its scheme prefix.

    Classification only. Deciding that ``local:Influencer`` and ``schema:Person``
    are close enough to satisfy a domain hint is a mapping assertion, and mappings
    are recorded in :mod:`semantic.mappings` with provenance - never inferred here
    from a spelling.
    """
    prefix, separator, _ = str(type_ref).partition(":")
    if not separator:
        return SemanticRef.INTERNAL
    return _SCHEME_BY_PREFIX.get(prefix.strip().lower(), SemanticRef.EXTERNAL)


def _default_type_refs() -> Mapping[str, str]:
    """Mention kind to type reference, for the clean golden path."""
    return MappingProxyType({"person": "schema:Person", "org": "schema:Organization"})


def mention_id_for(
    capture_ref: str,
    segment_ref: str,
    kind: str,
    value: str,
    start: int,
    end: int,
    extractor: str,
) -> str:
    """``MN-`` + 128-bit digest: which mention this is, from its own surface.

    **A thin adapter over :func:`domain.mention_occurrence_index.mint_mention_id`, and it exists
    only so this composition root reads naturally at its call sites.** The minter itself moved to
    :mod:`domain.mention_occurrence_index` for two reasons, and both are about the dependency
    graph rather than about tidiness: the index is the one thing that mints ``MN-…``, and a minter
    that lived here could not be reached by a producer without taking the edge
    producer → composition root — this module imports :mod:`extractors.registry` and
    :mod:`graph.relation_store`, so importing it below the mention layer would invert the layering
    and pull the graph package into extraction. :mod:`domain` sits strictly below both.

    ``capture_ref`` is **required and first**, and it was not before: the old tuple was
    ``(segment, kind, value, start, end, extractor)`` with no capture, so two captures of one
    segment addressed to **one** mention id and the platform could no longer say which retrieval
    saw it. That is a collision, not a simplification, and it is why the index's mint tuple has
    five keys of which the capture is one (``ARBITRATION`` §8, FR-018).

    ``kind`` is accepted and is **not** part of the mint: a producer's classification of an
    occurrence is evidence about a mention rather than part of its identity, and the index refuses
    a second kind at the same address rather than forking the id.
    """
    del kind
    return mint_mention_id(
        MentionOccurrenceKey.of(
            capture_ref=capture_ref,
            segment_ref=segment_ref,
            start=start,
            end=end,
            surface=value,
            extractor_ref=extractor,
        )
    )


def capture_id_for(source_id: str, observation_id: str) -> str:
    """``CAP-`` + 128-bit digest: a *placeholder* address for a capture that was never fetched.

    Kept only so a caller with no acquisition record still gets a chain, and every use
    of it is a chain with a hole in it. Nothing in this module calls it any more: the
    observation carries a real :class:`domain.capture.Capture` or admits it has none, and
    the lineage reports a missing capture hop instead of a fabricated address.

    A derived id is not a weaker fact about a fetch that happened - it is a statement
    about no fetch at all, wearing a fetch's shape.
    """
    return _CAPTURE_ID_PREFIX + digest128(
        canonical_material({"source": source_id, "observation": observation_id})
    )


@dataclass(frozen=True)
class Observation:
    """The raw record the whole path starts from, addressed by its own content.

    No shared ``Observation`` value type exists: acquisition emits observation dicts
    onto the bus and every downstream layer carries a bare ``observation_id``
    string. A vertical slice needs a real first stage with a real object, so this is
    that object - new, not a reimplementation of anything.

    ``observation_id`` is a content address derived on construction and **verified**
    when supplied, exactly as :class:`domain.evidence_context.EvidenceContext`
    verifies its own: a record carrying an id its content does not address to cannot
    be constructed, so no caller can forge one and a tampered row cannot load
    (FR-014, I-11).

    ``text`` is the segment the extractors read and it is deliberately not in the
    address material - an observation is a fact about a document, and the raw bytes
    live in object storage and are referenced, never inlined in an event (I-5). Its
    *digest* is in the material, so a segment whose content actually changed is a
    different observation while a re-fetch of identical bytes is the same one.
    """

    observation_id: str = ""
    event_id: str = ""
    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    source_id: str = ""
    source_family: str = ""
    independence_group: str = ""
    document_id: str = ""
    segment_id: str = ""
    text: str = ""
    language: str = "en"
    observed_at: datetime | None = None
    published_at: datetime | None = None
    extraction_version: str = ""
    normalization_version: str = ""
    ontology_version: str = ""
    capture: Capture | None = None
    """The acquisition fact that fetched the bytes this observation was read from.

    ``None`` means the caller did not supply one, and the lineage then says the capture
    hop is absent rather than inventing an address. That distinction is the whole point
    of feature 018: the previous arrangement derived a ``CAP-`` id from
    ``(source_id, observation_id)``, which produced a *looking* capture that existed in
    no store and joined to no fetch, so ``Source -> Capture -> Observation`` was a chain
    of shapes rather than of facts. A real capture has a real fetch basis, a real
    content digest and a real time, and its absence is now reportable.
    """

    def __post_init__(self) -> None:
        if not self.segment_id:
            raise SemanticExecutionError(
                "missing_segment_id",
                "an observation indexes into a segment; offsets with no segment are "
                "unresolvable, exactly as a SpanRef requires",
            )
        addressed = _OBSERVATION_ID_PREFIX + self.content_key()
        if not self.observation_id:
            object.__setattr__(self, "observation_id", addressed)
        elif self.observation_id != addressed:
            raise SemanticExecutionError(
                "observation_id_mismatch",
                f"observation carries {self.observation_id!r} but its own content addresses "
                f"to {addressed!r}; a content address is verified, never trusted",
            )
        if not self.event_id:
            object.__setattr__(
                self, "event_id", _EVENT_ID_PREFIX + digest128(f"event:{addressed}")
            )

    def content_key(self) -> str:
        """The 128-bit digest ``observation_id`` addresses, over the frame only."""
        return digest128(canonical_material(self.frame()))

    def frame(self) -> dict[str, Any]:
        """The serialised frame the id addresses - this record's audit surface."""
        return {
            "tenant_id": self.tenant_id,
            "investigation_id": self.investigation_id,
            "source_id": self.source_id,
            "source_family": self.source_family,
            "independence_group": self.independence_group,
            "document_id": self.document_id,
            "segment_id": self.segment_id,
            "text_digest": digest128(self.text),
            "language": self.language,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "extraction_version": self.extraction_version,
            "normalization_version": self.normalization_version,
            "ontology_version": self.ontology_version,
        }

    def provenance(self) -> dict[str, Any]:
        """The projection provenance every store write on this path must carry (I-12)."""
        return {"event_id": self.event_id, "observation_id": self.observation_id}


@dataclass(frozen=True)
class MentionRecord:
    """One addressed mention: the registry's own ``Mention`` plus where it sits.

    ``mention`` is the object ``apps/interpretation`` produced, unmodified and
    un-wrapped, and it is held *beside* an id rather than inside one because
    ``extractors.registry.Mention`` is not itself content-addressed and nothing
    downstream may key on a bare surface string. This is a position, not a copy.
    """

    mention_id: str
    segment_ref: str
    mention: Mention
    start: int
    end: int

    @property
    def kind(self) -> str:
        """The extractor's own kind, read off the real mention rather than restated."""
        return self.mention.kind

    @property
    def value(self) -> str:
        """The surface the extractor read."""
        return self.mention.value


@dataclass(frozen=True)
class ExecutionRequest:
    """Everything the path needs, supplied by the caller. No default reads a clock.

    The relation's *instruments* are a request, not an orchestrator decision: the
    :class:`~domain.relation_schema.RelationSchema` declares the operator contract,
    the :class:`~semantic.profiles.SemanticProfile` names which types the regime
    declares, and ``type_refs`` is the observed-layer mapping from mention kind to
    type reference. Supplying different instruments is how the same path is driven
    over an unknown type or a wrong range with not one line of this module changed.

    ``regime_store`` is the one field that is a *substrate* rather than an
    instrument, and it is optional for a reason worth stating: ``None`` means the
    path builds its own :class:`~semantic.regime_store.InMemoryRegimeStore` and
    exposes it on :attr:`RegimeStep.store`, which is correct for one run and wrong
    for two - a caller who wants the regime of a previous run to be the regime of
    this one supplies the store. Nothing is lost by the default, because the regime
    is still written and still read back within the run; what a shared store adds is
    the regime *surviving* the run, which is FR-014's actual subject.
    """

    sentence: str
    schema: RelationSchema
    profile: SemanticProfile
    extractors: DeterministicExtractorSet
    observed_at: datetime
    valid_from: datetime
    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    source_id: str = "src-golden-path"
    source_family: str = "src-golden-path"
    independence_group: str = "grp-golden-path"
    document_id: str = "doc-golden-path"
    segment_id: str = "seg-golden-path"
    language: str = "en"
    published_at: datetime | None = None
    valid_to: datetime | None = None
    ontology_version: str = "ontology-1"
    normalization_version: str = "norm-1"
    validation_profile: str = DEFAULT_VALIDATION_PROFILE
    subject_kind: str = "person"
    object_kind: str = "org"
    type_refs: Mapping[str, str] = field(default_factory=_default_type_refs)
    role_names: tuple[str, str] = ("person", "organization")
    subject_role: str = "subject"
    object_role: str = "object"
    extra_candidates: tuple[BlockingCandidate, ...] = ()
    resolution_candidates: tuple[ResolutionCandidate, ...] = ()
    vocabulary: ConceptScheme | None = None
    registry: SemanticRegistry | None = None
    resolution_scope: ResolutionScope | None = None
    collective_max_iterations: int = 16
    revision_number: int = 1
    claim_status: RelationStatus = RelationStatus.ACTIVE
    evidence_grade: EvidenceGrade = EvidenceGrade.MODERATE
    evidence_refs: tuple[str, ...] = ()
    assertion_refs: tuple[str, ...] = ()
    confidence: float = 0.85
    recorded_by: str = "semantic-execution"
    relation_store: InMemoryRelationStore | None = None
    graph_store: InMemoryGraphStore | None = None
    regime_store: RegimeStore | None = None
    capture: Capture | None = None
    """The acquisition record that fetched these bytes, when the caller has one.

    Preferred over the loose fields below: a supplied ``Capture`` is already
    content-addressed and already states its fetch basis. When this is ``None`` and
    ``content_digest``/``target_uri`` are given, the path builds one with
    :attr:`CaptureTimeBasis.INDEX_OBSERVATION` and **no** fetch time, because that is
    what a crawl index can honestly say. When neither is given the capture hop is
    reported absent rather than filled in.
    """
    content_digest: str | None = None
    target_uri: str = ""
    media_type: str = "text/html"
    transport: str = "warc-range"

    #: Feature 019. Producers to run over :attr:`sentence` before assembly, in addition to
    #: the caller's own declaration. Empty by default and that is the *usual* case: a caller
    #: asserting one relation about one sentence does not need discovery, and running
    #: producers nobody asked for would put observations in the record that the request did
    #: not contemplate.
    producers: tuple[RelationSignalExtractor, ...] = ()

    #: The region between the two mentions, when the caller read one. Carried as a mapping
    #: on the declared signal rather than as a live :class:`SpanRef`, so the declared signal
    #: has the same shape as a producer's and the assembler treats them alike.
    trigger_span: SpanRef | None = None

    @property
    def relation_type(self) -> str:
        """The operator identity both the candidate and the claim will carry."""
        return self.schema.relation_type

    @property
    def declared_by(self) -> str:
        """Who asserted this relation, when the caller says.

        Empty by default, and the default is meaningful: an unannotated declaration is
        recorded under ``request/declaration`` rather than under the name of whoever ran the
        process, because the caller's identity and the runner's identity are different facts
        and FR-034's independence count is computed over the first.
        """
        return ""

    def text_for_producers(self) -> str:
        """The text a producer is handed.

        The request's ``sentence``, verbatim, and named so the fact that it is *one
        sentence* rather than a document is visible at the call site. A producer's
        ``Neighbourhood`` will say it read this much, and a reader comparing two producers'
        scopes needs to know they were offered the same thing.
        """
        return self.sentence

    def provenance(self, observation: Observation) -> dict[str, Any]:
        """Store-write provenance for this request (I-12), read off the observation."""
        return observation.provenance()

    def extraction_version(self) -> str:
        """A content address over the extractor set actually bound to this run.

        Recorded in the frame, the type assertions, the candidate and the claim, so
        "which instruments read this" is answerable at every layer and a re-run with
        a different extractor set is a different record rather than a silent
        overwrite (constitution VII).
        """
        return EXTRACTION_SET_VERSION_PREFIX + digest128(
            "|".join(self.extractors.names())
        )[:12]


@dataclass(frozen=True)
class ObservationStep:
    """Step 1: the raw record exists, is addressed, and is what everything else quotes."""

    observation: Observation


@dataclass(frozen=True)
class ContextStep:
    """Step 2: the evidence frame the reading is licensed under (FR-007, I-12).

    Built by ``EvidenceContext``'s own constructor, so ``context_id`` is derived and
    verified rather than supplied, and registered in a real
    :class:`domain.evidence_context.InMemoryContextResolver` so every later
    ``context_ref`` resolves through the one legal path (FR-016).
    """

    frame: EvidenceContext
    resolver: InMemoryContextResolver


@dataclass(frozen=True)
class MentionStep:
    """Step 3: the real ``Mention`` objects, addressed, plus the pack's hint per kind.

    ``hints`` is the advisory semantic surface: ``DeterministicExtractorSet.hint`` is
    called for every mention kind, so *what a vocabulary knows* is recorded even
    though it can never filter anything (FR-002). Every kind the extractor set
    returns is kept - nothing here filters to the two kinds this relation needs and
    nothing drops an unknown one.
    """

    mentions: tuple[Mention, ...]
    records: tuple[MentionRecord, ...]
    subject: MentionRecord
    obj: MentionRecord
    hints: tuple[SemanticHint | None, ...]
    reading: RelationalReading | None = None
    """The relational reading the extraction layer measured, when it found one.

    The same text has two readings: the mentions it contains, and the relation those
    mentions stand in. Only the first existed before feature 018, which is why the
    candidate used to *guess* its trigger span. When this is ``None`` the sentence
    carried no cue, and the candidate falls back to the between-mentions guess and says
    so. It is never synthesised here: extraction reports, this step consumes.
    """

    index: MentionOccurrenceIndex | None = None
    """The :class:`~domain.mention_occurrence_index.MentionOccurrenceIndex` over this step's
    records, and the thing a producer's deferred address is resolved **through**.

    Carried rather than rebuilt because there is exactly one index per
    ``(capture, segment, extractor)`` scope, and a second one would be a second answer to "which
    mention is this address?". The scope is required rather than defaulted, so ``None`` means the
    request supplied no capture and no mention id could be minted honestly - it is never a
    placeholder scope with an invented member (FR-016, FR-018).

    **What it is for, and what it is not.** It answers "which ``MN-…`` is this occurrence?", and
    that is the whole of it. Reconciling a producer's address to a mention is this index's job and
    only this index's; deciding whether two mentions are the *same thing* is coreference, it
    belongs to :mod:`semantic.resolution`, and it has a ``ResolutionDecisionRecord`` behind it
    (constitution Invariant 2).
    """


@dataclass(frozen=True)
class TypeStep:
    """Step 6: the observed typing layer, one assertion per relation end (FR-003).

    ``scope=OBSERVED`` and ``status=OBSERVED`` unconditionally: this layer is what
    the extractor said, and it consults no profile, no pack and no ontology. An
    unknown type reference is recorded verbatim and is a first-class value, so no
    input to this step can fail on unfamiliar content (FR-001).

    ``entity_ref`` on each assertion is the **resolved** entity from step 5, not a
    digest of the mention. That is the visible consequence of running resolution first:
    the type is asserted about the entity the mention actually resolved to, so the
    validator's domain/range stage and the claim's participants agree by construction
    rather than by coincidence.
    """

    assertions: tuple[TypeAssertion, ...]
    subject: TypeAssertion
    obj: TypeAssertion
    by_entity: Mapping[str, tuple[TypeAssertion, ...]] = field(default_factory=dict)

    def assertions_for(self, entity_ref: str) -> tuple[TypeAssertion, ...]:
        """Every typing claim recorded about one entity, across all layers."""
        return self.by_entity.get(entity_ref, ())


class RegimeVerdict(StrEnum):
    """Whether the regime in force could be resolved from durable storage (FR-015).

    Two answers and no third, mirroring
    :class:`~semantic.resolution.ResolutionVerdict` for the same reason: a check that
    could not be evaluated must be able to say so instead of collapsing into pass or
    fail. ``RESOLVED`` means the store returned the record and the path rehydrated it
    into the regime the comparison will use. ``UNRESOLVED`` means it did not, and
    :attr:`RegimeResolution.reason` says why in words.

    There is deliberately no ``UNEVALUATED`` member here. The compatibility layer's
    ``regime_unevaluated`` verdict is a *different* fact - one side of a comparison
    names no regime - and keeping the two vocabularies distinct is the point: a regime
    that resolved and was compared, a regime that did not resolve, and a candidate
    that names no regime are three conditions, and this enum refuses to be the answer
    to the third.
    """

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"

    @property
    def is_resolved(self) -> bool:
        """Whether a real regime was recovered. Only ``RESOLVED`` did."""
        return self is RegimeVerdict.RESOLVED


@dataclass(frozen=True)
class RegimeResolution:
    """What storage said about the regime this run needs, and what it said in words.

    The first half of FR-015's requirement, as a value rather than a log line: an
    unresolvable regime is a **stated** ``UNRESOLVED`` carrying
    :attr:`reason`, never a silent absence and never a substituted default. The second
    half - "and MUST be counted" - is the store's
    :meth:`~semantic.regime_store.RegimeStore.unresolved_reads`, because the read is
    what was counted and the counting belongs where the read happens.

    :attr:`record` is ``None`` exactly when :attr:`verdict` is ``UNRESOLVED``, and it is
    never an empty or default record: there is no constructor path in this module that
    produces a :class:`~semantic.regime_store.RegimeRecord` with an empty ``regime_id``,
    because FR-016 forbids substituting an empty regime and proceeding as though it
    matched.
    """

    regime_id: str
    tenant_id: str
    context_ref: str
    verdict: RegimeVerdict
    record: RegimeRecord | None = None
    reason: str = ""

    @property
    def is_resolved(self) -> bool:
        """Whether a stored regime was recovered for this run."""
        return self.verdict.is_resolved

    def as_record(self) -> RegimeRecord:
        """The stored record, or a refusal naming this resolution's own reason.

        The one place the "no substitution" rule is mechanically enforced on this path:
        there is no default to fall back to, so an unresolved regime can only be a
        refusal. A caller that must not proceed on an unresolved regime gets an
        exception carrying the id, the tenant, the frame and the reason, rather than a
        regime that was never read from anywhere.
        """
        if self.record is None:
            raise SemanticExecutionError(
                "regime_unresolved",
                f"semantic regime {self.regime_id!r} for tenant {self.tenant_id!r} over frame "
                f"{self.context_ref!r} could not be resolved from storage: {self.reason}. "
                "No substitute regime is used and no comparison is run, because proceeding "
                "under a regime nobody wrote down is the silent substitution FR-016 "
                "forbids. Persist the regime through RegimeStore.ingest_regime and re-run.",
            )
        return self.record


@dataclass(frozen=True)
class RegimeStep:
    """Step 4: the instruments that interpreted it, the frame they extend, and the record.

    The regime *points at* the frame and the frame never points back, so
    :func:`semantic.regime.extend_context` returns a **new** content-addressed frame
    and the base frame keeps its own id forever. The claim is admitted under the
    extended frame - that is the one carrying ``ontology_version`` and ``language``
    as the regime pinned them - and both stay registered, so nothing already pointing
    at the base one stops resolving (FR-014, FR-018).

    It runs before resolution because the resolver's context layer compares the
    mention's ``regime_id`` against each candidate's, and persisting the regime first
    is what turns that comparison from ``UNEVALUATED`` into a real answer (D6).

    **The regime is written, and then read back.** :attr:`record` is what the store
    holds - a :class:`~semantic.regime_store.RegimeRecord` with its own second address -
    and :attr:`regime` is that record rehydrated, *not* the value this step built. The
    distinction is the whole of FR-015: the path proves its regime survives a round
    trip through storage before it is allowed to compare anything under it, and a
    regime that failed to round trip would raise at construction rather than be used.
    :attr:`store` is exposed so a caller can read the regime back independently, and so
    a second run can be handed the same store.
    """

    resolution: ProfileResolution
    regime: SemanticRegime
    base_frame: EvidenceContext
    frame: EvidenceContext
    record: RegimeRecord
    store: RegimeStore

    def instrument_refs(self) -> tuple[str, ...]:
        """Every instrument the stored regime records as bound, canonically ordered.

        Read off :attr:`record` rather than recomputed from :attr:`regime`, so this is a
        statement about what is *durable* - which is the question "what did we believe
        when we read this?" and not the question "what did this local variable hold".
        """
        return self.record.instrument_refs()


@dataclass(frozen=True)
class ResolutionStep:
    """Step 5: the real resolution machine, its decisions, and its measured blocking outcome.

    The whole of :mod:`semantic.resolution` is here, unflattened: the
    :class:`~semantic.resolution.MentionResolver` that ran, the
    :class:`~semantic.resolution.ResolutionBatch` it returned, the
    :class:`~semantic.resolution.BlockingOutcome` with the reported
    ``before_count``/``after_count``/``reduction_ratio`` (SC-10), the collective
    outcome, and the two decisions for this sentence's two ends.

    ``subject_ref``/``object_ref`` are read off the *decisions* - the resolved
    ``logical_entity_ref`` of each end - and are empty strings when that end did not
    resolve. There is no fallback to a mention-derived ref anywhere in this path: a
    participant that was not identified is named by nothing, and the steps that need a
    real participant refuse with a code rather than inventing one.

    :attr:`regime` is the :class:`~semantic.regime_store.RegimeRecord` this stage **read
    back from storage**, not the one step 4 held in memory, and both the mentions and the
    candidate universe were handed *that* address. So the regime comparison the resolver
    performed was a comparison of two durable addresses, and
    :attr:`regime_verdicts` reports what it concluded per candidate. On the golden path
    every entry is ``regime_compatible`` and :attr:`unevaluated_regimes` is empty; a
    non-empty tuple is the D6 defect returning, and it is a value a caller can assert on
    rather than a thing to be inferred from reading reason codes.
    """

    resolver: MentionResolver
    batch: ResolutionBatch
    scope: ResolutionScope
    operator: RelationOperator
    subject_decision: ResolutionDecision
    object_decision: ResolutionDecision
    regime: RegimeRecord
    store: RegimeStore

    @property
    def decisions(self) -> tuple[ResolutionDecision, ...]:
        return self.batch.decisions

    @property
    def subject_ref(self) -> str:
        """The resolved entity for the subject end, or ``""`` when it did not resolve."""
        return self.subject_decision.logical_entity_ref

    @property
    def object_ref(self) -> str:
        """The resolved entity for the object end, or ``""`` when it did not resolve."""
        return self.object_decision.logical_entity_ref

    @property
    def verdicts(self) -> Mapping[str, ResolutionVerdict]:
        """Every mention's verdict, so a caller can see an ambiguity without reading a decision."""
        return self.batch.verdicts()

    def independence_groups(self) -> tuple[tuple[str, ...], ...]:
        """Independence groups backing the two resolved ends, for the admitted claim.

        Forwarded rather than recomputed, so the corroboration the resolver actually found
        reaches ``RelationClaim.source_independence_groups`` and the ``cross_source``
        validation stage has something to evaluate. Without this the resolver computed
        corroboration, the claim reported ``independent_source_count == 0``, and FR-034 was
        untestable through this path.

        One group per resolved end, and an end that did not resolve contributes no group at
        all. An ambiguous end is *not* credited with the groups of its surviving candidates:
        choosing between them is exactly what has not happened, so attributing one candidate's
        backing to the claim would assert corroboration for a decision nobody made.
        """
        groups: list[tuple[str, ...]] = []
        for decision in (self.subject_decision, self.object_decision):
            if decision.verdict is not ResolutionVerdict.RESOLVED:
                continue
            supporting = self.batch.supporting_groups_for(decision.logical_entity_ref)
            if supporting:
                groups.append(supporting)
        return tuple(groups)

    @property
    def blocking_reductions(self) -> Mapping[str, float]:
        """The reported blocking reduction per mention (SC-10, FR-016)."""
        return self.batch.blocking_reductions()

    @property
    def unresolved(self) -> tuple[ResolutionDecision, ...]:
        """The decisions that named no entity, canonically ordered."""
        return tuple(
            decision
            for decision in self.batch.decisions
            if not decision.logical_entity_ref
        )

    def reason_codes(self, mention_id: str) -> tuple[str, ...]:
        """The recorded compatibility reason codes for one mention."""
        decision = self.batch.decision_for(mention_id)
        return () if decision is None else decision.reason_codes()

    @property
    def regime_verdicts(self) -> Mapping[str, str]:
        """Every candidate's regime-comparison verdict, keyed by candidate ref (FR-015).

        Read straight off the machine's own recorded
        :class:`~semantic.resolution.CompatibilityReason` values - surviving and
        blocked-out alike, so a candidate pruned by another layer still has its regime
        verdict reported rather than vanishing from the picture. Nothing is recomputed
        here: the point of the property is that a caller can read what the resolver
        concluded, and a recomputation would answer a slightly different question.

        Three codes are possible and they mean three different things:
        ``regime_compatible`` (both sides name the same stored regime),
        ``regime_mismatch`` (both name one, and they differ - a real graded answer,
        not a failure), and ``regime_unevaluated`` (one side names none, which is D6
        returning and must be zero on the ordinary path).
        """
        return regime_verdicts_for(self.batch)

    @property
    def unevaluated_regimes(self) -> tuple[str, ...]:
        """Candidates whose regime comparison had nothing to compare - empty on a real run.

        The direct, assertable form of FR-015: a non-empty tuple means some candidate
        reached the context layer without a stored regime on one side, which is the
        defect the spec describes. It is a property rather than a log line so a caller
        can fail on it.
        """
        return tuple(
            ref
            for ref, code in self.regime_verdicts.items()
            if code == REGIME_UNEVALUATED
        )

    @property
    def unresolved_regime_reads(self) -> int:
        """How many regime reads have come back empty on this store (FR-015's count).

        Zero on any run that resolved its regime, and the number to watch: a count that
        is not zero is the platform saying out loud that a regime it needed was not
        where it looked for it.
        """
        return self.store.unresolved_reads()


@dataclass(frozen=True)
class CandidateStep:
    """Step 7: the extraction hypothesis, its operator contract, and the reading.

    ``proposed`` is the ``PROPOSE`` reading extraction produced, and it is the *only*
    reading this step produces (feature 019, CD-1).

    **There used to be a second one.** The step returned both ``proposed`` and
    ``supported`` - the same hypothesis relabelled ``SUPPORTED`` - because
    ``to_claim`` demanded that label, and the only way to get an unlabelled reading into
    the claim layer was to write the label on it. That made the second field a
    ceremony: it was derived from the first by a string assignment, and its distinct
    ``candidate_id`` was evidence of nothing except that a string had been written.

    So the field is gone rather than deprecated, because keeping it would keep inviting
    the use. What replaced it is a gate that reads evidence: :func:`build` then
    :func:`domain.relation_claim_material.validate` then :func:`admit`, in
    :func:`_claim_step`. A reading that fails validation is refused there, and a reading
    that passes is committed on its merits - which is a stronger statement than a label
    ever was, and one a caller cannot satisfy by writing on a record.

    The operator is the one :class:`ResolutionStep` already derived from the same
    schema, handed forward rather than derived a second time: blocking (inside the
    resolver) and the extraction contract must be the *same* operator, and two
    derivations of one value is how they stop being the same.
    """

    schema: RelationSchema
    operator: RelationOperator
    proposed: RelationCandidate


@dataclass(frozen=True)
class SignalStep:
    """Step 6b: what producers saw, and what assembly made of it (feature 019, T034).

    Two sources of signals are kept apart on purpose, because conflating them would be the
    easiest way to make this stage lie:

    * :attr:`declared` is the caller's own statement - "this observation asserts that this
      subject relates to this object". It arrives as a :attr:`~extractors.signals.signal.
      SignalKind.SCHEMA` signal over the **real** mention ids, which is what lets the
      assembled candidate be the one the rest of the path expects without a special case.
    * :attr:`discovered` is what producers *observed* in the document. These address their
      endpoints as surfaces, because a producer sits below the mention layer and minting
      mention ids would put mention identity inside extraction.

    The two are assembled together and :attr:`report` holds the result, so the declared
    hypothesis and the discovered ones are competing readings of the same evidence rather
    than two unrelated collections. :attr:`unattributed` is the number that matters: signals
    that were seen and not attributed to any candidate, which
    :attr:`AssemblyReport.complete` refuses.
    """

    declared: RelationSignal
    discovered: tuple[RelationSignal, ...] = ()
    report: AssemblyReport | None = None

    @property
    def all_signals(self) -> tuple[RelationSignal, ...]:
        return (self.declared, *self.discovered)

    @property
    def complete(self) -> bool:
        """Whether every signal reached some candidate."""
        return self.report is not None and self.report.complete

    @property
    def unattributed(self) -> tuple[str, ...]:
        return () if self.report is None else self.report.unattributed_signal_ids

    def candidates_matching(self, relation_ref: RelationRef | None) -> tuple[RelationCandidate, ...]:
        """Assembled candidates whose predicate is ``relation_ref``.

        A ``None`` ref matches only the unresolved readings, which is deliberate: asking
        "the candidates with no operator type" is a real question CD-6 makes askable, and
        answering it with the typed ones would make the question unaskable.
        """
        if self.report is None:
            return ()
        if relation_ref is None:
            return tuple(c for c in self.report.candidates if c.relation_ref is None)
        return tuple(c for c in self.report.candidates if c.relation_ref == relation_ref)


@dataclass(frozen=True)
class ValidationStep:
    """Step 9: the layered, graded report, and the validator that produced it.

    Findings only, and nothing removed. ``report`` carries one finding per stage that
    ran; ``unevaluated`` names the stages that did not, so "nothing wrong" and
    "nothing checked" never read the same (SC-9).
    """

    report: ValidationReport
    outcomes: tuple[StageOutcome, ...]
    validator: LayeredValidator

    @property
    def adverse(self) -> tuple[str, ...]:
        """Codes of the findings indicating a real contradiction, canonically ordered."""
        return tuple(sorted(finding.code for finding in self.report.adverse_findings()))

    @property
    def codes(self) -> tuple[str, ...]:
        """Every finding code the report carries, in report order."""
        return tuple(finding.code for finding in self.report.findings)

    @property
    def unevaluated(self) -> tuple[str, ...]:
        """Stages that produced no finding at all - never checked, not passed."""
        return tuple(str(stage) for stage in self.report.unevaluated_stages())


@dataclass(frozen=True)
class AdmissionStep:
    """Step 10: the admission decision, as a named, operator-scoped value.

    Never a boolean. Under the default ``warn`` policy ``decision.materialisable`` is
    ``True`` however adverse the findings were, and ``decision.scope`` records that
    the answer is about *this operator's view* and about nothing else - which is
    SC-8 exactly: a ``works_for`` whose object is not organization-like produces a
    finding, a materialised claim and a projected edge (FR-012).
    """

    decision: MaterialisationDecision


@dataclass(frozen=True)
class ClaimStep:
    """Step 8: the checked reading promoted to a claim, with identity derived once.

    :meth:`RelationCandidate.to_claim` is the only path across and it raises rather
    than returning ``None`` for a non-admissible reading, so reaching a claim *is*
    the admission act rather than a formality. Both identity levels were re-derived
    from the claim's own fields inside that call, so a claim whose ids disagreed
    with its contents cannot be constructed (FR-004).
    """

    claim: RelationClaim
    candidate_id: str
    logical_candidate_id: str


@dataclass(frozen=True)
class StoreStep:
    """Step 11: a real write through the real store, twice, read back and checksummed.

    The second write is the idempotency proof (I-11): identical content under one
    ``relation_id`` returns the same id, the count is unchanged and so is the
    checksum. Provenance is enforced *before* anything is stored, so a refusal would
    leave the store byte-identical rather than half-written (I-12). ``checksum`` is
    content-only and order-independent, so it is comparable across processes and
    rebuilds (FR-040).
    """

    relation_id: str
    stored: RelationClaim
    checksum: str
    store: InMemoryRelationStore
    write_count_before_repeat: int
    write_count_after_repeat: int


@dataclass(frozen=True)
class EdgeStep:
    """Step 12: the graph projection, in both of its forms.

    ``edge`` is the pairwise projection with direction preserved and ``edge_id`` the
    claim's own ``relation_id`` - minted by the relation layer, never invented here.
    ``hyperedge`` is the authoritative N-ary projection, present because this relation
    is declared ``NARY``; it is not a clique expansion of the pairwise form (FR-045).
    The two neighbour reads prove direction survived the projection: ``out_neighbors``
    answers from the subject, ``in_neighbors`` from the object, and neither contains
    the other endpoint (FR-010, spec 016 D2).
    """

    edge: GraphEdge
    nodes: tuple[GraphNode, ...]
    hyperedge: HyperEdge | None
    out_neighbors: tuple[str, ...]
    in_neighbors: tuple[str, ...]
    store: InMemoryGraphStore


@dataclass(frozen=True)
class WorldlineStep:
    """Step 13: a real occurrence on a real entity's trajectory.

    The record is a genuine :class:`domain.dynamics.StreamRecord` carrying the claim's
    participants, its occurrence instant with the declared precision, its confidence
    and the trigger span, and its own fields carry the observation reference that
    makes the event evidence-backed. The fold is the real
    :func:`domain.temporal_worldline.build_worldline`, so the event id is a content
    address over the occurrence, the participants, the state transition and the
    record hash, and the worldline's integrity fingerprint covers exactly the records
    that built it (I-11, I-12). Nothing here is a placeholder.
    """

    record: StreamRecord
    worldline: EntityWorldline
    events: tuple[WorldlineEvent, ...]
    entity_id: str


@dataclass(frozen=True)
class LineageBundle:
    """Both directions of the evidence chain, and the objects the hops name.

    ``backward`` and ``forward`` are the two traces
    :class:`domain.evidence_lineage.EvidenceGraph` produced, unmodified. This bundle
    traverses nothing: it names the graph, the two traces, and the real objects a
    reader needs to inspect the hops, so verifying a chain is comparing ids rather
    than re-walking edges.
    """

    graph: EvidenceGraph
    relation_id: str
    edge_id: str
    claim: RelationClaim
    candidate: RelationCandidate
    type_assertions: tuple[TypeAssertion, ...]
    mentions: tuple[MentionRecord, ...]
    segment_id: str
    capture_id: str
    source_id: str
    observation: Observation
    backward: LineageTrace
    forward: LineageTrace

    @property
    def hop_ids(self) -> frozenset[str]:
        """Every node id either trace reached, for membership checks."""
        return frozenset(hop.node_id for hop in (*self.backward.hops, *self.forward.hops))

    @property
    def logical_ids(self) -> tuple[tuple[str, str], ...]:
        """Which *logical* thing each record is about - the second identity level.

        Not on the lineage, because a logical id names a chain rather than a node:
        every revision of one relation shares it, and a hop is a revision. It is
        exposed here so a reader can go from a node to its chain without walking.
        """
        return (
            ("relation", self.claim.logical_relation_id),
            ("candidate", self.candidate.logical_candidate_id),
            *(
                ("type_assertion", assertion.logical_type_assertion_id)
                for assertion in self.type_assertions
            ),
        )

    def backward_lineage(self) -> LineageTrace:
        """``GraphEdge -> RelationClaim -> ... -> Source``, as the primitive reports it."""
        return self.backward

    def forward_lineage(self) -> LineageTrace:
        """``Source -> ... -> GraphEdge``, as the primitive reports it."""
        return self.forward


@dataclass(frozen=True)
class ExecutionResult:
    """Every real object the path produced, up to the stage that was reached.

    One field per stage, each holding the typed value that step returned. A field is
    ``None`` exactly when its stage was not reached, and ``reached`` names the last
    one that was, so a caller can tell "not run" from "ran and found nothing".
    """

    request: ExecutionRequest
    reached: ExecutionStage | None = None
    observation: ObservationStep | None = None
    context: ContextStep | None = None
    mentions: MentionStep | None = None
    signals: SignalStep | None = None
    regime: RegimeStep | None = None
    resolution: ResolutionStep | None = None
    types: TypeStep | None = None
    candidate: CandidateStep | None = None
    claim: ClaimStep | None = None
    validation: ValidationStep | None = None
    admission: AdmissionStep | None = None
    store: StoreStep | None = None
    edge: EdgeStep | None = None
    worldline: WorldlineStep | None = None
    lineage: LineageBundle | None = None

    def stage(self, stage: ExecutionStage | str) -> Any:
        """The typed value one stage returned, or ``None`` if it was not reached."""
        return getattr(self, ExecutionStage(stage))

    def reached_through(self, stage: ExecutionStage | str) -> bool:
        """Whether ``stage`` ran, whatever its result was."""
        wanted = ExecutionStage(stage)
        return self.reached is not None and wanted.rank() <= self.reached.rank()

    def identifiers(self) -> tuple[tuple[str, str], ...]:
        """Every id this run produced, in stage order, for byte-comparison across runs.

        The only summary in this module. It exists solely so two processes can be
        diffed, and it is not a substitute for the typed fields above.
        """
        pairs: list[tuple[str, str]] = []
        if self.observation is not None:
            pairs.append(("observation", self.observation.observation.observation_id))
            pairs.append(("event", self.observation.observation.event_id))
        if self.context is not None:
            pairs.append(("context", self.context.frame.context_id))
        if self.mentions is not None:
            pairs.extend(("mention", record.mention_id) for record in self.mentions.records)
        if self.regime is not None:
            pairs.append(("regime", self.regime.regime.regime_id))
            pairs.append(("regime_record", self.regime.record.record_fingerprint))
            pairs.append(("interpreted_context", self.regime.frame.context_id))
        if self.resolution is not None:
            step = self.resolution
            pairs.append(("resolution_scope", step.scope.scope_id))
            pairs.append(("resolution_regime", step.regime.regime_id))
            for label, decision in (
                ("subject", step.subject_decision),
                ("object", step.object_decision),
            ):
                pairs.append((f"entity_{label}", decision.logical_entity_ref or "-"))
                pairs.append((f"resolution_{label}", decision.resolution_decision_id))
                pairs.append((f"resolution_verdict_{label}", str(decision.verdict)))
                blocking = decision.blocking
                if blocking is not None:
                    pairs.append((f"block_{label}", blocking.content_key()))
        if self.types is not None:
            pairs.extend(
                ("type_assertion", item.type_assertion_id) for item in self.types.assertions
            )
            pairs.extend(
                ("logical_type_assertion", item.logical_type_assertion_id)
                for item in self.types.assertions
            )
        if self.candidate is not None:
            step = self.candidate
            # One reading, one key. The fingerprint listed both `proposed_candidate` and
            # `candidate` because step 7 produced two readings under two labels (CD-1);
            # with the relabelled reading gone they are the same value, and carrying a
            # duplicate would make the fingerprint imply a distinction that no longer
            # exists. `candidate` is the historical name and is what a reader expects.
            pairs.append(("candidate", step.proposed.candidate_id))
            pairs.append(("logical_candidate", step.proposed.logical_candidate_id))
        if self.claim is not None:
            pairs.append(("relation", self.claim.claim.relation_id))
            pairs.append(("logical_relation", self.claim.claim.logical_relation_id))
        if self.validation is not None:
            pairs.append(("validation_report", self.validation.report.report_id))
        if self.admission is not None:
            pairs.append(("materialisation", str(self.admission.decision.code)))
        if self.store is not None:
            pairs.append(("store_checksum", self.store.checksum))
        if self.edge is not None:
            pairs.append(("edge", self.edge.edge.edge_id))
            if self.edge.hyperedge is not None:
                pairs.append(("hyperedge", self.edge.hyperedge.edge_id))
        if self.worldline is not None:
            pairs.append(("record", self.worldline.record.record_id))
            pairs.extend(("event", event.event_id) for event in self.worldline.events)
            pairs.append(("worldline", self.worldline.worldline.integrity_fingerprint))
        return tuple(pairs)


def deterministic_extractors(
    *,
    role_target_orgs: bool = True,
    ontology_pack: object | None = None,
) -> DeterministicExtractorSet:
    """A fresh deterministic extractor set: the built-ins plus the relational reader.

    ``role_target_orgs`` registers ``extractors.relations``' relation-aware reader
    under its own name. That rule used to live *here*, and moving it out is the whole
    point of feature 018 FR-018: an orchestrator holding extraction rules is an
    orchestrator that cannot be reasoned about as an orchestrator, and the gap it was
    patching is a gap in the extraction layer.

    The gap was real, and it was not about a missing suffix. ``extractors.orgs`` keys
    on a legal-form suffix (``Inc``/``Corp``/``Ltd``/...), so ``"Acme"`` alone in
    ``"John Smith became CEO of Acme in 2020."`` yields no organisation mention at all.
    The rule that finds it keys on the *relational cue* instead and reads the object
    **through** the relation, which is why it is a projection of the cue machinery
    (``extractors.relations``) rather than another suffix grammar. Adding a third
    relation is a third row in ``RELATION_CUES``, not a third function here.

    ``ontology_pack`` is forwarded untouched and is advisory: it annotates mentions
    with what a pack recognises and can never filter one (FR-002).
    """
    extractors = DeterministicExtractorSet(ontology_pack=ontology_pack)
    extractors.register_builtin()
    if role_target_orgs:
        register_relational_extractors(extractors)
    return extractors




def works_for_schema(schema_version: str = "1") -> RelationSchema:
    """The ``works_for`` contract: two named roles, one pair, one instant.

    ``NARY`` rather than ``DIRECTED`` because the claim shape this slice produces is
    the role-assignment one - ``Employment{person, organization}`` - and 016 ADR-0023
    makes arity mode part of identity material, so the two shapes are genuinely
    different relations rather than two spellings of one relation.

    The admissible evidence patterns are the two this path can satisfy *and*
    re-check: a relation pattern (at least one observation ref) and a context (a
    resolvable evidence frame). ``mention_pair`` is deliberately not declared,
    because this slice reads one observation - declaring it and then satisfying it
    with a segment ref would grade a single document as two observations, which is
    exactly the volume-for-corroboration substitution constitution IV forbids.
    """
    return RelationSchema(
        relation_type="works_for",
        arity_mode=RelationArityMode.NARY,
        allowed_subject_classes=frozenset({"schema:Person"}),
        allowed_object_classes=frozenset({"schema:Organization"}),
        allowed_role_bindings=(
            RelationRoleBinding("organization", ""),
            RelationRoleBinding("person", ""),
        ),
        allowed_role_classes={
            "organization": frozenset({"schema:Organization"}),
            "person": frozenset({"schema:Person"}),
        },
        admissible_evidence_patterns=("context", "relation_pattern"),
        temporal_semantics=TemporalSemantics.POINT,
        schema_version=schema_version,
    )


def base_profile(
    *type_refs: str,
    tenant_id: str = "default-tenant",
    profile_id: str = "golden-path",
    version: str = "1",
) -> SemanticProfile:
    """A profile declaring exactly the types it names, and nothing it does not.

    This is the whole point of the open-world cases: a profile that omits a type is
    not a profile that refutes it. Leave ``local:shell_company`` out of this profile
    and the semantic stage reports ``not_declared_in_profile`` with verdict
    ``UNKNOWN`` - an unevaluable check - and the claim still materialises and the
    edge still projects (FR-001, SC-9).
    """
    return SemanticProfile(
        profile_id=profile_id,
        version=version,
        type_refs=tuple(type_refs) or ("schema:Organization", "schema:Person"),
        relation_refs=("works_for",),
        applies_to=frozenset({"source", "extractor"}),
        description="golden path instruments; a hint surface, never a gate",
        tenant_id=tenant_id,
    )


def decoy_universe() -> tuple[BlockingCandidate, ...]:
    """Three non-matching candidates, so blocking has something real to reduce.

    Each is pruned at a different stage, which is the point. ``Acme Holdings`` is
    organization-like and type-sharing and is removed only by the name stage;
    ``Acme Group`` is removed by the affordance stage; ``Globex`` declares no kind at
    all and is therefore *retained* through the kind stage by the default ``retain``
    policy - pruning on an absent fact is an assertion by omission - before the name
    stage removes it too.

    They are returned as :class:`semantic.blocking.Candidate` because that is what
    ``extra_candidates`` has always been; :func:`resolution_candidate_for` projects them
    into the shape the resolver compares, adding the tenant and no invented content.
    """
    return (
        BlockingCandidate(
            entity_ref=_ENTITY_ID_PREFIX + digest128("decoy:acme-holdings"),
            name="Acme Holdings",
            kind="schema:Organization",
            type_refs=("schema:Organization",),
        ),
        BlockingCandidate(
            entity_ref=_ENTITY_ID_PREFIX + digest128("decoy:acme-group"),
            name="Acme Group",
            kind="schema:Company",
            type_refs=("schema:Company",),
        ),
        BlockingCandidate(
            entity_ref=_ENTITY_ID_PREFIX + digest128("decoy:globex"),
            name="Globex",
        ),
    )


def resolution_candidate_for(
    candidate: BlockingCandidate,
    *,
    tenant_id: str = "default-tenant",
    investigation_id: str = "",
    ontology_version: str = "",
    normalization_version: str = "",
) -> ResolutionCandidate:
    """Project one universe record into the shape the resolver compares.

    A projection, not a conversion: the name, kind, types and - importantly - the
    **established** ``entity_ref`` are carried across unchanged, and everything the
    ``BlockingCandidate`` never had is left at its default rather than invented. So a
    universe entry that already names an entity keeps naming it, and one that does not
    is honestly un-identified until the resolver anchors it to a mention.
    """
    return ResolutionCandidate(
        entity_ref=candidate.entity_ref,
        name=candidate.name,
        kind=candidate.kind,
        type_refs=tuple(candidate.type_refs),
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        ontology_version=ontology_version,
        normalization_version=normalization_version,
    )


def golden_vocabulary() -> ConceptScheme:
    """The one local SKOS scheme the golden path resolves names through.

    The reason it exists is specific and is the point of the whole exercise: the golden
    sentence says ``"Acme"`` and the entity table says ``"Acme Corporation"``. Those are
    two surface forms, and without a vocabulary the resolver has no standing to call them
    one thing - it would be doing string surgery in the identity layer. So the scheme
    records ``acme:AcmeCorporation`` with ``"Acme"`` and ``"Acme Corp"`` as alternative
    labels, and :class:`semantic.resolution.MentionResolver` asks the registry for the
    labels rather than guessing at them (FR-015, US8).

    The concept carries a ``closeMatch`` to ``schema:Organization`` rather than an
    equality, because SKOS records correspondence and never identity, and resolution must
    not read a correspondence as one (FR-008).
    """
    return ConceptScheme.from_concepts(
        "golden-path",
        (
            Concept(
                concept_id="acme:AcmeCorporation",
                pref_label="Acme Corporation",
                alt_labels=("Acme", "Acme Corp"),
                close_match=("schema:Organization",),
            ),
            Concept(
                concept_id="globex:GlobexCorporation",
                pref_label="Globex Ltd",
                alt_labels=("Globex Limited",),
                close_match=("schema:Organization",),
            ),
            Concept(concept_id="schema:Organization", pref_label="Organization"),
            Concept(concept_id="schema:Person", pref_label="Person"),
        ),
        version="1",
    )


def golden_candidates(
    *,
    tenant_id: str = "default-tenant",
    investigation_id: str = "inv-golden-path",
    ontology_version: str = "ontology-1",
    normalization_version: str = "norm-1",
    with_decoys: bool = True,
) -> tuple[ResolutionCandidate, ...]:
    """The entity table the golden path resolves its mentions against.

    This is the fixture that replaces the old lie. Previously the "universe" was built out
    of the mentions themselves, so the platform was resolving a mention against a copy of
    itself and the resulting identity was circular. Now it is an ordinary table of
    pre-existing records, each with an established ``ENT-`` ref, a validity window that
    reaches back before the sentence, and its own support:

    * ``Acme Corporation`` and ``John Smith`` are the two records the sentence is about;
    * each already carries one mention from an **independent** group, so corroboration is
      real rather than the mention corroborating itself;
    * ``with_decoys`` appends the three records from :func:`decoy_universe` so blocking has
      something to reduce. :func:`golden_request` passes ``with_decoys=False`` here and
      supplies those three through ``extra_candidates`` instead, because they are the same
      records and the universe should hold each exactly once.

    The refs are content addresses over fixed material, so the table is the same in every
    process and a diff between two runs means something changed.

    **The support mention is the one ``MN-`` on this path with no occurrence behind it.** It is a
    corpus constant naming a mention an independent group is said to have seen, and the registry
    it names does not exist in this slice - so it is minted through
    :func:`domain.mention_occurrence_index.unbound_mention_id`, which is the *only* ``MN-`` on the
    platform that is deliberately not resolvable through
    :class:`domain.mention_occurrence_index.MentionOccurrenceIndex`. It is stated here rather than
    quietly left as a string concatenation, because a fixture that resolved would be a claim about
    provenance that nothing backs.
    """
    records = (
        ("acme-corporation", "Acme Corporation", "schema:Organization"),
        ("john-smith", "John Smith", "schema:Person"),
    )
    table = [
        ResolutionCandidate(
            entity_ref=_ENTITY_ID_PREFIX + digest128(f"golden-entity:{key}"),
            name=name,
            kind=kind,
            type_refs=(kind,),
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            ontology_version=ontology_version,
            normalization_version=normalization_version,
            source_family="src-registry",
            independence_group="grp-registry",
            valid_from=datetime(2010, 1, 1, tzinfo=UTC),
            valid_to=None,
            observed_at=datetime(2019, 11, 1, tzinfo=UTC),
            support_mention_ids=(
                unbound_mention_id(f"golden-support:{key}"),
            ),
            supporting_groups=("grp-registry",),
        )
        for key, name, kind in records
    ]
    if with_decoys:
        table.extend(
            resolution_candidate_for(
                decoy,
                tenant_id=tenant_id,
                investigation_id=investigation_id,
                ontology_version=ontology_version,
                normalization_version=normalization_version,
            )
            for decoy in decoy_universe()
        )
    return tuple(table)


@dataclass(frozen=True)
class _Unset:
    """The type of :data:`UNSET`, so a request field can be *emptied*, not only defaulted.

    :func:`golden_request` needs to tell "the caller did not mention this" from "the caller
    asked for none of these", because the second is a real case: an empty candidate universe
    is how a caller asks what the path does with nothing to resolve against, and no
    vocabulary is how a caller asks what it does without the semantic layer. A default of
    ``None`` cannot express both, and an empty tuple cannot express "use the golden table".
    """

    label: str = "unset"


#: The "not specified" marker for :func:`golden_request`'s resolution fields.
UNSET = _Unset()


def golden_request(
    sentence: str = GOLDEN_SENTENCE,
    *,
    type_refs: Mapping[str, str] | None = None,
    profile_type_refs: Iterable[str] = ("schema:Person", "schema:Organization"),
    valid_from: datetime = datetime(2020, 1, 1, tzinfo=UTC),
    valid_to: datetime | None = None,
    observed_at: datetime = datetime(2020, 6, 1, tzinfo=UTC),
    published_at: datetime | None = None,
    tenant_id: str = "default-tenant",
    investigation_id: str = "inv-golden-path",
    schema: RelationSchema | None = None,
    profile: SemanticProfile | None = None,
    extractors: DeterministicExtractorSet | None = None,
    with_decoys: bool = True,
    resolution_candidates: tuple[ResolutionCandidate, ...] | _Unset = UNSET,
    extra_candidates: tuple[BlockingCandidate, ...] | _Unset = UNSET,
    vocabulary: ConceptScheme | None | _Unset = UNSET,
    **overrides: Any,
) -> ExecutionRequest:
    """A fully specified request over the golden sentence, with every id stable.

    Every timestamp is a parameter with an explicit default rather than a clock read,
    so a caller who wants a different window asks for one and a caller who does not
    gets the same ids on every run and in every process. ``**overrides`` passes
    straight through to :class:`ExecutionRequest`, so a variant is a keyword argument
    and never an edit of this function.

    The three resolution fields accept :data:`UNSET` so a caller can pass ``()`` or ``None``
    to ask for a genuinely empty universe or a genuinely absent vocabulary - which is how the
    smoke run demonstrates that an unresolvable mention is refused rather than guessed.
    """
    declared = schema if schema is not None else works_for_schema()
    instruments = (
        profile if profile is not None else base_profile(*profile_type_refs, tenant_id=tenant_id)
    )
    table = (
        golden_candidates(
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            ontology_version="ontology-1",
            normalization_version="norm-1",
            with_decoys=False,
        )
        if isinstance(resolution_candidates, _Unset)
        else tuple(resolution_candidates)
    )
    decoys = (
        (decoy_universe() if with_decoys else ())
        if isinstance(extra_candidates, _Unset)
        else tuple(extra_candidates)
    )
    scheme = golden_vocabulary() if isinstance(vocabulary, _Unset) else vocabulary
    return ExecutionRequest(
        sentence=sentence,
        schema=declared,
        profile=instruments,
        extractors=extractors if extractors is not None else deterministic_extractors(),
        observed_at=observed_at,
        published_at=published_at,
        valid_from=valid_from,
        valid_to=valid_from if valid_to is None else valid_to,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        type_refs=type_refs if type_refs is not None else _default_type_refs(),
        extra_candidates=decoys,
        resolution_candidates=table,
        vocabulary=scheme,
        **{
            **(
                {"content_digest": digest128(canonical_material(sentence))}
                if overrides.get("capture") is None
                else {}
            ),
            "target_uri": f"urn:cognitive:golden:{digest128(canonical_material(sentence))}",
            **overrides,
        },
    )


def run_until(request: ExecutionRequest, stage: ExecutionStage | str) -> ExecutionResult:
    """Execute the path up to and including ``stage``, returning the real objects.

    The whole orchestrator is this function plus the step functions it calls: there
    is no state to configure and nothing to subclass, because the interesting
    question is "what does the platform actually produce at step N" and the answer
    should be a value rather than a re-implementation. Asking for an earlier stage is
    how a caller inspects an intermediate without running the rest, and the later
    fields are then ``None`` rather than pre-filled, so nothing can be read out of a
    stage that never ran.
    """
    wanted = ExecutionStage(stage)
    if wanted not in STAGE_ORDER:
        raise SemanticExecutionError("unknown_stage", f"{wanted!r} is not a pipeline stage")
    result = ExecutionResult(request=request)
    for reached_stage, step in _STEP_TABLE:
        result = step(result)
        if reached_stage is wanted:
            break
    return _finalise(result)


def run_golden_path(request: ExecutionRequest | None = None) -> ExecutionResult:
    """The full path: every stage, both lineage directions, the real aggregates."""
    return run_until(
        request if request is not None else golden_request(), ExecutionStage.WORLDLINE
    )


def backward_lineage(result: ExecutionResult) -> LineageTrace:
    """From the projected graph edge, back through claim, assertion, mention, segment.

    The subject is the ``GraphEdge``'s own ``edge_id``, which *is* the claim's
    ``relation_id`` - the projection mints no id - so walking from the edge is
    literally walking from the claim. The trace is
    :meth:`domain.evidence_lineage.EvidenceGraph.backward`'s, unmodified, including
    its ``complete`` flag and the name of the first unresolved hop when there is one
    (FR-031, FR-033).
    """
    return _lineage(result).backward


def forward_lineage(result: ExecutionResult) -> LineageTrace:
    """From the source, everything the chain produced, ending at the projected edge."""
    return _lineage(result).forward


def derived_from_observation(
    result: ExecutionResult, observation_id: str | None = None
) -> LineageTrace:
    """Everything derived from one observation, in chain order.

    :meth:`domain.evidence_lineage.EvidenceGraph.forward` starts at a *source*,
    because a source is the only node with nothing upstream of it - and an
    observation sits in the middle of the chain, so asking the primitive to start
    there reports ``capture`` as the first unresolved hop, which is a fact about
    direction rather than a defect. The full forward trace is therefore taken from
    the source and the suffix from the observation onward is returned: a projection
    of the primitive's output, not a second traversal, because no link is followed
    here. The subject is the observation, the hops are the primitive's, and
    ``complete`` is the primitive's own (FR-032).
    """
    bundle = _lineage(result)
    wanted = observation_id or bundle.observation.observation_id
    trace = bundle.forward
    start = next(
        (
            index
            for index, hop in enumerate(trace.hops)
            if hop.kind is HopKind.OBSERVATION and hop.node_id == wanted
        ),
        None,
    )
    if start is None:
        raise SemanticExecutionError(
            "observation_not_in_lineage",
            f"observation {wanted!r} is not on the forward chain from {bundle.source_id!r}",
        )
    return LineageTrace(
        subject_id=wanted,
        direction="forward",
        hops=trace.hops[start:],
        complete=trace.complete,
    )


def chain_to_observation(
    result: ExecutionResult, *, subject_side: bool = True
) -> tuple[str, ...]:
    """The architect's chain as ordered ids, each verified to be on a lineage trace.

    ``GraphEdge -> RelationClaim -> RelationCandidate -> TypeAssertion -> Mention ->
    Segment -> Observation``. Every id is read off a real object, and the membership
    check is what makes this a *report* rather than a claim: an id that is on no
    trace raises instead of being printed. Two links are proven by construction and
    are worth naming: the edge id and the claim id are the same string because the
    projection mints nothing, and the ``Segment``/``Observation`` pair is present
    because the capture hop was derived rather than skipped.
    """
    bundle = _lineage(result)
    assertion = bundle.type_assertions[0 if subject_side else -1]
    mention = _mention_citing(assertion, bundle.mentions)
    ordered = (
        bundle.edge_id,
        bundle.claim.relation_id,
        bundle.candidate.candidate_id,
        assertion.type_assertion_id,
        mention.mention_id,
        bundle.segment_id,
        bundle.observation.observation_id,
    )
    missing = [ref for ref in ordered if ref not in bundle.hop_ids]
    if missing:
        raise SemanticExecutionError(
            "chain_off_graph",
            f"ids {missing} are named by the chain but are on neither lineage trace",
        )
    return ordered


def _lineage(result: ExecutionResult) -> LineageBundle:
    """The lineage bundle, or a typed refusal naming what still has to run."""
    if result.lineage is None:
        raise SemanticExecutionError(
            "lineage_unavailable",
            "lineage needs the EDGE stage; reached "
            f"{result.reached or 'nothing'}",
        )
    return result.lineage


def _mention_citing(
    assertion: TypeAssertion, mentions: Sequence[MentionRecord]
) -> MentionRecord:
    """The registered mention an assertion's evidence names, or a typed refusal."""
    for ref in assertion.evidence_refs:
        for record in mentions:
            if record.mention_id == ref:
                return record
    raise SemanticExecutionError(
        "assertion_without_mention",
        f"type assertion {assertion.type_assertion_id!r} cites no registered mention",
    )


def _finalise(result: ExecutionResult) -> ExecutionResult:
    """Attach the lineage bundle once the projection exists; otherwise pass through."""
    if result.lineage is not None or result.edge is None or result.claim is None:
        return result
    if result.observation is None or result.regime is None or result.types is None:
        return result
    if result.mentions is None or result.candidate is None or result.resolution is None:
        return result
    return replace(result, lineage=_build_lineage(result))


def _build_lineage(result: ExecutionResult) -> LineageBundle:
    """Register every hop of the chain into one ``EvidenceGraph``, then read it.

    Registration, not traversal: this function injects the links and delegates both
    directions to the primitive. The chain is
    ``Source -> Capture -> Observation -> Segment -> Mention -> TypeAssertion ->
    Candidate -> Relation -> Entity``, which is ``EvidenceGraph``'s own forward order,
    and the two traces returned are whatever the primitive makes of these links.

    Each node is registered with both of its neighbours: the node it was derived
    *from* (which is how the forward walk finds it) and the node that derives it
    (which is how the backward walk finds it). A node with two parents - a claim
    rests on two typing claims, a typing claim rests on two mentions - is registered
    once per parent, so the traces branch where the data does rather than pretending
    the chain is a line.
    """
    observation = result.observation.observation
    claim = result.claim.claim
    candidate = result.candidate.proposed
    mentions = result.mentions.records
    graph = EvidenceGraph()
    tenant = observation.tenant_id
    capture = observation.capture
    if capture is not None:
        _link_node(
            graph,
            EvidenceHop(
                HopKind.SOURCE, observation.source_id, observation.source_family, tenant_id=tenant
            ),
            derived_from=("",),
            derives=(capture.capture_id,),
        )
        _link_node(
            graph,
            EvidenceHop(
                HopKind.CAPTURE,
                capture.capture_id,
                capture.hop_label,
                tenant_id=tenant,
            ),
            derived_from=(observation.source_id,),
            derives=(observation.observation_id,),
        )
    else:
        _link_node(
            graph,
            EvidenceHop(
                HopKind.SOURCE, observation.source_id, observation.source_family, tenant_id=tenant
            ),
            derived_from=("",),
            derives=(observation.observation_id,),
        )
    assertion_ids = tuple(assertion.type_assertion_id for assertion in result.types.assertions)
    mention_of = {
        assertion.type_assertion_id: _mention_citing(assertion, mentions)
        for assertion in result.types.assertions
    }

    _link_node(
        graph,
        EvidenceHop(
            HopKind.OBSERVATION,
            observation.observation_id,
            observation.document_id,
            relation_id=claim.relation_id,
            tenant_id=tenant,
        ),
        derived_from=(capture.capture_id,) if capture is not None else (observation.source_id,),
        derives=(observation.segment_id,),
    )
    _link_node(
        graph,
        EvidenceHop(
            HopKind.SEGMENT, observation.segment_id, observation.language, tenant_id=tenant
        ),
        derived_from=(observation.observation_id,),
        derives=tuple(record.mention_id for record in mentions),
    )
    for record in mentions:
        assertions = tuple(
            assertion_id
            for assertion_id, citing in mention_of.items()
            if citing.mention_id == record.mention_id
        )
        _link_node(
            graph,
            EvidenceHop(
                HopKind.MENTION, record.mention_id, record.value, tenant_id=tenant
            ),
            derived_from=(observation.segment_id,),
            derives=assertions,
        )
    for assertion in result.types.assertions:
        _link_node(
            graph,
            EvidenceHop(
                HopKind.ASSERTION,
                assertion.type_assertion_id,
                assertion.type_ref,
                tenant_id=tenant,
            ),
            derived_from=(candidate.candidate_id,),
            derives=(claim.relation_id,),
        )
    _link_node(
        graph,
        EvidenceHop(
            HopKind.CANDIDATE,
            candidate.candidate_id,
            candidate.relation_type,
            tenant_id=tenant,
        ),
        derived_from=(candidate.subject_mention_ref,),
        derives=(claim.relation_id,),
    )
    _link_node(
        graph,
        EvidenceHop(
            HopKind.RELATION, claim.relation_id, claim.relation_type, tenant_id=tenant
        ),
        derived_from=assertion_ids,
        derives=("",),
    )
    for ref in (result.resolution.subject_ref, result.resolution.object_ref):
        _link_node(
            graph,
            EvidenceHop(HopKind.ENTITY, ref, "resolved", tenant_id=tenant),
            derived_from=(claim.relation_id,),
            derives=("",),
        )

    backward = graph.backward(claim.relation_id)
    forward = graph.forward(observation.source_id)
    return LineageBundle(
        graph=graph,
        relation_id=claim.relation_id,
        edge_id=result.edge.edge.edge_id,
        claim=claim,
        candidate=candidate,
        type_assertions=result.types.assertions,
        mentions=mentions,
        segment_id=observation.segment_id,
        capture_id=capture.capture_id if capture is not None else "",
        source_id=observation.source_id,
        observation=observation,
        backward=backward,
        forward=forward,
    )


def _link_node(
    graph: EvidenceGraph,
    hop: EvidenceHop,
    *,
    derived_from: Sequence[str],
    derives: Sequence[str],
) -> None:
    """Register one chain node against both of its neighbours, once per pairing.

    ``EvidenceGraph.add_hop`` names one neighbour pair per call, and a node in the
    middle of a chain needs both readings: the forward walk indexes by the node a hop
    was derived *from*, the backward walk by the node it derives. Registering the
    cross product means a node with two parents is reachable by either, and the
    traces branch where the evidence branches. ``""`` is how an end of the chain
    says so - the source has nothing before it and the relation has nothing after it,
    and ``add_hop`` ignores an empty endpoint, so neither end dangles.

    Registration is idempotent: ``add_hop`` drops a repeated identical link, so a
    replayed build cannot inflate a trace (I-11).
    """
    for parent in derived_from:
        for child in derives:
            graph.add_hop(hop, forward=parent, backward=child)


def regime_verdicts_for(batch: ResolutionBatch) -> Mapping[str, str]:
    """Every candidate's regime-comparison verdict in ``batch``, keyed by candidate ref.

    Read off the machine's own recorded
    :class:`~semantic.resolution.CompatibilityReason` values rather than recomputed, over
    ``reasons`` and ``blocked_out`` alike so a candidate another layer pruned still has its
    regime verdict reported. Where one candidate was compared against more than one mention
    the codes agree by construction - they are the same candidate under the same regime -
    and the address is the tiebreak that makes the mapping deterministic if they ever did
    not (constitution VI).

    Module-level rather than only a property because a caller holding a
    :class:`~semantic.resolution.ResolutionBatch` from somewhere other than this path
    should be able to ask the same question without importing the orchestrator.
    """
    verdicts: dict[str, str] = {}
    for decision in batch.decisions:
        for reason in (*decision.reasons, *decision.blocked_out):
            if reason.code in REGIME_REASON_CODES and reason.candidate_ref:
                verdicts[reason.candidate_ref] = reason.code
    return MappingProxyType(dict(sorted(verdicts.items())))


def _observation_step(result: ExecutionResult) -> ExecutionResult:
    """Step 1 - build the raw record and address it by its own content."""
    request = result.request
    observation = Observation(
        tenant_id=request.tenant_id,
        investigation_id=request.investigation_id,
        source_id=request.source_id,
        source_family=request.source_family,
        independence_group=request.independence_group,
        document_id=request.document_id,
        segment_id=request.segment_id,
        text=request.sentence,
        language=request.language,
        observed_at=request.observed_at,
        published_at=request.published_at,
        extraction_version=request.extraction_version(),
        normalization_version=request.normalization_version,
        ontology_version="",
        capture=_acquisition_capture(result),
    )
    return replace(
        result, observation=ObservationStep(observation), reached=ExecutionStage.OBSERVATION
    )


def _acquisition_capture(result: ExecutionResult) -> Capture | None:
    """The real acquisition record for this observation, or ``None`` when none was fetched.

    Built through the shared stream seam rather than from a derived address, so the
    ``Capture`` in the lineage is the same object a store would hold: it carries a
    content digest, a target, a fetch basis and a fetch time that may be *absent* on
    purpose. A crawl index cannot tell us when it fetched a document, only when it
    indexed it, and saying so with :attr:`CaptureTimeBasis.INDEX_OBSERVATION` is a fact;
    the address this function replaces pretended otherwise.

    ``None`` is returned when the request carries no acquisition record, and the lineage
    then reports the capture hop as missing. That is the honest outcome and it is
    visible.
    """
    request = result.request
    if request.capture is not None:
        return request.capture
    if request.content_digest is None or not request.target_uri:
        return None
    return Capture(
        tenant_id=request.tenant_id,
        source_id=request.source_id,
        source_family=request.source_family,
        target_uri=request.target_uri,
        content_digest=request.content_digest,
        media_type=request.media_type,
        fetched_at=None,
        time_basis=CaptureTimeBasis.INDEX_OBSERVATION,
        transport=request.transport,
        recorded_by=request.recorded_by,
    )


def _context_step(result: ExecutionResult) -> ExecutionResult:
    """Step 2 - build the immutable evidence frame and register it in a resolver."""
    observation = result.observation.observation
    frame = EvidenceContext(
        tenant_id=observation.tenant_id,
        investigation_id=observation.investigation_id,
        observation_id=observation.observation_id,
        source_id=observation.source_id,
        document_id=observation.document_id,
        segment_id=observation.segment_id,
        observed_at=observation.observed_at,
        published_at=observation.published_at,
        source_family=observation.source_family,
        independence_group=observation.independence_group,
        language=observation.language,
        extraction_version=observation.extraction_version,
        normalization_version=observation.normalization_version,
        ontology_version=observation.ontology_version,
        completeness=ContextCompleteness.COMPLETE,
        trust_state=ContextTrustState.ATTESTED,
    )
    resolver = InMemoryContextResolver([frame])
    return replace(
        result,
        context=ContextStep(frame=frame, resolver=resolver),
        reached=ExecutionStage.CONTEXT,
    )


def _mentions_step(result: ExecutionResult) -> ExecutionResult:
    """Step 3 - drive the real extractor registry and address everything it returns.

    ``DeterministicExtractorSet.extract`` is called with the observation's segment ref
    and language; its ``TypedMention`` values become
    :class:`extractors.registry.Mention` records - the fan-out's own output type - and
    are addressed by :func:`mention_id_for`. Every kind the set returns is kept: the
    ontology gate is gone, so nothing here filters down to the two kinds this relation
    needs and nothing drops an unfamiliar one (FR-002).

    **The step builds the :class:`~domain.mention_occurrence_index.MentionOccurrenceIndex`
    over what it found and hands it forward**, which is the production use of the one
    ``MN-`` minter: the records are registered as occurrences, their ids are minted by the
    index, and a producer's deferred address is resolved against this same object rather
    than against a second table built somewhere else. The index needs the retrieval, and
    the request's :attr:`ExecutionRequest.capture` is the only real one there is - so a
    request built without a capture leaves :attr:`MentionStep.index` at ``None`` and says
    so, rather than minting ids under an invented scope.
    """
    request = result.request
    observation = result.observation.observation
    found = request.extractors.extract(
        request.sentence, segment_ref=observation.segment_id, lang=observation.language
    )
    readings = extract_relational_readings(
        request.sentence,
        lang_hint=observation.language,
        observation_refs=(observation.observation_id,),
    )
    capture = _acquisition_capture(result)
    capture_ref = capture.capture_id if capture is not None else ""
    mentions: list[Mention] = []
    records: list[MentionRecord] = []
    hints: list[SemanticHint | None] = []
    for typed in found:
        mention = Mention(
            kind=typed.kind,
            value=typed.value,
            offset=typed.offset,
            confidence=typed.confidence,
            attrs={
                "extractor": typed.extractor or "unknown",
                "source": typed.source,
                "lang": observation.language,
                "segment_ref": observation.segment_id,
                "end_offset": str(typed.end_offset),
            },
        )
        records.append(
            MentionRecord(
                mention_id=mention_id_for(
                    capture_ref,
                    observation.segment_id,
                    typed.kind,
                    typed.value,
                    typed.offset,
                    typed.end_offset,
                    typed.extractor,
                ),
                segment_ref=observation.segment_id,
                mention=mention,
                start=typed.offset,
                end=typed.end_offset,
            )
        )
        hint = request.extractors.hint(typed.kind)
        if hint is not None:
            mention.attrs["semantic_hint"] = hint.flag
        mentions.append(mention)
        hints.append(hint)
    index = _occurrence_index(capture_ref, observation.segment_id, records)
    return replace(
        result,
        mentions=MentionStep(
            mentions=tuple(mentions),
            records=tuple(records),
            subject=_select(records, request.subject_kind, "subject"),
            obj=_select(records, request.object_kind, "object"),
            hints=tuple(hints),
            reading=readings[0] if readings else None,
            index=index,
        ),
        reached=ExecutionStage.MENTIONS,
    )


def _occurrence_index(
    capture_ref: str, segment_ref: str, records: Sequence[MentionRecord]
) -> MentionOccurrenceIndex | None:
    """The index over ``records``, or ``None`` when the run named no retrieval.

    Two things are decided here rather than at each call site. **The extractor ref** is the set's
    own version, because the scope's fifth key is *which instrument read this* and every record on
    this step came from one set; a per-record extractor name would give each mention its own index
    and turn the index into a lookup that always misses. **The refusal** is on a blank
    ``capture_ref``: an index's scope is three of the five keys a mention id is minted from, and a
    placeholder scope would mint ids that cannot say which retrieval produced them - the collision
    the capture key was added to prevent, arriving by another route (FR-018).
    """
    if not capture_ref.strip():
        return None
    return MentionOccurrenceIndex(
        capture_ref=capture_ref,
        segment_ref=segment_ref,
        extractor_ref=EXTRACTOR_SET_SCOPE_REF,
        occurrences=[
            MentionOccurrence(
                kind=record.kind,
                surface=record.value,
                start=record.start,
                end=record.end,
            )
            for record in records
        ],
    )


def _select(records: Sequence[MentionRecord], kind: str, role: str) -> MentionRecord:
    """The first mention of ``kind``, or a typed refusal naming what *was* found.

    "First" is the extractor's own canonical ``(offset, kind, value)`` order, so the
    choice is deterministic. Two mentions of one kind is a real ambiguity the platform
    would resolve elsewhere; this path reports it rather than picking silently, and
    widening the query is the caller's job.
    """
    matching = tuple(record for record in records if record.kind == kind)
    if not matching:
        raise SemanticExecutionError(
            "no_mention_of_kind",
            f"no {kind!r} mention in the segment for the {role!r} end; the extractors "
            f"returned kinds {sorted({record.kind for record in records})}",
        )
    return matching[0]


def _regime_step(result: ExecutionResult) -> ExecutionResult:
    """Step 4 - resolve the profile, bind the regime, **persist it, read it back**, extend.

    ``ProfileRegistry.resolve`` performs the inheritance walk (memoised, cycle-safe)
    and ``SemanticRegime.from_profile`` binds the result as a separate
    content-addressed value that *points at* the frame. ``extend_context`` then returns
    a **new** frame carrying the regime's pinned ``ontology_version`` and language; the
    base frame is untouched and keeps its id, so nothing already referring to it stops
    resolving (FR-014, FR-018).

    It runs before resolution so the mention can carry a real ``regime_id`` into the
    resolver's context layer, which would otherwise have to record ``UNEVALUATED`` for
    every candidate and never make the comparison SC-9 asks it to make.

    **The regime is now written down, and then read back (D6, FR-014).** This is the
    single change that removes a permanent ``regime_unevaluated`` from the golden path,
    and it is deliberately two operations rather than one. The regime is serialised to a
    :class:`~semantic.regime_store.RegimeRecord`, written through the store, and
    *rehydrated from what the store returned*; every value the rest of the path uses -
    the regime itself and the frame extended by it - is derived from the read-back value
    rather than from the local one. So the path proves its regime survives storage
    before it is allowed to compare anything under it, and :meth:`RegimeRecord.to_regime`
    makes the machine re-verify the address on the way back. A regime that failed to
    round trip raises here, where the cause is obvious, instead of producing a decision
    that claims an interpretation nobody can read (FR-004, FR-014).

    The store is the caller's if one was supplied and a fresh
    :class:`~semantic.regime_store.InMemoryRegimeStore` otherwise, and it is exposed on
    :attr:`RegimeStep.store` so a second run can be handed the same one. Ingestion is
    idempotent on the regime's content address, so running this path twice against one
    store writes one record - which is what keeps a re-run byte-identical (I-11, FR-022).
    """
    request = result.request
    observation = result.observation.observation
    base_frame = result.context.frame
    registry = ProfileRegistry(tenant_id=request.tenant_id)
    registry.register(request.profile)
    resolution = registry.resolve(request.profile.profile_id, request.profile.version)
    bound = SemanticRegime.from_profile(
        resolution,
        context_ref=base_frame.context_id,
        ontology_version=request.ontology_version,
        validation_profile=request.validation_profile,
        language=observation.language,
        note=f"golden path over {observation.segment_id}",
        recorded_at=observation.observed_at,
    ).promoted(SemanticCommitment.TYPED)
    store = request.regime_store if request.regime_store is not None else InMemoryRegimeStore()
    store.ingest_regime(bound)
    stored = store.regime_for(request.tenant_id, bound.regime_id)
    if stored is None:
        raise SemanticExecutionError(
            "regime_unresolved",
            f"the regime {bound.regime_id!r} was written to storage and read back as absent; "
            "a store that does not return what it was just given is a broken store, and no "
            "substitute regime is used in its place (FR-016)",
        )
    regime = stored.to_regime()
    frame = extend_context(base_frame, regime)
    result.context.resolver.register(frame)
    return replace(
        result,
        regime=RegimeStep(
            resolution=resolution,
            regime=regime,
            base_frame=base_frame,
            frame=frame,
            record=stored,
            store=store,
        ),
        reached=ExecutionStage.REGIME,
    )


def _stored_regime(result: ExecutionResult) -> RegimeResolution:
    """The regime for this run, **read back from storage**, or a stated reason it is not there.

    This is the read that makes FR-015 an execution rather than a report, and it is a
    *second* read rather than a reuse of what step 4 held: step 4 wrote a regime and
    proved it round-tripped, and this step asks the store again as a separate consumer
    would. A path that compared under the value it had just built would satisfy the
    letter of "the regime exists" while never consulting the store, which is the shape of
    the defect D6 describes.

    Three outcomes, and only three:

    * the store returns the record - ``RESOLVED``, carrying it;
    * the store raises a cross-tenant refusal - that travels **unchanged**, as a
      component's own refusal always does, because "you may not read that" is a fact
      about the boundary and not this module's inference (constitution IV);
    * the store returns nothing for a real address - ``UNRESOLVED``, carrying the reason
      and *nothing else*. :meth:`RegimeResolution.as_record` turns that into the
      ``regime_unresolved`` refusal, so the exceptional path is a stated error with a
      count on the store rather than a comparison run under a regime nobody wrote down
      (FR-015, FR-016).
    """
    step = result.regime
    if step is None:
        raise SemanticExecutionError(
            "regime_unavailable",
            f"resolution needs the REGIME stage to have stored a regime; reached "
            f"{result.reached or 'nothing'}",
        )
    record = step.store.regime_for(result.request.tenant_id, step.record.regime_id)
    resolution = RegimeResolution(
        regime_id=step.record.regime_id,
        tenant_id=result.request.tenant_id,
        context_ref=step.regime.context_ref,
        verdict=RegimeVerdict.RESOLVED if record is not None else RegimeVerdict.UNRESOLVED,
        record=record,
        reason=(
            ""
            if record is not None
            else (
                f"the store holds no record under this address for tenant "
                f"{result.request.tenant_id!r} after {step.store.unresolved_reads()} "
                f"unresolved read(s); the regime was written at step 4 and is not there now"
            )
        ),
    )
    return resolution


def _resolution_step(result: ExecutionResult) -> ExecutionResult:
    """Step 5 - run the real mention-to-entity machine over this segment's mentions.

    This is the step that replaced ``entity_ref_for``. Everything the resolver needs is a
    request field or an already-reached object:

    * the mentions come from step 3, each projected into a
      :class:`semantic.resolution.ResolutionMention` carrying the frame, the window, the
      provenance and the regime id;
    * the candidate universe is ``resolution_candidates`` plus any ``extra_candidates``
      the caller added, so the platform resolves against a *table* rather than against a
      copy of itself;
    * the vocabulary, when supplied, is wrapped in a real
      :class:`semantic.registry.SemanticRegistry` so alias expansion goes through the
      facade and swapping the backend stays free (FR-015);
    * the operator is derived from the same ``RelationSchema`` by
      :func:`semantic.operators.default_operator_for_schema`, and handed forward to step 7
      so blocking and extraction share one contract rather than two derivations of it.

    **The orchestrator's own contribution is honesty, not a fallback.** Every mention in
    the segment is resolved - not only the two this relation needs - and the verdicts are
    carried on the step. Nothing here picks between ambiguous candidates, and nothing here
    invents an entity for a mention that matched nothing: :func:`_require_resolved` is
    where that refusal lives, and it names the mention and the reasons.

    **The regime is read back here, and bound to both sides of the comparison (FR-015,
    FR-016).** :func:`_stored_regime` asks the store for the regime this run depends on and
    refuses with ``regime_unresolved`` if it is not there; the address it returns is then
    handed to *both* :func:`_resolution_mentions` and :func:`_resolution_universe`. That
    both-sides part is what removes the permanent ``regime_unevaluated``: the resolver's
    context layer compares the mention's regime against the candidate's, so a regime on one
    side alone is an unevaluated comparison no matter how durable the regime itself is.
    :attr:`ResolutionStep.regime_verdicts` then reports what the comparison concluded, per
    candidate, so the fix is observable rather than asserted.
    """
    request = result.request
    operator = default_operator_for_schema(request.schema)
    registry = _registry_for(request)
    resolver = MentionResolver(
        registry=registry,
        operator=operator,
        collective_max_iterations=request.collective_max_iterations,
    )
    scope = request.resolution_scope or resolution_scope_for(
        request.tenant_id, request.investigation_id
    )
    regime = _stored_regime(result)
    regime_record = regime.as_record()
    batch = resolver.resolve(
        _resolution_mentions(result, regime_record.regime_id),
        _resolution_universe(result, regime_record.regime_id),
        scope,
    )
    subject = batch.decision_for(result.mentions.subject.mention_id)
    obj = batch.decision_for(result.mentions.obj.mention_id)
    if subject is None or obj is None:
        raise SemanticExecutionError(
            "resolution_missing_decision",
            "the resolver returned no decision for "
            f"{result.mentions.subject.mention_id!r} or {result.mentions.obj.mention_id!r}; "
            "a decision per mention is the resolver's contract",
        )
    return replace(
        result,
        resolution=ResolutionStep(
            resolver=resolver,
            batch=batch,
            scope=batch.scope,
            operator=operator,
            subject_decision=subject,
            object_decision=obj,
            regime=regime_record,
            store=result.regime.store,
        ),
        reached=ExecutionStage.RESOLUTION,
    )


def _registry_for(request: ExecutionRequest) -> SemanticRegistry | None:
    """The vocabulary facade the resolver widens names through, or ``None`` for no vocabulary.

    A request that supplies ``registry`` gets exactly that one - so a caller can wire a
    different backend, or two, and no calling code changes (FR-015, SC-7). Otherwise a supplied
    ``vocabulary`` scheme is wrapped in a real :class:`semantic.registry.SemanticRegistry` here,
    which is the one-call case. A caller supplies a *scheme* by default because a scheme is a
    value and a registry is *wiring*, and a request should not have to know which it is.
    """
    if request.registry is not None:
        return request.registry
    if request.vocabulary is None:
        return None
    return SemanticRegistry(
        tenant_id=request.tenant_id,
        backends=(
            ConceptSchemeBackend(request.vocabulary, tenant_id=request.tenant_id),
        ),
    )


def _resolution_mentions(
    result: ExecutionResult, regime_id: str
) -> tuple[ResolutionMention, ...]:
    """Every mention of the segment, as the resolver's own mention shape.

    All of them, not just the two ends this relation uses: resolution is a property of
    the segment, and narrowing the batch to the relation's own needs is exactly the
    pre-filtering that would let a third mention's evidence go unseen (FR-001).

    ``regime_id`` is a parameter and is not read off ``result.regime`` on purpose. The
    caller has already fetched that address back from storage and is passing the address
    it actually compared under, so a mention cannot quietly end up carrying the in-memory
    regime while the candidate universe carries the stored one (FR-015).
    """
    request = result.request
    observation = result.observation.observation
    roles = {request.subject_kind: RelationRole.SUBJECT, request.object_kind: RelationRole.OBJECT}
    return tuple(
        ResolutionMention(
            mention_id=record.mention_id,
            surface=record.value,
            kind=record.kind,
            role=roles.get(record.kind, RelationRole.OBJECT),
            tenant_id=request.tenant_id,
            investigation_id=request.investigation_id,
            source_id=request.source_id,
            source_family=request.source_family,
            independence_group=request.independence_group,
            valid_from=request.valid_from,
            valid_to=request.valid_to,
            observed_at=observation.observed_at,
            profile_id=request.profile.profile_id,
            profile_version=request.profile.version,
            ontology_version=request.ontology_version,
            normalization_version=request.normalization_version,
            regime_id=regime_id,
            declared_type_refs=(request.type_refs[record.kind],)
            if record.kind in request.type_refs
            else (),
        )
        for record in sorted(result.mentions.records, key=lambda item: item.mention_id)
    )


def _universe_under_regime(
    universe: tuple[ResolutionCandidate, ...], regime_id: str
) -> tuple[ResolutionCandidate, ...]:
    """The entity table as this run reads it: every record bound to the stored regime.

    **This is the other half of the fix, and the half that is easy to get wrong.** A regime
    is a property of a *reading*, not of a record -
    :class:`~semantic.regime.SemanticRegime` answers "what did we believe when we read
    that?" and never "what may exist". So binding the active regime to a record that names
    none states the truth about this run: the platform read that record now, under these
    instruments, and the decision it produces carries the address so the claim is
    reconstructable. It is a projection, not an invention - every other field of the
    candidate is carried across untouched.

    The asymmetry with a record that *does* name a regime is the load-bearing part. Such a
    record keeps its own, so a record read earlier under different instruments produces
    ``regime_mismatch`` - a graded ``WEAKENED`` with a stated detail - rather than being
    flattened into a pass by having its regime overwritten. Overwriting would make the
    comparison agree by construction, which is precisely the "proceed as though it matched"
    that FR-016 forbids, arrived at by a different road.

    Nothing here invents a regime: ``regime_id`` arrives as an argument from storage, and a
    caller with no stored regime never reaches this function (see :func:`_stored_regime`).
    """
    return tuple(
        candidate if candidate.regime_id else replace(candidate, regime_id=regime_id)
        for candidate in universe
    )


def _resolution_universe(
    result: ExecutionResult, regime_id: str
) -> tuple[ResolutionCandidate, ...]:
    """The candidate universe: the entity table plus anything the caller appended.

    The caller's ``extra_candidates`` arrive in the older :class:`semantic.blocking.Candidate`
    shape and are projected rather than reinterpreted, so a caller who already has a universe
    does not have to learn a second one. De-duplication is the resolver's job, not this
    function's, and it is deterministic there.

    Every record in the result is then read under the stored regime, by
    :func:`_universe_under_regime`. That last step is what makes the resolver's regime
    comparison resolvable rather than ``UNEVALUATED`` on every run: the context layer
    compares the mention's ``regime_id`` with the candidate's, so a durable regime on one
    side alone still yields no comparison (FR-015, D6).
    """
    request = result.request
    projected = tuple(
        resolution_candidate_for(
            candidate,
            tenant_id=request.tenant_id,
            investigation_id=request.investigation_id,
            ontology_version=request.ontology_version,
            normalization_version=request.normalization_version,
        )
        for candidate in request.extra_candidates
    )
    return _universe_under_regime(
        (*request.resolution_candidates, *projected), regime_id
    )


def _types_step(result: ExecutionResult) -> ExecutionResult:
    """Step 6 - assert the observed typing of each relation end, with no gate.

    One :class:`semantic.contracts.TypeAssertion` per end at ``TypeScope.OBSERVED`` /
    ``SemanticStatus.OBSERVED``, carrying the surface it was read from, the extractor
    that read it, the frame it was read under, and the observation, segment and mention as
    evidence. The type reference comes from the request and is recorded verbatim: nothing
    here checks it against a profile, a pack or a vocabulary, because an unknown type is a
    first-class value (FR-001, FR-003).

    ``entity_ref`` is the **resolved** entity from step 5, read off that end's
    :class:`semantic.resolution.ResolutionDecision`. That is the whole reason resolution
    runs before typing: a type asserted about a mention-derived identifier is a type
    about nothing, and the validator keys its domain/range check by entity - so the two
    would have had to agree by coincidence.
    """
    request = result.request
    observation = result.observation.observation
    mentions = result.mentions
    frame = result.context.frame
    by_entity: dict[str, list[TypeAssertion]] = {}

    def build(record: MentionRecord, kind: str, entity_ref: str) -> TypeAssertion:
        type_ref = request.type_refs.get(kind, "")
        assertion = TypeAssertion(
            tenant_id=request.tenant_id,
            entity_ref=entity_ref,
            type_ref=type_ref,
            type_scheme=_scheme_for(type_ref),
            scope=TypeScope.OBSERVED,
            status=SemanticStatus.OBSERVED,
            raw_surface=record.value,
            source_ref=observation.observation_id,
            extractor_ref=record.mention.attrs.get("extractor", ""),
            context_ref=frame.context_id,
            evidence_refs=(
                observation.observation_id,
                observation.segment_id,
                record.mention_id,
            ),
            observed_at=observation.observed_at,
        ).with_id()
        by_entity.setdefault(assertion.entity_ref, []).append(assertion)
        return assertion

    subject_ref = _require_resolved(result, mentions.subject, "subject")
    object_ref = _require_resolved(result, mentions.obj, "object")
    subject = build(mentions.subject, request.subject_kind, subject_ref)
    obj = build(mentions.obj, request.object_kind, object_ref)
    return replace(
        result,
        types=TypeStep(
            assertions=(subject, obj),
            subject=subject,
            obj=obj,
            by_entity=MappingProxyType(
                {ref: tuple(items) for ref, items in sorted(by_entity.items())}
            ),
        ),
        reached=ExecutionStage.TYPES,
    )


def _require_resolved(
    result: ExecutionResult, record: MentionRecord, role: str
) -> str:
    """The entity this end resolved to, or a typed refusal that says exactly why not.

    This is the honest handling of ``AMBIGUOUS`` and ``UNRESOLVED`` that the previous
    shape of this module could not express. The old path minted an ``ENT-`` from the
    mention and carried on, which is not a weaker answer - it is a *false* one, because it
    asserted an identity no evidence supported and then let a claim, an edge and a worldline
    event be built on it. Here the path stops, and the refusal carries:

    * the mention and the surface, so the reader knows which reading failed;
    * the verdict, so ``ambiguous`` is distinguishable from ``unresolved``;
    * both surviving candidates for an ambiguity, because a refusal that hid the two
      candidates would be no more useful than a guess;
    * the recorded compatibility reason codes, so the cause is one attribute access away;
    * the decision's own id, so the failed resolution is still a durable, citable fact.

    Everything up to this point is already on the result, so
    ``run_until(request, ExecutionStage.RESOLUTION)`` succeeds and the decision is
    inspectable without ever reaching the claim.
    """
    step = result.resolution
    if step is None:
        raise SemanticExecutionError(
            "resolution_unavailable",
            f"the {role!r} end needs the RESOLUTION stage; reached {result.reached or 'nothing'}",
        )
    decision = step.batch.decision_for(record.mention_id)
    if decision is None:
        raise SemanticExecutionError(
            "resolution_missing_decision",
            f"the resolver returned no decision for the {role!r} mention {record.mention_id!r}",
        )
    if decision.logical_entity_ref:
        return decision.logical_entity_ref
    detail = (
        f"the {role!r} end is a participant of a claim, and a participant must be identified. "
        f"Mention {record.mention_id!r} (surface {record.value!r}) resolved "
        f"{str(decision.verdict)!r}"
    )
    if decision.verdict is ResolutionVerdict.AMBIGUOUS:
        detail += (
            f" between {len(decision.ambiguous_candidates())} equally supported candidates "
            f"{list(decision.ambiguous_candidates())}; the path will not pick one"
        )
    elif decision.verdict is ResolutionVerdict.CONFLICTED:
        detail += f"; the winning candidate is contested by {list(decision.collective.contested)}"
    else:
        detail += "; nothing in the candidate universe matched it"
    detail += (
        f". Reasons: {list(decision.reason_codes())}. Decision "
        f"{decision.resolution_decision_id}. Admit the entity separately, widen the "
        "universe, or supply more evidence - this path does not substitute a synthetic "
        "entity reference."
    )
    raise SemanticExecutionError(
        f"{role}_end_{decision.verdict!s}",
        detail,
    )


def _measured_trigger(result: ExecutionResult, segment_ref: str) -> SpanRef:
    """The cue span the extractor actually measured, or the honest fallback.

    This used to be ``min(subject.end, object.start) … max(...)`` — the region
    *between* the two mentions, which is a guess dressed as a measurement. For
    ``John Smith became CEO of Acme`` it yields ``[10, 25)``, and that span swallows
    ``"became "``. The relational reader measures the cue instead: ``[18, 24)`` is
    exactly ``"CEO of"``.

    The fallback is the old guess, and it is reached only when the extraction layer
    reported no reading at all. It is kept because a sentence with no cue still has to
    produce a candidate, but the two are no longer silently the same thing: one is what
    was found, the other is what was assumed, and only the first is used when both
    exist.
    """
    reading = result.mentions.reading
    if reading is not None and reading.trigger_span is not None:
        return reading.trigger_span.into(segment_ref)
    mentions = result.mentions
    return SpanRef(
        segment_ref=segment_ref,
        start=min(mentions.subject.end, mentions.obj.start),
        end=max(mentions.subject.end, mentions.obj.start),
    )


def _reading_extractor_version(result: ExecutionResult, fallback: str) -> str:
    """The version of whichever extractor actually produced the reading.

    The reading names its own extractor, and a candidate that attributed itself to the
    observation's extraction version while being produced by a different extractor would
    make the version field a decoration rather than provenance. The fallback is the
    honest answer when no reading exists.
    """
    reading = result.mentions.reading
    if reading is not None and reading.extractor_version:
        return reading.extractor_version
    return fallback


def _signal_step(result: ExecutionResult) -> ExecutionResult:
    """Step 6b - turn the request's declaration and the producers' findings into candidates.

    Feature 019, T034. This is where the orchestrator stops constructing candidates by hand.

    **The declaration is a signal, and that is the load-bearing decision.** Before this,
    :func:`_candidate_step` built a :class:`~domain.relation_candidate.RelationCandidate`
    field by field from the request, which meant the relation the caller asked about was
    never *evidence* for anything - it was an instruction. It is now a
    :attr:`~extractors.signals.signal.SignalKind.SCHEMA` signal over the real mention ids,
    assembled alongside whatever the producers observed. Two consequences, both of them the
    point:

    * The caller's declaration and a producer's observation are the same kind of thing, so
      they aggregate, corroborate or conflict through one code path instead of a declared
      candidate and a discovered one arriving by different routes.
    * The declared signal's ``trigger_span`` and temporal hypothesis travel as
      ``extra``, so the span and the window the caller supplied reach the assembled
      candidate through the assembler rather than around it. That is also the only reason
      this can be done without losing them: the assembler builds a candidate from
      :class:`~domain.relation_candidate.RelationCandidate`'s defaults for anything a signal
      does not carry.

    **Producers run over the observation's text and their endpoints are NOT remapped to
    mention ids.** A producer addresses its ends as surfaces, because it sits below the
    mention layer; remapping them here would be the orchestrator inventing mention identity
    from a string match, which is resolution with no ``ResolutionDecisionRecord`` behind it.
    A discovered signal therefore produces a candidate over surface addresses, and it is
    *not* the candidate this path continues with. It is kept, counted and reported, and the
    reconciliation of surface addresses to mention ids is a later layer's job with somewhere
    to record the decision.

    :attr:`SignalStep.declared` is what :func:`_candidate_step` reads. If no producer ran,
    this stage still produces a candidate, from the declaration alone - which is the
    behaviour the path had before and the one a caller asserting a relation explicitly
    should keep getting.
    """
    request = result.request
    mentions = result.mentions
    # The regime the regime step actually derived, not a placeholder. Before this stage
    # moved after REGIME it had to name an "uncommitted" regime because the real one did
    # not exist yet, and a placeholder that satisfies the type is indistinguishable from a
    # real value in every downstream read - which is the opposite of what FR-014 wants.
    frame = result.regime.frame
    regime_ref = result.regime.record.regime_id
    # The retrieval, when the request supplied one. Empty rather than the observation's
    # ``source_id`` when it did not: a source is a publisher and a capture is a retrieval,
    # and a signal's ``capture_ref`` has to be resolvable against something somebody
    # actually fetched (I-3). A blank says "no retrieval was named", which is the truth for
    # a request built without one.
    capture = request.capture
    document_ref = capture.capture_id if capture is not None else ""
    scope = ExtractionScope(
        tenant_id=request.tenant_id,
        context_ref=frame.context_id,
        semantic_regime_ref=regime_ref,
        document_ref=document_ref,
        investigation_id=request.investigation_id,
        recorded_by=request.recorded_by,
    )

    declared = RelationSignal(
        # The native participant path (Phase 4B), and the two ends are **real mention ids**
        # here - `result.mentions.subject.mention_id` is whatever
        # :func:`mention_id_for` minted for the mention the mention layer found. This is the
        # one construction site on this path that is not a producer: the orchestrator is
        # holding a mention record, not a surface, so there is nothing deferred about it and
        # nothing to resolve later.
        participants=(
            RelationParticipant(
                mention_ref=mentions.subject.mention_id,
                slot=ArgumentSlot(0),
                # The request's own role names, which are the *caller's* declaration and not
                # this module's reading. They are the role_hypothesis - evidence, and never
                # identity material (FR-009).
                role_hypothesis=request.role_names[0] if request.role_names else "",
                ordinal=0,
                confidence=1.0,
            ),
            RelationParticipant(
                mention_ref=mentions.obj.mention_id,
                slot=ArgumentSlot(1),
                role_hypothesis=request.role_names[1] if len(request.role_names) > 1 else "",
                ordinal=1,
                confidence=1.0,
            ),
        ),
        kind=SignalKind.SCHEMA,
        # The relation's own words as the caller stated them, which for a declared
        # hypothesis is the operator's name. Unlike a producer's surface, this one *is* a
        # type the platform holds, so the ref is set - the declaration is a typed claim and
        # pretending otherwise would lose the only part of it that is unambiguous.
        relation_surface=request.relation_type,
        relation_ref=RelationRef(request.relation_type, request.schema.schema_version),
        # `attribute_key` and not `predicate_text`, and the choice is the same one every
        # producer in the package makes: a declaration is a key the caller asserted beside a
        # value, not a phrase the document contained between two mentions. Nothing was read
        # here - `Neighbourhood.characters_scanned` is 0 and says so - and a basis of
        # `predicate_text` on a signal that read no predicate words would be a record
        # claiming an observation this stage did not make.
        basis=SignalBasis.ATTRIBUTE_KEY,
        # Stated, not defaulted. The caller declared a relation; nothing in the request says
        # the document denied it, and a denial this stage cannot see must not be invented.
        # Phase 4C deleted `SignalKind.NEGATION`, so this is the only place a signal can be
        # denied - which is what makes it the one place here the polarity has to be set by
        # hand rather than left to a kind the producer would have chosen.
        polarity=Polarity.ASSERTED,
        neighbourhood=Neighbourhood(
            characters_scanned=0,
            pairs_considered=0,
            scope_read=(
                "nothing was read: this signal is the caller's declaration that the "
                "observation asserts this relation, not a producer's reading of a document"
            ),
            precision="declared",
        ),
        direction=DirectionHypothesis.SUBJECT_TO_OBJECT,
        producer_ref=request.declared_by or "request/declaration",
        # The operator's identity from the *request's* schema, not from
        # ``result.resolution.operator``: this stage runs before resolution, because a
        # producer needs mentions and a frame but not a resolved participant. Reading the
        # operator off the resolution step would have made the stage order a lie about its
        # own dependencies.
        producer_version=request.schema.relation_type,
        context_ref=frame.context_id,
        semantic_regime_ref=regime_ref,
        capture_ref=document_ref,
        stated_axes=(TemporalAxis.OBSERVED_AT,),
        producer_confidence=1.0,
        tenant_id=request.tenant_id,
        notes="declared by the caller, not observed by a producer",
        extra={
            "declared": True,
            "arity_mode": str(request.schema.arity_mode),
            # Plain tuples, not RelationRoleBinding objects, and the reason is
            # serialisability: a signal's ``extra`` is carried into ``to_dict`` and into the
            # durable row, and a frozen dataclass does not belong in either. The assembler
            # rebuilds the typed bindings from these on the way into the candidate, so the
            # type discipline lands where the field is typed rather than in transit.
            "role_bindings": (
                (request.role_names[0], mentions.subject.mention_id,
                 request.type_refs.get(request.subject_kind, "")),
                (request.role_names[1], mentions.obj.mention_id,
                 request.type_refs.get(request.object_kind, "")),
            ),
            "trigger_span": _span_to_dict(result),
            "temporal_semantics": str(request.schema.temporal_semantics),
        },
    )

    discovered: tuple[RelationSignal, ...] = ()
    if request.producers:
        found: list[RelationSignal] = []
        for producer in request.producers:
            found.extend(
                run_producer(producer, [request.text_for_producers()], scope=scope)
            )
        discovered = tuple(found)
        # Phase 4C: **and the discovered signals are bound before assembly sees them.** They
        # arrive holding deferred addresses, and assembly groups by participant reference, so
        # unbound they would group under their own strings forever - report as though they had
        # been read, corroborate nothing, and be unreachable by every mention id the platform
        # holds. The mention layer's records address whole entity spans at extractor
        # granularity while a producer addresses the cue group that matched, so there is no
        # re-addressing that would be honest; what 4C does is register the producer's own reads
        # and resolve through that, and refuse the ends that cannot resolve.
        #
        # `MentionStep.index` is the mention layer's own index and is the scope every bound id
        # must be minted in: the binding takes its capture and segment from the index rather
        # than from `document_ref`, because a minted id that disagreed with the mention layer's
        # own scope would be a second set of addresses for one retrieval — which is the
        # collision the capture key was added to prevent, arriving by another route (FR-018).
        # It is also the *only* thing that can resolve a `capture:` end and an **unpositioned**
        # surface (the syntactic producer's positions are clause-relative token indices, so
        # there is no span to register an occurrence from). It is `None` when the request named
        # no retrieval, and 4C then refuses rather than minting an id under an invented scope.
        # It is not defaulted to a placeholder index: a placeholder would resolve nothing while
        # looking as though it had been consulted.
        #
        # **What is deliberately not changed here.** `document_ref` above still comes from
        # `request.capture` alone, so the *declared* signal keeps `capture_ref=""` on a request
        # whose only retrieval is the one `_acquisition_capture` derived. That inconsistency is
        # real and it is reported rather than silently repaired, because repairing it would
        # change `capture_ref` — which is in `RelationSignal._material()` — and therefore re-key
        # every stored signal, candidate and claim on the golden path for a reason that has
        # nothing to do with 4C's deletions. See the phase report, `execution.py:2909`.
        if mentions.index is None:
            raise SemanticExecutionError(
                "producer_occurrence_scope_unavailable",
                f"{len(discovered)} producer signal(s) carry deferred participant addresses and "
                "this run named no retrieval, so the mention layer minted no index and no "
                "mention id can be minted honestly: a mention address is (capture, segment, "
                "extractor, span, surface) and the capture is the first key. Bind the producers "
                "against a named retrieval, or run no producer and keep the declared hypothesis "
                "(FR-018)",
            )
        discovered = bind_producer_signals(
            discovered,
            capture_ref=mentions.index.capture_ref,
            segment_ref=mentions.index.segment_ref,
            mention_index=mentions.index,
        )

    report = assemble(
        (*discovered, declared),
        tenant_id=request.tenant_id,
        context_ref=frame.context_id,
        semantic_regime_ref=regime_ref,
        investigation_id=request.investigation_id,
        recorded_by=request.recorded_by,
    )
    return replace(
        result,
        signals=SignalStep(declared=declared, discovered=discovered, report=report),
        reached=ExecutionStage.SIGNALS,
    )


def _span_to_dict(result: ExecutionResult) -> dict[str, object] | None:
    """The declared trigger span as a mapping the assembler can pass on, or ``None``.

    A span, not a span *ref*: :class:`extractors.signals.signal.RelationSignal` is built
    from primitives the producer contract can express, and the caller-supplied span is
    carried as data rather than as a live object so the declared signal is the same shape
    whether it was built here or by a producer. The assembler reads it back in
    ``_candidate_for``.
    """
    request = result.request
    if request.trigger_span is None:
        return None
    span = request.trigger_span
    return {
        "segment_ref": span.segment_ref,
        "start": span.start,
        "end": span.end,
        "mention_ref": span.mention_ref,
    }


def _candidate_step(result: ExecutionResult) -> ExecutionResult:
    """Step 7 - build the extraction hypothesis and its operator contract.

    The operator is the one step 5 already derived from the same ``RelationSchema`` by
    :func:`semantic.operators.default_operator_for_schema` and handed forward, so the
    schema stays the single declaration of what the relation means, the affordances that
    pruned the candidate set and the contract the claim is admitted under are *the same
    object*, and blocking cannot have run against a different one (FR-006, US7). The
    candidate takes the ``role_assignment`` shape - ``NARY`` with two named role bindings -
    because that is the shape ``works_for`` has in this slice, and because a ``DIRECTED``
    candidate carrying role assignments is refused by construction, so a role-shaped
    hypothesis is ``NARY`` or it is not admissible.

    The trigger span is the region *between* the two mentions, which is what a lexical
    cue is: a ``SpanRef`` with no ``mention_ref`` is exactly that shape. The temporal
    hypothesis is ``explicit`` because "in 2020" was read out of the text with no
    inference behind it, and a guess promoted silently would be the failure
    ``TemporalHypothesis``'s ``basis`` field exists to prevent.
    """
    request = result.request
    observation = result.observation.observation
    mentions = result.mentions
    operator = result.resolution.operator
    signals = result.signals
    if signals is None or signals.report is None:
        raise SemanticExecutionError(
            "signals_step_missing",
            "the candidate step reads an assembled reading, so the signals step must have "
            "run; a candidate constructed here instead would be the hand-built reading this "
            "path stopped doing in feature 019 (T034)",
        )
    wanted = RelationRef(request.relation_type, request.schema.schema_version)
    readings = signals.candidates_matching(wanted)
    if not readings:
        raise SemanticExecutionError(
            "declared_reading_missing",
            f"no assembled candidate carries {wanted}. The declaration is a signal like any "
            "other, so it is aggregated and can lose - and if it has, the report says so: "
            f"unattributed={signals.unattributed}. Reading "
            f"{len(signals.report.candidates)} candidate(s) and finding none with this "
            "operator means the request's own declaration did not survive assembly, which "
            "is a bug in the signal step rather than a fact about the document",
        )
    # Exactly one reading should match: the declared signal is the only source that names
    # this operator over these mentions, and a second would mean something else in the
    # document also stated it. That is legitimate - a cue phrase and a table header naming
    # the same relation - and both signals are already in the same reading's signal_refs, so
    # one candidate is still the right answer. Two *candidates* for one operator over one
    # pair would mean two readings that the key failed to merge.
    if len(readings) > 1:
        raise SemanticExecutionError(
            "duplicate_declared_reading",
            f"{len(readings)} assembled candidates carry {wanted} over the same mention "
            f"pair: {[c.candidate_id for c in readings]}. Assembly groups by pair and by "
            "reading, so two candidates here means two readings that should have been one - "
            "a disagreement the assembly key did not catch",
        )
    assembled = readings[0]
    # The fields the caller supplied and the assembler does not model are restored here,
    # and each one is restored from the *request* rather than from the signal: the span, the
    # window, the observation and the evidence set are the caller's account of what it read,
    # and the assembler's job was to derive the identity, not to re-decide those.
    proposed = replace(
        assembled,
        candidate_id="",
        trigger_span=(
            SpanRef(
                segment_ref=str(assembled.trigger_span.get("segment_ref", "")),
                start=int(assembled.trigger_span.get("start", 0)),
                end=int(assembled.trigger_span.get("end", 0)),
                mention_ref=str(assembled.trigger_span.get("mention_ref", "")),
            )
            if isinstance(assembled.trigger_span, dict)
            else _measured_trigger(result, observation.segment_id)
        ),
        observation_refs=(observation.observation_id,),
        evidence_refs=(
            observation.observation_id,
            observation.segment_id,
            mentions.subject.mention_id,
            mentions.obj.mention_id,
        ),
        temporal_hypothesis=TemporalHypothesis.explicit(
            valid_from=request.valid_from,
            valid_to=request.valid_to,
            semantics=request.schema.temporal_semantics,
        ),
        confidence=request.confidence,
        extractor_version=_reading_extractor_version(result, observation.extraction_version),
        observed_at=observation.observed_at,
    ).with_id()
    return replace(
        result,
        candidate=CandidateStep(
            schema=request.schema,
            operator=operator,
            proposed=proposed,
        ),
        reached=ExecutionStage.CANDIDATE,
    )


def _claim_step(result: ExecutionResult) -> ExecutionResult:
    """Step 8 - build the material, validate it, and admit it (feature 019, CD-1).

    **This is the change CD-1 exists to make.** The step used to call
    ``step.supported.to_claim(...)``, and that is worth unpacking because every part of
    it was wrong in the same direction:

    * ``to_claim`` raised unless the reading carried the ``SUPPORTED`` label, so the label
      was the precondition for committing anything - and a label is a string a caller
      writes. The gate tested the caller's belief.
    * ``to_claim`` reached admission through
      :func:`~domain.relation_claim_material.admit` with
      :func:`~domain.relation_claim_material.unvalidated_report` - a report saying
      "nothing was checked". So even the report slot that exists to gate admission carried
      no findings. The evidence was not consulted, not weakly consulted: not at all.
    * The relabelled ``supported`` reading was what got committed, so the thing that
      entered the graph was not the reading extraction produced.

    The order here is the substance. :func:`~domain.relation_claim_material.build` cannot
    admit, by construction - its return type has no path to a committed claim even in
    principle. :func:`~domain.relation_claim_material.validate` cannot admit either, and
    does not need to: ``LayeredValidator`` was widened to read a *material*, so the six
    stages can run before anything is committed. :func:`~domain.relation_claim_material.admit`
    is the only producer of a claim, and it now receives a real report. The candidate is
    never relabelled on the way through.

    That last point is what makes the guard meaningful. A reading with an adverse finding
    under a blocking operator policy is refused here, and the caller cannot make it pass
    by writing ``supported`` on the record - because nothing reads that field any more.

    **The role bindings are rebuilt against the resolved entities, not transcribed.**
    A candidate's role bindings name *mentions*, because a candidate has resolved
    nothing; a claim's must name *admitted participants*. Handing
    ``to_claim`` the candidate's own bindings - the obvious reading of a parameter
    called ``role_bindings`` - produces a claim whose identity material holds mention
    refs in ``role_bindings`` and entity refs in ``subject_ref``/``object_ref``: two
    ref namespaces in one claim, which is the Mention/Entity separation I-2 exists to
    hold apart. It also leaks into the projection, because
    ``GraphProjectionBridge.to_nodes`` emits a node for every participant including
    every role member, so the graph grows four nodes for two entities and the N-ary
    hyperedge's members are mentions rather than the entities the relation is about.
    The mapping is rebuilt here by asking the resolution batch what each **mention**
    resolved to, so a role member is the entity the mention actually resolved to rather
    than a digest of the mention.

    ``source_independence_groups`` is passed from the resolution batch, so the
    ``cross_source`` stage has real groups to corroborate against rather than an empty
    set that can only ever answer ``UNKNOWN``.
    """
    request = result.request
    step = result.candidate
    resolution = result.resolution
    material = build_material(
        step.proposed,
        subject_ref=resolution.subject_ref,
        object_ref=resolution.object_ref,
        revision_number=request.revision_number,
        evidence_grade=request.evidence_grade,
        tenant_id=request.tenant_id,
        role_bindings=(
            RelationRoleBinding(
                binding.role,
                resolution.batch.entity_for(binding.member_ref),
                binding.member_class,
            )
            for binding in step.proposed.role_assignments
        ),
        assertion_refs=tuple(
            assertion.type_assertion_id for assertion in result.types.assertions
        )
        + request.assertion_refs,
        source_independence_groups=resolution.independence_groups(),
        normalization_version=request.normalization_version,
        ontology_version=request.ontology_version,
        observed_at=result.observation.observation.observed_at,
    )
    report = validate_material(
        material,
        operators={request.relation_type: step.operator},
        resolution=result.regime.resolution,
        type_assertions=dict(result.types.by_entity),
        contexts={
            result.regime.base_frame.context_id: result.regime.base_frame,
            result.regime.frame.context_id: result.regime.frame,
        },
        # Empty rather than a default guess: there is no committed claim yet at this point
        # in the lifecycle, and inventing a peer set for the cross_source stage to
        # corroborate against would be asserting relations nobody admitted. The stage will
        # answer UNKNOWN, which is the truth - and `_validation_step` re-runs it over the
        # committed claim with the claim itself in scope.
        claims=(),
        regime=result.regime.regime,
    )
    claim = admit_material(
        material,
        report,
        operator=step.operator,
        claim_status=request.claim_status,
        created_at=result.observation.observation.observed_at,
    )
    return replace(
        result,
        claim=ClaimStep(
            claim=claim,
            candidate_id=step.proposed.candidate_id,
            logical_candidate_id=step.proposed.logical_candidate_id,
        ),
        reached=ExecutionStage.CLAIM,
    )


def _validation_step(result: ExecutionResult) -> ExecutionResult:
    """Step 9 - run the six validation stages over the claim that now exists.

    The claim is built before it is validated, and that ordering is forced rather than
    chosen: ``LayeredValidator.evaluate`` takes a ``RelationClaim``, and
    ``to_claim`` *is* the admission act, so a candidate cannot be validated without
    first being admitted. Every input is the real object - the operator map, the
    resolved profile, the observed type assertions keyed by entity, both frames, the
    regime, the claim set - and each stage is evaluated exactly once, with the report
    assembled from those findings by ``report_for``.

    Nothing is removed: the claim object the caller already holds is the same object
    afterwards, with the same evidence and the same identity (FR-012).
    """
    request = result.request
    contexts = {
        result.regime.base_frame.context_id: result.regime.base_frame,
        result.regime.frame.context_id: result.regime.frame,
    }
    validator = LayeredValidator(
        operators={request.relation_type: result.candidate.operator},
        resolution=result.regime.resolution,
        type_assertions=dict(result.types.by_entity),
        contexts=contexts,
        claims=(result.claim.claim,),
        regime=result.regime.regime,
    )
    outcomes = tuple(
        validator.evaluate_stage(stage, result.claim.claim) for stage in VALIDATION_STAGE_ORDER
    )
    report = validator.report_for(
        result.claim.claim,
        [finding for outcome in outcomes for finding in outcome.findings],
    )
    return replace(
        result,
        validation=ValidationStep(
            report=report, outcomes=outcomes, validator=validator
        ),
        reached=ExecutionStage.VALIDATION,
    )


def _admission_step(result: ExecutionResult) -> ExecutionResult:
    """Step 9 - ask the operator's own view whether it admits the claim.

    :meth:`LayeredValidator.admission_decision` runs the semantic stage for its
    findings and hands them to :func:`semantic.validation.decide_materialisation`,
    which never receives the claim and therefore cannot withhold one from anywhere
    but this operator's view. Under the default ``warn`` the answer is materialisable
    however adverse the findings were: a finding, a claim and an edge, all three (SC-8).
    """
    decision = result.validation.validator.admission_decision(result.claim.claim)
    return replace(
        result, admission=AdmissionStep(decision=decision), reached=ExecutionStage.ADMISSION
    )


def _store_step(result: ExecutionResult) -> ExecutionResult:
    """Step 11 - write through the real relation store, twice, and read it back.

    The second write is the idempotency proof (I-11): identical content under one
    ``relation_id`` returns the same id and the count is unchanged. Provenance is
    enforced before anything is stored, so a refusal would leave the store
    byte-identical rather than half-written (I-12). An injected store is used as
    supplied, which is how a caller runs two executions against one projection.
    """
    request = result.request
    observation = result.observation.observation
    store = (
        request.relation_store
        if request.relation_store is not None
        else InMemoryRelationStore()
    )
    claim = result.claim.claim
    provenance = request.provenance(observation)
    relation_id = store.write(claim, provenance=provenance)
    before = len(store)
    store.write(claim, provenance=provenance)
    return replace(
        result,
        store=StoreStep(
            relation_id=relation_id,
            stored=store.get(relation_id),
            checksum=store.checksum(),
            store=store,
            write_count_before_repeat=before,
            write_count_after_repeat=len(store),
        ),
        reached=ExecutionStage.STORE,
    )


def _edge_step(result: ExecutionResult) -> ExecutionResult:
    """Step 12 - project the stored claim into the graph, and read direction back.

    ``GraphProjectionBridge`` supplies the node, edge and hyperedge forms and mints no
    identifier: ``edge_id`` is the claim's own ``relation_id``, so the edge and the
    claim are one object seen twice. Both nodes are written before the edge because the
    store refuses an edge whose endpoints do not exist, and both the ``out`` and ``in``
    reads are taken with an explicit direction because an ``NARY`` edge's *default* is
    ``both`` - the explicit read is the only way the smoke run can show that
    orientation survived the projection rather than collapsing into symmetric adjacency
    (FR-010, spec 016 D2).
    """
    request = result.request
    claim = result.store.stored
    observation = result.observation.observation
    bridge = GraphProjectionBridge()
    store = request.graph_store if request.graph_store is not None else InMemoryGraphStore()
    provenance = request.provenance(observation)
    nodes = bridge.to_nodes(claim)
    for node in nodes:
        store.write_node(node, provenance)
    edge = bridge.to_edge(claim)
    store.write_edge(edge, provenance)
    hyperedge = (
        bridge.to_hyperedge(claim) if claim.arity_mode is RelationArityMode.NARY else None
    )
    if hyperedge is not None:
        store.write_hyperedge(hyperedge, provenance)
    return replace(
        result,
        edge=EdgeStep(
            edge=edge,
            nodes=nodes,
            hyperedge=hyperedge,
            out_neighbors=tuple(
                store.neighbors(claim.subject_ref, claim.relation_type, direction="out")
            ),
            in_neighbors=tuple(
                store.neighbors(claim.object_ref, claim.relation_type, direction="in")
            ),
            store=store,
        ),
        reached=ExecutionStage.EDGE,
    )


def _worldline_step(result: ExecutionResult) -> ExecutionResult:
    """Step 13 - append one real stream record and fold the entity's worldline.

    The record is a genuine :class:`domain.dynamics.StreamRecord` whose payload carries
    the claim's participants, the occurrence instant with its declared precision, the
    confidence and the trigger span, and whose own fields carry the observation
    reference that makes the event evidence-backed - ``require_evidence`` refuses a
    record with neither, so the event cannot exist unbacked (I-3). The fold is
    :func:`domain.temporal_worldline.build_worldline`, so the event id is a content
    address over the occurrence, the participants, the state transition and the record
    hash, and the integrity fingerprint covers exactly the records that built it
    (I-11, I-12). This is the occurrence the claim asserts, on the subject entity's own
    trajectory, not a placeholder.
    """
    request = result.request
    claim = result.store.stored
    observation = result.observation.observation
    trigger = result.candidate.proposed.trigger_span
    record = StreamRecord(
        entity_id=result.resolution.subject_ref,
        kind=f"relation.{claim.relation_type}",
        ts=observation.observed_at,
        tenant_id=request.tenant_id,
        payload={
            "occurred_at": request.valid_from.isoformat(),
            "time_precision": "year",
            "participants": [
                {
                    "entity_id": claim.subject_ref,
                    "role": request.subject_role,
                    "schema_name": result.types.subject.type_ref,
                },
                {
                    "entity_id": claim.object_ref,
                    "role": request.object_role,
                    "schema_name": result.types.obj.type_ref,
                },
            ],
            "state": {
                claim.relation_type: claim.object_ref,
                "context_ref": claim.context_ref,
                "relation_id": claim.relation_id,
            },
            "confidence": claim.confidence,
            "span_start": None if trigger is None else trigger.start,
            "span_end": None if trigger is None else trigger.end,
            "extractor": claim.extraction_version,
        },
        valid_from=request.valid_from,
        observation_id=observation.observation_id,
        extraction_version=claim.extraction_version,
        sequence=1,
    )
    worldline = build_worldline(
        [record],
        tenant_id=request.tenant_id,
        entity_id=result.resolution.subject_ref,
        require_evidence=True,
    )
    return replace(
        result,
        worldline=WorldlineStep(
            record=record,
            worldline=worldline,
            events=worldline.events,
            entity_id=worldline.entity_id,
        ),
        reached=ExecutionStage.WORLDLINE,
    )


_STEP_TABLE: tuple[tuple[ExecutionStage, Callable[[ExecutionResult], ExecutionResult]], ...] = (
    (ExecutionStage.OBSERVATION, _observation_step),
    (ExecutionStage.CONTEXT, _context_step),
    (ExecutionStage.MENTIONS, _mentions_step),
    (ExecutionStage.REGIME, _regime_step),
    (ExecutionStage.SIGNALS, _signal_step),
    (ExecutionStage.RESOLUTION, _resolution_step),
    (ExecutionStage.TYPES, _types_step),
    (ExecutionStage.CANDIDATE, _candidate_step),
    (ExecutionStage.CLAIM, _claim_step),
    (ExecutionStage.VALIDATION, _validation_step),
    (ExecutionStage.ADMISSION, _admission_step),
    (ExecutionStage.STORE, _store_step),
    (ExecutionStage.EDGE, _edge_step),
    (ExecutionStage.WORLDLINE, _worldline_step),
)
