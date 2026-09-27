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
:class:`extractors.registry.Mention` values, the ``TypeAssertion`` values, the
``SemanticRegime``, the ``RelationCandidate``, the ``BlockingResult``, the
``ValidationReport``, the ``RelationClaim``, the ``GraphEdge``, the
``WorldlineEvent``. Nothing is flattened into a summary of strings, because a
summary is not inspectable. A stage that was not reached is ``None``, so "not run
yet" and "ran and produced nothing" stay distinguishable.

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
``BLOCKING -> CLAIM -> VALIDATION -> ADMISSION -> STORE -> EDGE -> WORLDLINE``,
and the resulting finding is a design question for the next round: validation
should be able to run against a *candidate* shape, or ``to_claim`` should be split
into "build" and "admit" so a claim can exist, be validated, and still be refused.

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

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from domain.dynamics import StreamRecord
from domain.evidence_context import (
    ContextCompleteness,
    ContextTrustState,
    EvidenceContext,
    InMemoryContextResolver,
)
from domain.evidence_lineage import EvidenceGraph, EvidenceHop, HopKind, LineageTrace
from domain.relation_candidate import (
    CandidateStatus,
    ExtractionStrategy,
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
from domain.relation_identity import RelationArityMode, canonical_material, digest128
from domain.relation_schema import RelationSchema, TemporalSemantics
from domain.temporal_worldline import EntityWorldline, WorldlineEvent, build_worldline
from extractors.registry import DeterministicExtractorSet, Mention, SemanticHint
from extractors.types import TypedMention
from extractors.util import byte_offset, end_byte_offset
from graph.abstraction import GraphEdge, GraphNode, HyperEdge, InMemoryGraphStore
from graph.relation_store import GraphProjectionBridge, InMemoryRelationStore
from semantic.blocking import (
    BlockingResult,
    RelationRole,
    TypeHypothesis,
    block_for_relation,
)
from semantic.blocking import (
    Candidate as BlockingCandidate,
)
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
from semantic.validation import (
    STAGE_ORDER as VALIDATION_STAGE_ORDER,
)
from semantic.validation import (
    LayeredValidator,
    MaterialisationDecision,
    StageOutcome,
)

__all__ = [
    "GOLDEN_SENTENCE",
    "STAGE_ORDER",
    "AdmissionStep",
    "BlockingStep",
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
    "RegimeStep",
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
    "entity_ref_for",
    "forward_lineage",
    "golden_request",
    "mention_id_for",
    "role_target_org_extractor",
    "run_golden_path",
    "run_until",
    "works_for_schema",
]

#: The one sentence the architect named, so nothing drifts onto a different fixture.
GOLDEN_SENTENCE = "John Smith became CEO of Acme in 2020."

_OBSERVATION_ID_PREFIX = "OBS-"
_EVENT_ID_PREFIX = "EVT-"
_CAPTURE_ID_PREFIX = "CAP-"
_MENTION_ID_PREFIX = "MN-"
_ENTITY_ID_PREFIX = "ENT-"

EXTRACTION_SET_VERSION_PREFIX = "det-set-"


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
    """The thirteen steps, in the order they execute.

    The order is the point of the enum: it is what a reader follows, what a caller
    stops at, and what a diff is read against. :data:`STAGE_ORDER` is derived from
    the declaration order so the two cannot drift apart.
    """

    OBSERVATION = "observation"
    CONTEXT = "context"
    MENTIONS = "mentions"
    TYPES = "types"
    REGIME = "regime"
    CANDIDATE = "candidate"
    BLOCKING = "blocking"
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
    segment_ref: str,
    kind: str,
    value: str,
    start: int,
    end: int,
    extractor: str,
) -> str:
    """``MN-`` + 128-bit digest: which mention this is, from its own surface.

    Derived through the same ``digest128``/``canonical_material`` pair every other
    content address in the platform uses, so two readings of the same surface in the
    same segment are one mention (idempotency) and a *different* extractor reading
    it is a different mention - the extractor is in the material because how a
    surface was read is part of what was read.
    """
    return _MENTION_ID_PREFIX + digest128(
        canonical_material(
            {
                "segment": segment_ref,
                "kind": kind,
                "value": value,
                "start": start,
                "end": end,
                "extractor": extractor,
            }
        )
    )


def entity_ref_for(tenant_id: str, mention_id: str) -> str:
    """``ENT-`` + 128-bit digest: the entity one mention resolved to.

    The *only* resolution this module performs, and deliberately the weakest
    honest one: one mention, one candidate entity, no corroboration. That is not a
    claim that the mention and the entity are the same thing in the world; it is a
    deterministic stand-in that lets the rest of the path address a stable
    participant. A real resolution engine would substitute its own ids here and
    nothing downstream would change, because every id is a content address and the
    chain is reference-based. Blocking narrows the universe and is not consulted
    here; nothing in this function looks at a type.
    """
    return _ENTITY_ID_PREFIX + digest128(
        canonical_material({"tenant": tenant_id, "mention": mention_id})
    )


def capture_id_for(source_id: str, observation_id: str) -> str:
    """``CAP-`` + 128-bit digest: the capture that produced one observation.

    The evidence chain is ``Source -> Capture -> Observation -> ...`` and the capture
    hop is the one link with no value type of its own anywhere in the platform. It
    is derived here so the chain is complete rather than silently skipping a hop,
    and derived rather than generated so a replay reproduces it.
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
    revision_number: int = 1
    claim_status: RelationStatus = RelationStatus.ACTIVE
    evidence_grade: EvidenceGrade = EvidenceGrade.MODERATE
    evidence_refs: tuple[str, ...] = ()
    assertion_refs: tuple[str, ...] = ()
    confidence: float = 0.85
    recorded_by: str = "semantic-execution"
    relation_store: InMemoryRelationStore | None = None
    graph_store: InMemoryGraphStore | None = None

    @property
    def relation_type(self) -> str:
        """The operator identity both the candidate and the claim will carry."""
        return self.schema.relation_type

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


@dataclass(frozen=True)
class TypeStep:
    """Step 4: the observed typing layer, one assertion per relation end (FR-003).

    ``scope=OBSERVED`` and ``status=OBSERVED`` unconditionally: this layer is what
    the extractor said, and it consults no profile, no pack and no ontology. An
    unknown type reference is recorded verbatim and is a first-class value, so no
    input to this step can fail on unfamiliar content (FR-001).
    """

    assertions: tuple[TypeAssertion, ...]
    subject: TypeAssertion
    obj: TypeAssertion
    by_entity: Mapping[str, tuple[TypeAssertion, ...]] = field(default_factory=dict)

    def assertions_for(self, entity_ref: str) -> tuple[TypeAssertion, ...]:
        """Every typing claim recorded about one entity, across all layers."""
        return self.by_entity.get(entity_ref, ())


@dataclass(frozen=True)
class RegimeStep:
    """Step 5: the instruments that interpreted it, and the frame they extend.

    The regime *points at* the frame and the frame never points back, so
    :func:`semantic.regime.extend_context` returns a **new** content-addressed frame
    and the base frame keeps its own id forever. The claim is admitted under the
    extended frame - that is the one carrying ``ontology_version`` and ``language``
    as the regime pinned them - and both stay registered, so nothing already pointing
    at the base one stops resolving (FR-014, FR-018).
    """

    resolution: ProfileResolution
    regime: SemanticRegime
    base_frame: EvidenceContext
    frame: EvidenceContext


@dataclass(frozen=True)
class CandidateStep:
    """Step 6: the extraction hypothesis, its operator contract, and both readings.

    ``proposed`` is the raw ``PROPOSE`` reading extraction produced; ``supported`` is
    the same hypothesis after the check that admits it. Both are returned because a
    rejection is a preserved candidate and never a deleted one (I-3, FR-006), and
    because their distinct ``candidate_id`` values under one ``logical_candidate_id``
    are the two-level identity working as designed.
    """

    schema: RelationSchema
    operator: RelationOperator
    proposed: RelationCandidate
    supported: RelationCandidate


@dataclass(frozen=True)
class BlockingStep:
    """Step 7: the candidate universe, the type hypotheses, and what they removed.

    Two calls, one per relation end, both through
    :func:`semantic.blocking.block_for_relation` so the affordance kinds come from the
    operator via ``affordance_kinds`` rather than from a re-derivation here (US7,
    FR-016). ``subject_ref``/``object_ref`` are the canonically-first survivors, which
    is a *deterministic* choice and not a resolution decision - see
    :func:`entity_ref_for`. Pruning asserts nothing: the pruned candidates come back
    in ``pruned_candidates`` as the original frozen objects, unaltered.
    """

    universe: tuple[BlockingCandidate, ...]
    hypotheses: tuple[TypeHypothesis, ...]
    subject_block: BlockingResult
    object_block: BlockingResult
    subject_ref: str
    object_ref: str


@dataclass(frozen=True)
class ValidationStep:
    """Step 8: the layered, graded report, and the validator that produced it.

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
    """Step 9: the admission decision, as a named, operator-scoped value.

    Never a boolean. Under the default ``warn`` policy ``decision.materialisable`` is
    ``True`` however adverse the findings were, and ``decision.scope`` records that
    the answer is about *this operator's view* and about nothing else - which is
    SC-8 exactly: a ``works_for`` whose object is not organization-like produces a
    finding, a materialised claim and a projected edge (FR-012).
    """

    decision: MaterialisationDecision


@dataclass(frozen=True)
class ClaimStep:
    """Step 10: the checked reading promoted to a claim, with identity derived once.

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
    types: TypeStep | None = None
    regime: RegimeStep | None = None
    candidate: CandidateStep | None = None
    blocking: BlockingStep | None = None
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
        if self.types is not None:
            pairs.extend(
                ("type_assertion", item.type_assertion_id) for item in self.types.assertions
            )
            pairs.extend(
                ("logical_type_assertion", item.logical_type_assertion_id)
                for item in self.types.assertions
            )
        if self.regime is not None:
            pairs.append(("regime", self.regime.regime.regime_id))
            pairs.append(("interpreted_context", self.regime.frame.context_id))
        if self.candidate is not None:
            step = self.candidate
            pairs.append(("candidate", step.supported.candidate_id))
            pairs.append(("logical_candidate", step.supported.logical_candidate_id))
            pairs.append(("proposed_candidate", step.proposed.candidate_id))
        if self.blocking is not None:
            pairs.append(("subject_block", self.blocking.subject_block.content_key()))
            pairs.append(("object_block", self.blocking.object_block.content_key()))
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
    """A fresh deterministic extractor set: the five built-ins, optionally plus one.

    ``role_target_orgs`` adds :func:`role_target_org_extractor`, and the reason it is
    not one of the five is a real gap worth naming. The built-in English organisation
    grammar in ``extractors.orgs`` keys on a **legal-form suffix**
    (``Inc``/``Corp``/``Ltd``/``University``/...) or a Russian legal form, so ``"Acme"``
    alone in ``"John Smith became CEO of Acme in 2020."`` yields no organisation
    mention at all, and ``"CEO of Acme Corporation"`` yields a mention whose surface
    swallows the role cue. The rule below keys on the *role cue* instead - a
    different rule rather than a copy of the first - and lives here as caller-supplied
    configuration, so the gap is visible in the caller rather than papered over inside
    the extraction package.

    ``ontology_pack`` is forwarded untouched and is advisory: it annotates mentions
    with what a pack recognises and can never filter one (FR-002).
    """
    extractors = DeterministicExtractorSet(ontology_pack=ontology_pack)
    extractors.register_builtin()
    if role_target_orgs:
        extractors.register("role_target_orgs", role_target_org_extractor)
    return extractors


_ROLE_CUE = re.compile(
    r"\b(?:CEO|chief\s+[A-Za-z]+|director|head|president|chair(?:man|woman|person)"
    r"|founder|manager|partner|owner)\s+of\s+"
    r"([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,3})"
)


def role_target_org_extractor(text: str, lang_hint: str | None = None) -> list[TypedMention]:
    """A role-cue organisation reader: the proper-noun run after ``<ROLE> of``.

    Deterministic, rule-only, no model - the same honesty contract as the built-in
    extractors, and the same reduced confidence for a pattern-only match. It reads the
    *cue* rather than the corporate form, which is the complementary half of
    ``extractors.orgs``'s grammar rather than a second implementation of it: a
    document writing "Acme Corp" and a document writing "CEO of Acme" are both
    common, and only one of them is reachable from a suffix list.

    Offsets are UTF-8 byte offsets, matching ``extractors.orgs`` and
    ``extractors.persons``, which both go through ``extractors.util.byte_offset``.
    """
    found: list[TypedMention] = []
    for match in _ROLE_CUE.finditer(text):
        surface = match.group(1).strip(" .,;")
        if not surface:
            continue
        start = match.start(1)
        cue = match.group(0)[: match.start(1) - match.start(0)].strip()
        found.append(
            TypedMention(
                kind="org",
                value=surface,
                offset=byte_offset(text, start),
                end_offset=end_byte_offset(text, start + len(surface)),
                extractor="role_target_orgs",
                lang=lang_hint,
                source="pattern",
                confidence=0.5,
                evidence={"cue": cue},
            )
        )
    return found


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


def golden_request(
    sentence: str = GOLDEN_SENTENCE,
    *,
    type_refs: Mapping[str, str] | None = None,
    profile_type_refs: Iterable[str] = ("schema:Person", "schema:Organization"),
    valid_from: datetime = datetime(2020, 1, 1, tzinfo=UTC),
    observed_at: datetime = datetime(2020, 6, 1, tzinfo=UTC),
    published_at: datetime | None = None,
    tenant_id: str = "default-tenant",
    investigation_id: str = "inv-golden-path",
    schema: RelationSchema | None = None,
    profile: SemanticProfile | None = None,
    extractors: DeterministicExtractorSet | None = None,
    with_decoys: bool = True,
    **overrides: Any,
) -> ExecutionRequest:
    """A fully specified request over the golden sentence, with every id stable.

    Every timestamp is a parameter with an explicit default rather than a clock read,
    so a caller who wants a different window asks for one and a caller who does not
    gets the same ids on every run and in every process. ``**overrides`` passes
    straight through to :class:`ExecutionRequest`, so a variant is a keyword argument
    and never an edit of this function.
    """
    declared = schema if schema is not None else works_for_schema()
    instruments = (
        profile if profile is not None else base_profile(*profile_type_refs, tenant_id=tenant_id)
    )
    return ExecutionRequest(
        sentence=sentence,
        schema=declared,
        profile=instruments,
        extractors=extractors if extractors is not None else deterministic_extractors(),
        observed_at=observed_at,
        published_at=published_at,
        valid_from=valid_from,
        valid_to=valid_from,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        type_refs=type_refs if type_refs is not None else _default_type_refs(),
        extra_candidates=decoy_universe() if with_decoys else (),
        **overrides,
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
    if result.mentions is None or result.candidate is None or result.blocking is None:
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
    candidate = result.candidate.supported
    mentions = result.mentions.records
    graph = EvidenceGraph()
    tenant = observation.tenant_id
    capture_id = capture_id_for(observation.source_id, observation.observation_id)
    assertion_ids = tuple(assertion.type_assertion_id for assertion in result.types.assertions)
    mention_of = {
        assertion.type_assertion_id: _mention_citing(assertion, mentions)
        for assertion in result.types.assertions
    }

    _link_node(
        graph,
        EvidenceHop(
            HopKind.SOURCE, observation.source_id, observation.source_family, tenant_id=tenant
        ),
        derived_from=("",),
        derives=(capture_id,),
    )
    _link_node(
        graph,
        EvidenceHop(HopKind.CAPTURE, capture_id, "capture", tenant_id=tenant),
        derived_from=(observation.source_id,),
        derives=(observation.observation_id,),
    )
    _link_node(
        graph,
        EvidenceHop(
            HopKind.OBSERVATION,
            observation.observation_id,
            observation.document_id,
            relation_id=claim.relation_id,
            tenant_id=tenant,
        ),
        derived_from=(capture_id,),
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
    for ref in (result.blocking.subject_ref, result.blocking.object_ref):
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
        capture_id=capture_id,
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
    )
    return replace(
        result, observation=ObservationStep(observation), reached=ExecutionStage.OBSERVATION
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
    """
    request = result.request
    observation = result.observation.observation
    found = request.extractors.extract(
        request.sentence, segment_ref=observation.segment_id, lang=observation.language
    )
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
    return replace(
        result,
        mentions=MentionStep(
            mentions=tuple(mentions),
            records=tuple(records),
            subject=_select(records, request.subject_kind, "subject"),
            obj=_select(records, request.object_kind, "object"),
            hints=tuple(hints),
        ),
        reached=ExecutionStage.MENTIONS,
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


def _types_step(result: ExecutionResult) -> ExecutionResult:
    """Step 4 - assert the observed typing of each relation end, with no gate.

    One :class:`semantic.contracts.TypeAssertion` per end at ``TypeScope.OBSERVED`` /
    ``SemanticStatus.OBSERVED``, carrying the surface it was read from, the extractor
    that read it, the frame it was read under, and the observation, segment and
    mention as evidence. The type reference comes from the request and is recorded
    verbatim: nothing here checks it against a profile, a pack or a vocabulary,
    because an unknown type is a first-class value (FR-001, FR-003).
    """
    request = result.request
    observation = result.observation.observation
    mentions = result.mentions
    frame = result.context.frame
    by_entity: dict[str, list[TypeAssertion]] = {}

    def build(record: MentionRecord, kind: str) -> TypeAssertion:
        type_ref = request.type_refs.get(kind, "")
        assertion = TypeAssertion(
            tenant_id=request.tenant_id,
            entity_ref=entity_ref_for(request.tenant_id, record.mention_id),
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

    subject = build(mentions.subject, request.subject_kind)
    obj = build(mentions.obj, request.object_kind)
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


def _regime_step(result: ExecutionResult) -> ExecutionResult:
    """Step 5 - resolve the profile, bind the regime, extend the frame.

    ``ProfileRegistry.resolve`` performs the inheritance walk (memoised, cycle-safe)
    and ``SemanticRegime.from_profile`` binds the result as a separate
    content-addressed value that *points at* the frame. ``extend_context`` then returns
    a **new** frame carrying the regime's pinned ``ontology_version`` and language; the
    base frame is untouched and keeps its id, so nothing already referring to it stops
    resolving (FR-014, FR-018).
    """
    request = result.request
    observation = result.observation.observation
    base_frame = result.context.frame
    registry = ProfileRegistry(tenant_id=request.tenant_id)
    registry.register(request.profile)
    resolution = registry.resolve(request.profile.profile_id, request.profile.version)
    regime = SemanticRegime.from_profile(
        resolution,
        context_ref=base_frame.context_id,
        ontology_version=request.ontology_version,
        validation_profile=request.validation_profile,
        language=observation.language,
        note=f"golden path over {observation.segment_id}",
        recorded_at=observation.observed_at,
    ).promoted(SemanticCommitment.TYPED)
    frame = extend_context(base_frame, regime)
    result.context.resolver.register(frame)
    return replace(
        result,
        regime=RegimeStep(
            resolution=resolution,
            regime=regime,
            base_frame=base_frame,
            frame=frame,
        ),
        reached=ExecutionStage.REGIME,
    )


def _candidate_step(result: ExecutionResult) -> ExecutionResult:
    """Step 6 - build the extraction hypothesis and its operator contract.

    The operator is derived from the request's ``RelationSchema`` by
    :func:`semantic.operators.default_operator_for_schema`, so the schema stays the
    single declaration of what the relation means and the operator only adds
    behaviour (FR-006). The candidate takes the ``role_assignment`` shape - ``NARY``
    with two named role bindings - because that is the shape ``works_for`` has in this
    slice, and because a ``DIRECTED`` candidate carrying role assignments is refused
    by construction, so a role-shaped hypothesis is ``NARY`` or it is not admissible.

    The trigger span is the region *between* the two mentions, which is what a lexical
    cue is: a ``SpanRef`` with no ``mention_ref`` is exactly that shape. The temporal
    hypothesis is ``explicit`` because "in 2020" was read out of the text with no
    inference behind it, and a guess promoted silently would be the failure
    ``TemporalHypothesis``'s ``basis`` field exists to prevent.
    """
    request = result.request
    observation = result.observation.observation
    mentions = result.mentions
    operator = default_operator_for_schema(request.schema)
    proposed = RelationCandidate(
        subject_mention_ref=mentions.subject.mention_id,
        object_mention_ref=mentions.obj.mention_id,
        relation_ref=RelationRef(request.relation_type, request.schema.schema_version),
        arity_mode=request.schema.arity_mode,
        role_assignments=(
            RelationRoleBinding(
                request.role_names[0],
                mentions.subject.mention_id,
                request.type_refs.get(request.subject_kind, ""),
            ),
            RelationRoleBinding(
                request.role_names[1],
                mentions.obj.mention_id,
                request.type_refs.get(request.object_kind, ""),
            ),
        ),
        context_ref=result.regime.frame.context_id,
        semantic_regime_ref=result.regime.regime.regime_id,
        trigger_span=SpanRef(
            segment_ref=observation.segment_id,
            start=min(mentions.subject.end, mentions.obj.start),
            end=max(mentions.subject.end, mentions.obj.start),
        ),
        extraction_method=ExtractionStrategy.LEXICAL_PATTERN,
        extractor_version=observation.extraction_version,
        extraction_rule_id="mention_cue",
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
        candidate_status=CandidateStatus.PROPOSE,
        confidence=request.confidence,
        tenant_id=request.tenant_id,
        investigation_id=request.investigation_id,
        observed_at=observation.observed_at,
        recorded_by=request.recorded_by,
    ).with_id()
    return replace(
        result,
        candidate=CandidateStep(
            schema=request.schema,
            operator=operator,
            proposed=proposed,
            supported=proposed.with_status(CandidateStatus.SUPPORTED),
        ),
        reached=ExecutionStage.CANDIDATE,
    )


def _blocking_step(result: ExecutionResult) -> ExecutionResult:
    """Step 7 - narrow the candidate universe with the operator's own affordances.

    One :func:`semantic.blocking.block_for_relation` call per end, so the kind filter
    comes from ``affordance_kinds`` reading the operator rather than from a
    re-derivation here (US7, FR-016). The hypotheses are built from the *observed type
    assertions*, which is the point: blocking narrows on recorded types and records
    nothing, so the module cannot type a pruned candidate even by accident.

    The surviving candidate's ``entity_ref`` becomes the participant ref the claim
    carries. Taking the canonically-first survivor is deterministic and deliberately
    the weakest honest choice: blocking is a cost optimisation, not a resolution, so
    nothing here asserts identity.
    """
    request = result.request
    operator = result.candidate.operator
    types = result.types
    mentions = result.mentions
    known = {record.mention_id: record for record in mentions.records}
    universe = (
        _universe_entry(types.subject, operator.subject_kinds, known),
        _universe_entry(types.obj, operator.object_kinds, known),
        *request.extra_candidates,
    )
    ordered = tuple(
        sorted(universe, key=lambda candidate: (candidate.entity_ref, candidate.name))
    )
    subject_hypothesis = _hypotheses(types.subject)
    object_hypothesis = _hypotheses(types.obj)
    subject_block = block_for_relation(
        ordered,
        subject_hypothesis,
        operator,
        RelationRole.SUBJECT,
        query_name=mentions.subject.value,
    )
    object_block = block_for_relation(
        ordered,
        object_hypothesis,
        operator,
        RelationRole.OBJECT,
        query_name=mentions.obj.value,
    )
    return replace(
        result,
        blocking=BlockingStep(
            universe=ordered,
            hypotheses=subject_hypothesis + object_hypothesis,
            subject_block=subject_block,
            object_block=object_block,
            subject_ref=_survivor(subject_block, mentions.subject.value),
            object_ref=_survivor(object_block, mentions.obj.value),
        ),
        reached=ExecutionStage.BLOCKING,
    )


def _universe_entry(
    assertion: TypeAssertion,
    declared_kinds: tuple[str, ...],
    known: Mapping[str, MentionRecord],
) -> BlockingCandidate:
    """One record of the candidate universe, as blocking sees it.

    ``kind`` is the operator's declared affordance class when it declares one - which
    is what the kind stage filters against - and the entity's own observed type
    otherwise, so a relation with no declared hints still narrows by type without
    being read as restricted. ``name`` is the mention surface, read off the mention
    the assertion cites rather than remembered.
    """
    record = _mention_citing(assertion, tuple(known.values()))
    return BlockingCandidate(
        entity_ref=assertion.entity_ref,
        name=record.value,
        kind=declared_kinds[0] if declared_kinds else assertion.type_ref,
        type_refs=(assertion.type_ref,) if assertion.type_ref else (),
    )


def _hypotheses(assertion: TypeAssertion) -> tuple[TypeHypothesis, ...]:
    """The type hypotheses one member carries, as :class:`semantic.blocking.TypeHypothesis`.

    Deliberately not a ``TypeAssertion``: a hypothesis has no evidence, no scope and
    no status ladder, and it has no effect on any record. The scheme travels with the
    reference so ``internal:Company`` and ``skos:Company`` cannot meet by spelling.
    """
    if not assertion.type_ref:
        return ()
    return (TypeHypothesis(type_ref=assertion.type_ref, scheme=assertion.type_scheme),)


def _survivor(block: BlockingResult, surface: str) -> str:
    """The canonically-first surviving candidate, or a typed refusal.

    The refusal names the query that resolved to nothing rather than substituting the
    mention ref, because a mention in a claim's identity material is exactly the
    substitution ``to_claim``'s own docstring warns against (I-2).
    """
    if not block.candidates:
        raise SemanticExecutionError(
            "blocking_resolved_nothing",
            f"no candidate survived blocking for surface {surface!r}; "
            f"{block.pruned_count} of {block.before_count} were pruned",
        )
    return block.candidates[0].entity_ref


def _claim_step(result: ExecutionResult) -> ExecutionResult:
    """Step 10 - promote the checked reading to a claim, with both ids derived once.

    :meth:`RelationCandidate.to_claim` is the only path across and it raises unless the
    reading is ``SUPPORTED``, so producing a claim here *is* the admission act. The
    ``assertion_refs`` it is given are the real typing claims, which is what makes the
    claim's identity material name the typing its participants rest on and what makes
    the lineage chain walkable from the claim to a mention.

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
    The mapping is rebuilt here, from the same deterministic
    :func:`entity_ref_for` the type assertions used.

    Two interface facts recorded here rather than worked around silently:
    ``evidence_refs`` is **required** by ``to_claim`` but ``RelationClaim`` has no
    field for it, so the evidence set a caller passes is dropped at admission; and
    ``source_independence_groups`` is not a parameter at all, so every claim this
    path produces has ``independent_source_count == 0`` and the validator's
    ``cross_source`` stage can only ever answer ``UNKNOWN``.
    """
    request = result.request
    step = result.candidate
    claim = step.supported.to_claim(
        subject_ref=result.blocking.subject_ref,
        object_ref=result.blocking.object_ref,
        revision_number=request.revision_number,
        claim_status=request.claim_status,
            evidence_grade=request.evidence_grade,
            tenant_id=request.tenant_id,
        role_bindings=(
            RelationRoleBinding(
                binding.role,
                entity_ref_for(request.tenant_id, binding.member_ref),
                binding.member_class,
            )
            for binding in step.supported.role_assignments
        ),
        assertion_refs=tuple(
            assertion.type_assertion_id for assertion in result.types.assertions
        )
        + request.assertion_refs,
        normalization_version=request.normalization_version,
        ontology_version=request.ontology_version,
        observed_at=result.observation.observation.observed_at,
    )
    return replace(
        result,
        claim=ClaimStep(
            claim=claim,
            candidate_id=step.supported.candidate_id,
            logical_candidate_id=step.supported.logical_candidate_id,
        ),
        reached=ExecutionStage.CLAIM,
    )


def _validation_step(result: ExecutionResult) -> ExecutionResult:
    """Step 8 - run the six validation stages over the claim that now exists.

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
    trigger = result.candidate.supported.trigger_span
    record = StreamRecord(
        entity_id=result.blocking.subject_ref,
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
        entity_id=result.blocking.subject_ref,
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
    (ExecutionStage.TYPES, _types_step),
    (ExecutionStage.REGIME, _regime_step),
    (ExecutionStage.CANDIDATE, _candidate_step),
    (ExecutionStage.BLOCKING, _blocking_step),
    (ExecutionStage.CLAIM, _claim_step),
    (ExecutionStage.VALIDATION, _validation_step),
    (ExecutionStage.ADMISSION, _admission_step),
    (ExecutionStage.STORE, _store_step),
    (ExecutionStage.EDGE, _edge_step),
    (ExecutionStage.WORLDLINE, _worldline_step),
)
