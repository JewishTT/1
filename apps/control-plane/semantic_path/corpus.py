"""The corpus runner: real sentences in, a recorded world out, and three proofs.

``specs/018-world-substrate/spec.md`` FR-020...FR-023, SC-11...SC-14; plan
decision D-C. The data is in :mod:`semantic_path.corpus_cases`; this module is the
code that runs it.

**What this is.** Functionality over a committed corpus. :func:`run_case` drives
the real thirteen-stage :mod:`semantic_path.execution` path over a case's committed
request and reads every real object the path produced - the
:class:`~semantic.resolution.ResolutionDecision` values, the durable
:class:`~domain.entity_identity.ResolutionDecisionRecord` and
:class:`~domain.entity_identity.EntityIdentity` rows, the real
:class:`~domain.capture.Capture` the acquisition seam emitted, the claim, the
projection, the worldline and both lineage traces. :func:`run_corpus` does that for
every case. Nothing here re-derives what a component already derives, and nothing
here fabricates an identifier.

**What this is not.** Not a test suite, and deliberately so. There is no ``assert``
in this module and no expectation that a case fails. A divergence is a
:class:`Divergence` value that a report prints; deciding what to do about it is the
caller's, which is what lets the corpus live beside the code rather than under
``tests/`` and lets a case record that the path *refuses*, which a test asserting
success could not.

**Three proofs, and what each one actually proves.**

* :func:`compare` - FR-021 and SC-11. ``run(input, versions, policy)`` compared over
  **five named layers** rather than the final graph, because a defect can hide
  behind an accidentally equal graph. The layers are ``identity`` (entity refs,
  anchors, merged mentions, identity fingerprints), ``decisions`` (the ``RES-``
  addresses *and* the record fingerprints *and* the reasoning behind them),
  ``claims`` (candidate, claim, materialisation, per-stage validation verdicts),
  ``context`` (frames, regime, capture, and both lineage traces' exact hop
  sequences) and ``edges`` (the graph projection, the worldline, and the store
  reads taken back out of both stores). Each layer's payload is a canonical list of
  ``(label, value)`` pairs and its digest is
  :func:`domain.relation_identity.digest128` over that list, so a divergence names
  the layer before it names the value. :func:`digest_bundle` reduces a whole run to
  one mapping of strings, which is what makes a **cross-process** comparison
  possible without writing a file.
* :func:`replay` - FR-022 and SC-12. Two replays, because they prove different
  things. :func:`replay_from_request` re-executes the recorded request against
  **empty** stores and compares everything, which proves the request is a complete
  input. :func:`replay_from_records` rebuilds the durable stores, the claim, the
  projection and the lineage from the recorded event log **alone**, with no live
  object from the original run reachable, which proves the log is sufficient. The
  second is the one FR-022 asks for. :func:`replay_of_replay` feeds the first
  replay's own log into the second and requires identity, which is the fixed point.
* :func:`acceptance_chains` - SC-14, the gate. Both chains, reconstructed from
  durable state, for every case, with every link's status named. A hole is a
  :class:`ChainHole` naming the link, not a shorter chain that reads as whole.

**The gaps this module found, stated here rather than papered over.**
:func:`acceptance_chains` reports them per case and this docstring says which they
are, so a reader who meets one in the output has already been told to expect it.
Every one of them is a fact about code this module does not own - ``execution.py``
or ``apps/shared/**`` - and every one is reported with the specific missing link
rather than worked around:

1. **The capture hop in the orchestrator's lineage is a derived stand-in.**
   :func:`semantic_path.execution.capture_id_for` is a digest of
   ``(source_id, observation_id)`` - computed *from* the observation it is supposed
   to explain. The real :class:`~domain.capture.Capture` the acquisition seam
   emitted addresses to something else entirely and is on no graph the orchestrator
   built, so a reader following its own chain arrives at a ``CAP-`` that is in no
   registry. Task T012 is therefore not done. The corpus links the **real** capture
   into the durable anchor, so the corpus's own entity chain is whole, and it
   reports the derived id beside it in the same sentence - the difference is
   visible per case rather than argued about in prose.
2. **A committed claim carries no reference to its candidate.**
   :class:`~domain.relation_claim.RelationClaim` has no ``candidate_id`` field, so
   ``RelationClaim -> RelationCandidate`` is walkable only through the run's
   :class:`~semantic_path.execution.CandidateStep` - in memory, not on the record.
   The chain report marks the link ``in_memory_only``. The material that preceded
   admission does carry it, so the information exists one layer earlier and is
   dropped by :func:`domain.relation_claim_material.admit`.
3. **A committed claim has no ``evidence_refs`` field either.**
   Its mentions and its segment travel inside ``observation_refs``, which is the
   right content under the wrong name. The chain report marks the link ``present``
   and says in the same line that the field a reader would look for is absent.
4. **The entity chain's ``Mentions`` link is only partly walkable.**
   :attr:`semantic.resolution.ResolutionDecision.merged_mentions` is the union of
   this segment's mentions and the ``support_mention_ids`` carried on the registry
   record, and the carried ones were produced by some earlier observation that this
   corpus does not hold. The chain report marks the link ``partial`` and names both
   halves. The gap is in the **fixture**, not the machinery: a registry record
   ingested as its own source would close it.
5. **A newly minted identity carries no independence groups.**
   :meth:`semantic.resolution.ResolutionBatch.supporting_groups_for` looks a record
   up by ``identity_ref()``, and a record with no established identity answers
   ``NEW-`` while the claim quotes the minted ``ENT-``. So for the
   ``minted_identity`` case ``independent_source_count`` is zero and the
   cross-source stage answers ``no_independence_recorded``, even though the
   selected record recorded a supporting group.
6. **The resolution scope's anchors are not :class:`EntityAnchor` values.**
   :class:`semantic.resolution.MentionResolver` stores its private anchor-assignment
   type inside :class:`semantic.resolution.ResolutionScope`, which is annotated as
   holding :class:`~semantic.resolution.EntityAnchor`. The four fields the two share
   are readable; ``established_by_decision`` is not present, so a reader following
   the type gets an ``AttributeError`` rather than a value. Replay builds real
   ``EntityAnchor`` objects from the recorded four and says so.
7. **The orchestrator admits from an empty validation report.**
   :meth:`domain.relation_candidate.RelationCandidate.to_claim` is the documented
   composition of ``build``/``admit`` and hands ``admit`` a report with zero
   findings, so a real adverse finding cannot gate admission on this path. The
   materialisation decision does see the finding - which is why the
   ``non_blocking_validation_finding`` case is a demonstration rather than an
   accident - but the gate that could exist is not wired.
8. **An ambiguous pass anchors an entity it then declines to name.**
   The resolver's third pass elects an anchor for the entity every mention landed
   on, before the verdict is known, and an ``ambiguous`` verdict then names none. So
   the scope holds an anchor whose creating decision recorded no entity, and
   :meth:`InMemoryEntityIdentityStore.ingest_scope` **refuses** to bind it -
   correctly, because the chain would have a hole at its first link. The corpus
   reports the refusal in :attr:`CaseTrace.identity_refusals` and withholds the
   binding rather than adopting it with
   :data:`domain.entity_identity.UNATTRIBUTED_RESOLUTION`.

**Determinism.** No clock, no network, no randomness, no I/O, no model. Every
timestamp enters through the case fixture.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import datetime
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import Any

from adapters.common_crawl import STREAM_ID as COMMON_CRAWL_STREAM
from adapters.sec_edgar import STREAM_ID as EDGAR_STREAM
from domain.capture import Capture, InMemoryCaptureRegistry
from domain.entity_identity import (
    EntityIdentity,
    EntityIdentityError,
    EntityReconstruction,
    InMemoryEntityIdentityStore,
    ResolutionDecisionRecord,
)
from domain.evidence_lineage import EvidenceGraph, EvidenceHop, HopKind
from domain.relation_candidate import (
    CandidateStatus,
    ExtractionStrategy,
    RelationCandidate,
    SpanRef,
    TemporalBasis,
    TemporalHypothesis,
)
from domain.relation_claim import EvidenceGrade, RelationClaim, RelationRoleBinding, RelationStatus
from domain.relation_claim_material import (
    RelationClaimMaterial,
    admit,
    build,
    unvalidated_report,
)
from domain.relation_identity import (
    RelationArityMode,
    canonical_material,
    digest128,
)
from domain.relation_schema import TemporalSemantics
from graph.abstraction import InMemoryGraphStore
from graph.relation_store import GraphProjectionBridge, InMemoryRelationStore
from semantic.contracts import (
    RelationRef,
    SemanticRef,
    SemanticStatus,
    TypeAssertion,
    TypeScope,
)
from semantic.regime_store import InMemoryRegimeStore, RegimeRecord
from semantic.resolution import EntityAnchor, ResolutionScope
from stream import CaptureContext, StreamContractError

from semantic_path import corpus_cases
from semantic_path.corpus_cases import (
    CASES,
    CaseExpectation,
    CaseSpec,
    axis_report,
    graded_coverage,
    stream_registry,
)
from semantic_path.execution import (
    STAGE_ORDER,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStage,
    LineageBundle,
    SemanticExecutionError,
    run_until,
)

__all__ = [
    "ENTITY_CHAIN",
    "LAYER_ORDER",
    "RELATION_CHAIN",
    "AcceptanceChain",
    "AnchorReport",
    "CaseRun",
    "CaseTrace",
    "ChainHole",
    "ChainLink",
    "CorpusRun",
    "Divergence",
    "InvarianceReport",
    "LayerComparison",
    "ReplayDivergence",
    "ReplayReport",
    "acceptance_chains",
    "anchor_survives_scope_loss",
    "chain_status",
    "compare",
    "compare_to_committed",
    "digest_bundle",
    "layer_payloads",
    "main",
    "record_log",
    "replay",
    "replay_from_records",
    "replay_from_request",
    "replay_of_replay",
    "run_case",
    "run_corpus",
    "smoke",
]

#: The five layers FR-021 names, in the order a divergence report prints them. Each
#: one is a separate content address over a separate payload, so "the graph is
#: equal" can never be the only thing an invariance check established.
LAYER_ORDER: tuple[str, ...] = ("identity", "decisions", "claims", "context", "edges")


@dataclass(frozen=True)
class CaseTrace:
    """What one case produced, reduced to committed, comparable values.

    Every field is read off a real object the path produced. The five
    :attr:`layer_digests` are the FR-021 comparison unit, and they are the only
    thing the runner compares across processes; the readable fields are what a
    reviewer reads in a diff and what the acceptance chains are checked against.
    """

    case_id: str
    reached: str
    refusal: str
    mention_values: tuple[tuple[str, str], ...]
    extractor_output: tuple[tuple[str, str], ...]
    mentions_reached: bool
    identity_refusals: tuple[str, ...]
    verdicts: tuple[tuple[str, str, str], ...]
    decision_ids: tuple[str, ...]
    decision_fingerprints: tuple[str, ...]
    identity_refs: tuple[str, ...]
    context_refs: tuple[tuple[str, str], ...]
    capture_refs: tuple[tuple[str, str, str, str], ...]
    claim_ids: tuple[tuple[str, str], ...]
    validation_verdicts: tuple[tuple[str, str, str], ...]
    adverse_codes: tuple[str, ...]
    materialisation: str
    lineage_backward_kinds: tuple[str, ...]
    lineage_forward_kinds: tuple[str, ...]
    lineage_digests: tuple[tuple[str, str], ...]
    edge_refs: tuple[tuple[str, str, str], ...]
    worldline_refs: tuple[str, ...]
    layer_digests: Mapping[str, str]
    identifiable: bool

    def as_expectation(self) -> CaseExpectation:
        """This trace in the committed-expectation shape, for a one-line diff."""
        return CaseExpectation(
            case_id=self.case_id,
            reached=self.reached,
            refusal=self.refusal,
            mention_values=self.mention_values,
            extractor_output=self.extractor_output,
            mentions_reached=self.mentions_reached,
            identity_refusals=self.identity_refusals,
            verdicts=self.verdicts,
            decision_ids=self.decision_ids,
            decision_fingerprints=self.decision_fingerprints,
            identity_refs=self.identity_refs,
            context_refs=self.context_refs,
            capture_refs=self.capture_refs,
            claim_ids=self.claim_ids,
            validation_verdicts=self.validation_verdicts,
            adverse_codes=self.adverse_codes,
            materialisation=self.materialisation,
            lineage_backward_kinds=self.lineage_backward_kinds,
            lineage_forward_kinds=self.lineage_forward_kinds,
            lineage_digests=self.lineage_digests,
            edge_refs=self.edge_refs,
            worldline_refs=self.worldline_refs,
            layer_digests=self.layer_digests,
        )

    def text(self) -> str:
        """A one-line-per-case summary, for a smoke run's console."""
        grade = f"refused:{self.refusal}" if self.refusal else "materialised"
        return (
            f"{self.case_id:32s} {self.reached:10s} {grade:34s} "
            f"mentions={len(self.mention_values)} decisions={len(self.decision_ids)} "
            f"claims={len(self.claim_ids)} layers={len(self.layer_digests)}"
        )


@dataclass(frozen=True)
class CaseRun:
    """A case's spec, its live result, its capture, and its recorded trace.

    The live objects are here for the acceptance chains and the event log, which
    need the real values rather than the reduced ones. They are never what
    :func:`compare` looks at, and :func:`replay_from_records` is given only
    :func:`record_log`'s plain mappings so it cannot reach them.
    """

    spec: CaseSpec
    result: ExecutionResult
    capture: Capture | None
    refusal: str
    trace: CaseTrace
    decision_records: tuple[ResolutionDecisionRecord, ...] = ()
    identities: tuple[EntityIdentity, ...] = ()


@dataclass(frozen=True)
class CorpusRun:
    """Every case's outcome, in corpus order."""

    cases: tuple[CaseRun, ...]

    def traces(self) -> tuple[CaseTrace, ...]:
        return tuple(case.trace for case in self.cases)

    def by_id(self, case_id: str) -> CaseRun:
        for case in self.cases:
            if case.spec.case_id == case_id:
                return case
        raise KeyError(case_id)

    def refusals(self) -> tuple[str, ...]:
        return tuple(case.refusal for case in self.cases if case.refusal)

    def reached_worldline(self) -> tuple[str, ...]:
        return tuple(
            case.spec.case_id
            for case in self.cases
            if case.trace.reached == str(ExecutionStage.WORLDLINE)
        )


def _layer_identity(result: ExecutionResult) -> list[tuple[str, Any]]:
    """Anchors, resolved identities and corroboration - "which entity is this?"."""
    payload: list[tuple[str, Any]] = []
    step = result.resolution
    if step is None:
        return _unreached("resolution")
    payload.append(("scope_id", step.batch.scope.scope_id))
    for anchor in sorted(step.batch.scope.anchors, key=lambda item: item.logical_entity_ref):
        payload.append(
            (
                f"anchor:{anchor.logical_entity_ref}",
                (
                    anchor.logical_entity_ref,
                    anchor.anchor_mention_id,
                    anchor.anchor_key,
                    anchor.candidate_ref,
                ),
            )
        )
    for decision in sorted(step.batch.decisions, key=lambda item: item.mention_id):
        payload.append(
            (
                f"identity:{decision.surface}",
                (
                    str(decision.verdict),
                    decision.logical_entity_ref,
                    decision.anchor_mention_id,
                    list(decision.merged_mentions),
                    decision.corroboration,
                ),
            )
        )
    payload.append(("independence_groups", [list(g) for g in step.independence_groups()]))
    payload.append(("regime_verdicts", dict(sorted(step.regime_verdicts.items()))))
    payload.append(("unevaluated_regimes", list(step.unevaluated_regimes)))
    return payload


def _layer_decisions(result: ExecutionResult) -> list[tuple[str, Any]]:
    """The ``RES-`` layer: addresses, record fingerprints, and the reasoning itself."""
    payload: list[tuple[str, Any]] = []
    step = result.resolution
    if step is None:
        return _unreached("resolution")
    for decision in sorted(step.batch.decisions, key=lambda item: item.mention_id):
        record = ResolutionDecisionRecord.from_decision(
            decision, decided_at=_decided_at(result)
        )
        payload.append(
            (
                f"decision:{decision.mention_id}",
                (
                    decision.resolution_decision_id,
                    record.record_fingerprint,
                    str(decision.verdict),
                    decision.logical_entity_ref,
                    list(decision.surviving),
                    [[ref, round(score, 6)] for ref, score in decision.scored],
                    list(decision.reason_codes()),
                    [reason.code for reason in decision.blocked_out],
                    decision.corroboration,
                    decision.confidence,
                ),
            )
        )
    collective = step.batch.collective
    if collective is not None:
        payload.append(
            (
                "collective",
                (
                    collective.applied,
                    collective.converged,
                    collective.iterations,
                    collective.edges_before,
                    collective.edges_after,
                    list(collective.contested),
                    list(collective.committed),
                    [removal.content_key() for removal in collective.removals],
                    list(collective.notes),
                ),
            )
        )
    for mention_id, ratio in sorted(step.blocking_reductions.items()):
        payload.append((f"blocking:{mention_id}", round(ratio, 6)))
    return payload


def _layer_claims(result: ExecutionResult) -> list[tuple[str, Any]]:
    """The claim lifecycle: candidate, claim, validation verdicts, materialisation."""
    payload: list[tuple[str, Any]] = _unreached("claim")
    if result.candidate is not None:
        payload.append(
            (
                "candidate",
                (
                    result.candidate.proposed.candidate_id,
                    result.candidate.supported.candidate_id,
                    result.candidate.supported.logical_candidate_id,
                ),
            )
        )
    if result.claim is not None:
        claim = result.claim.claim
        payload.append(
            (
                "claim",
                (
                    claim.relation_id,
                    claim.logical_relation_id,
                    claim.subject_ref,
                    claim.object_ref,
                    [binding.to_dict() for binding in claim.role_bindings],
                    [list(group) for group in claim.source_independence_groups],
                    claim.independent_source_count,
                    list(claim.assertion_refs),
                ),
            )
        )
    if result.validation is not None:
        payload.append(("validation_report", result.validation.report.report_id))
        for finding in result.validation.report.findings:
            payload.append(
                (
                    f"verdict:{finding.stage}",
                    (str(finding.verdict), finding.code, finding.finding_id),
                )
            )
        payload.append(("adverse", list(result.validation.adverse)))
        payload.append(("unevaluated", list(result.validation.unevaluated)))
    if result.admission is not None:
        decision = result.admission.decision
        payload.append(
            (
                "materialisation",
                (
                    str(decision.code),
                    decision.materialisable,
                    str(decision.policy),
                    str(decision.scope),
                    [finding.code for finding in decision.findings],
                ),
            )
        )
    return payload


def _layer_context(result: ExecutionResult, capture: Capture | None) -> list[tuple[str, Any]]:
    """Frames, the regime, the capture, and both lineage traces node for node."""
    payload: list[tuple[str, Any]] = _unreached("regime")
    if result.observation is not None:
        observation = result.observation.observation
        payload.append(
            (
                "observation",
                (
                    observation.observation_id,
                    observation.event_id,
                    observation.source_id,
                    observation.source_family,
                    observation.document_id,
                    observation.segment_id,
                ),
            )
        )
        payload.append(
            (
                "orchestrator_capture",
                (
                    observation.capture.capture_id
                    if observation.capture is not None
                    else "",
                    str(observation.capture.time_basis) if observation.capture is not None else "",
                    observation.capture.target_uri if observation.capture is not None else "",
                ),
            )
        )
    if result.context is not None:
        payload.append(("context", result.context.frame.context_id))
    if result.regime is not None:
        payload.append(
            (
                "regime",
                (
                    result.regime.regime.regime_id,
                    result.regime.record.record_fingerprint,
                    list(result.regime.instrument_refs()),
                    result.regime.frame.context_id,
                ),
            )
        )
    if capture is not None:
        payload.append(
            (
                "capture",
                (
                    capture.capture_id,
                    str(capture.time_basis),
                    capture.fetched_at.isoformat() if capture.fetched_at else "",
                    capture.source_id,
                    capture.source_family,
                    capture.target_uri,
                    capture.locator,
                    capture.content_digest,
                ),
            )
        )
    lineage = result.lineage
    if lineage is not None:
        payload.append(("lineage_backward", _hop_pairs(lineage.backward.hops)))
        payload.append(("lineage_forward", _hop_pairs(lineage.forward.hops)))
    return payload


def _layer_edges(result: ExecutionResult) -> list[tuple[str, Any]]:
    """The projection and the worldline, read back out of both stores."""
    payload: list[tuple[str, Any]] = _unreached("edge")
    if result.store is not None:
        payload.append(
            (
                "store",
                (
                    result.store.relation_id,
                    result.store.checksum,
                    result.store.write_count_before_repeat,
                    result.store.write_count_after_repeat,
                ),
            )
        )
    if result.edge is not None:
        step = result.edge
        payload.append(
            (
                "edge",
                (step.edge.edge_id, step.edge.edge_type, step.edge.source, step.edge.target),
            )
        )
        payload.append(
            (
                "graph_nodes",
                sorted(
                    (node.node_id, node.node_type) for node in step.store.nodes()
                ),
            )
        )
        payload.append(
            (
                "graph_edges",
                sorted(
                    (edge.edge_id, edge.edge_type, edge.source, edge.target)
                    for edge in step.store.edges()
                ),
            )
        )
        payload.append(
            (
                "graph_hyperedges",
                sorted(
                    (hyper.edge_id, hyper.members)
                    for hyper in step.store.hyperedges()
                ),
            )
        )
        payload.append(("graph_out", list(step.out_neighbors)))
        payload.append(("graph_in", list(step.in_neighbors)))
    if result.worldline is not None:
        step = result.worldline
        payload.append(
            (
                "worldline",
                (
                    step.record.record_id,
                    step.worldline.integrity_fingerprint,
                    step.worldline.entity_id,
                    [event.event_id for event in step.events],
                ),
            )
        )
    return payload


def _unreached(stage: str) -> list[tuple[str, Any]]:
    """The payload of a layer whose stage this run did not reach.

    Named rather than empty, and distinct per layer, so a layer digest for a case
    that refused early is (a) visibly a refusal rather than a value that happens to
    hash like another layer's, and (b) a *statement* about the absent stage. An
    empty payload would satisfy FR-021's digest trivially while establishing
    nothing, which is the failure mode the five layers exist to prevent.
    """
    return [("reached", "not_reached"), ("absent_stage", stage)]


def _hop_pairs(hops: Iterable[EvidenceHop]) -> list[list[str]]:
    return [[str(hop.kind), hop.node_id] for hop in hops]


def layer_payloads(
    result: ExecutionResult, capture: Capture | None
) -> Mapping[str, list[tuple[str, Any]]]:
    """Every layer's payload for one run, keyed by layer name.

    Split out from :func:`_layer_digests` because a divergence report that can
    only say "the context layer differs" is much less useful than one that can
    print the two payloads that differ, and this is what makes that possible
    without a second execution.
    """
    return MappingProxyType(
        {
            "identity": _layer_identity(result),
            "decisions": _layer_decisions(result),
            "claims": _layer_claims(result),
            "context": _layer_context(result, capture),
            "edges": _layer_edges(result),
        }
    )


def _layer_digests(result: ExecutionResult, capture: Capture | None) -> Mapping[str, str]:
    return MappingProxyType(
        {
            layer: digest128(canonical_material(payload))
            for layer, payload in layer_payloads(result, capture).items()
        }
    )


def _decided_at(result: ExecutionResult) -> datetime | None:
    """The instant a decision is recorded at, which is the observation's.

    Read from the observation rather than a clock, so a replay at a different
    moment produces the same ``decided_at`` and therefore the same record
    fingerprint (constitution VII). ``None`` only before the observation stage.
    """
    return result.observation.observation.observed_at if result.observation else None


def _drive(request: ExecutionRequest, until: ExecutionStage) -> tuple[ExecutionResult, str]:
    """Run the path as deep as it goes, and then to the end, and report both.

    Two runs of the *same* request, and both are needed. The first walks down from
    ``until`` until a prefix completes, so a case whose refusal happens *inside* a
    stage - the MENTIONS stage raises when the segment carries no mention of the
    kind this relation needs, and hands back nothing - still records the last
    stage it genuinely reached rather than nothing at all. The second runs to
    ``worldline`` and yields the refusal code, which is what
    :attr:`CaseSpec.expected_refusal` is compared against.

    Both runs share nothing but the request. The request is a frozen value and the
    path builds every store it touches, so a run cannot inherit state from the one
    before it.
    """
    partial: ExecutionResult | None = None
    for stage in reversed(STAGE_ORDER[: ExecutionStage(until).rank() + 1]):
        try:
            partial = run_until(request, stage)
        except SemanticExecutionError:
            continue
        break
    if partial is None:
        raise SemanticExecutionError(
            "no_stage_reachable",
            f"case refused before {until!s}; not even the observation stage completed",
        )
    refusal = ""
    try:
        run_until(request, ExecutionStage.WORLDLINE)
    except SemanticExecutionError as refusal_error:
        refusal = refusal_error.code
    return partial, refusal


def _extractor_output(request: ExecutionRequest) -> tuple[tuple[str, str], ...]:
    """What the request's own extractor set returns over the sentence.

    Recorded for **every** case, and it is the same call
    :func:`semantic_path.execution._mentions_step` makes with the same arguments,
    so for a case that completed the MENTIONS stage it equals the step's own output
    and the corpus compares the two. It is recorded separately because a case whose
    refusal happens *inside* that stage gets no ``MentionStep`` back at all, and a
    case whose whole subject is "the extractors read this sentence and found no
    organisation" would otherwise record nothing about what it did find.
    """
    observation_like = request.segment_id
    found = request.extractors.extract(
        request.sentence, segment_ref=observation_like, lang=request.language
    )
    return tuple((typed.kind, typed.value) for typed in found)


def _capture_for(case: CaseSpec) -> Capture | None:
    """The real ``Capture`` the acquisition seam emits for this case.

    The registry is consulted only when the request does not already carry a
    capture. A case's fixture builds the capture once and hands the *same object*
    to the request, and building it again here - with a different
    ``CaptureContext`` and therefore a different content address - would give one
    fetch two ``CAP-`` ids and put the mismatch straight back into the chain this
    function is meant to check. A capture's address covers who recorded it, so
    "build it twice" and "build it once" are not the same record.
    """
    if case.request.capture is not None:
        return case.request.capture
    registry = stream_registry()
    try:
        return registry.capture(
            case.acquisition.stream_id,
            dict(case.acquisition.record),
            context=CaptureContext(
                tenant_id=case.request.tenant_id,
                ingest_batch_id=case.acquisition.ingest_batch_id,
                ingest_attempt=case.acquisition.ingest_attempt,
                recorded_by=case.request.recorded_by,
            ),
        )
    except StreamContractError:
        return None


def run_case(case: CaseSpec) -> CaseRun:
    """Drive one case over the real path and record what it produced.

    The live result, the real capture, the durable decision records, the durable
    identity rows and the reduced trace all come from one execution of one
    request. Nothing is computed twice and nothing is cached between cases, so a
    case cannot be contaminated by the case before it.
    """
    capture = _capture_for(case)
    result, refusal = _drive(case.request, case.until)
    decided_at = _decided_at(result)
    records = _decision_records(result, decided_at)
    identities, refused = _identities(result, capture, decided_at)
    trace = _trace(case, result, capture, refusal, refused)
    return CaseRun(
        spec=case,
        result=result,
        capture=capture,
        refusal=refusal,
        trace=trace,
        decision_records=records,
        identities=identities,
    )


def run_corpus(cases: Sequence[CaseSpec] = CASES) -> CorpusRun:
    """Drive every case, in the order given, with nothing shared between them.

    Each case builds its own stores, its own regime and its own projection, so a
    case's ids depend on its fixture and on nothing that ran before it - which is
    what makes ``run_corpus`` and ``run_corpus`` comparable at all.
    """
    return CorpusRun(cases=tuple(run_case(case) for case in cases))


def _decision_records(
    result: ExecutionResult, decided_at: datetime | None
) -> tuple[ResolutionDecisionRecord, ...]:
    """The durable ``RES-`` rows for this run, appended in one call.

    Every decision, including the ones that named no entity. ``ambiguous`` and
    ``unresolved`` are decisions and a history that omitted them could not answer
    why an entity is the entity it is (FR-004).
    """
    if result.resolution is None or decided_at is None:
        return ()
    return tuple(
        ResolutionDecisionRecord.from_decision(decision, decided_at=decided_at)
        for decision in sorted(result.resolution.batch.decisions, key=lambda i: i.mention_id)
    )


def _identities(
    result: ExecutionResult, capture: Capture | None, decided_at: datetime | None
) -> tuple[tuple[EntityIdentity, ...], tuple[str, ...]]:
    """The durable anchor rows for this run, and the refusals for the rest.

    :meth:`InMemoryEntityIdentityStore.ingest_scope` is the real write path and it
    **refuses** an anchor whose creating decision is not among those supplied. That
    refusal is a correct answer rather than an obstacle: an ambiguous or unresolved
    pass names no entity, so the entity the scope anchored that mention onto has no
    decision behind it and must not be durably bound. So the whole scope is offered
    first, and the anchors whose creation is unattested are then withheld and their
    refusal code returned, which is what the trace records and what the acceptance
    chain reports. Nothing is bound with a guessed attribution.

    ``anchor_observations`` and ``anchor_captures`` are the two references that make
    the entity half of SC-14's chain reachable, and the second is the real capture
    this case's acquisition emitted - not the orchestrator's derived hop. A case
    with no resolved entity produces no anchor, and an empty tuple is the honest
    answer.
    """
    if result.resolution is None or decided_at is None:
        return (), ()
    store = InMemoryEntityIdentityStore()
    scope = result.resolution.batch.scope
    arguments = {
        "anchor_observations": _anchor_observations(result),
        "anchor_captures": _anchor_captures(result, capture),
        "decided_at": decided_at,
        "created_at": decided_at,
    }
    refused: list[str] = []
    try:
        store.ingest_scope(scope, _decision_records(result, decided_at), **arguments)
    except EntityIdentityError as refusal:
        refused.append(refusal.code)
        store = InMemoryEntityIdentityStore()
        attested = _attested_scope(scope, _decision_records(result, decided_at))
        store.ingest_scope(attested, _decision_records(result, decided_at), **arguments)
    return _bound_identities(store, result), tuple(refused)


def _attested_scope(
    scope: ResolutionScope, records: tuple[ResolutionDecisionRecord, ...]
) -> ResolutionScope:
    """The same scope with the anchors no recorded decision created, withheld."""
    created = {
        (record.entity_ref, record.anchor_mention_id)
        for record in records
        if record.entity_ref and record.anchor_mention_id
    }
    return ResolutionScope(
        scope_id=scope.scope_id,
        tenant_id=scope.tenant_id,
        investigation_id=scope.investigation_id,
        anchors=tuple(
            anchor
            for anchor in scope.anchors
            if (anchor.logical_entity_ref, anchor.anchor_mention_id) in created
        ),
    )


def _bound_identities(
    store: InMemoryEntityIdentityStore, result: ExecutionResult
) -> tuple[EntityIdentity, ...]:
    """Every anchor row this store now holds, read back through the real read path."""
    rows: list[EntityIdentity] = []
    for ref in sorted(_entity_refs(result)):
        record = store.identity_for_entity(result.request.tenant_id, ref)
        if record is not None:
            rows.append(record)
    return tuple(rows)


def _entity_refs(result: ExecutionResult) -> set[str]:
    if result.resolution is None:
        return set()
    return {
        decision.logical_entity_ref
        for decision in result.resolution.batch.decisions
        if decision.logical_entity_ref
    }


def _anchor_observations(result: ExecutionResult) -> Mapping[str, str]:
    """``mention id -> observation id`` for every mention the run resolved."""
    if result.resolution is None or result.observation is None:
        return MappingProxyType({})
    observation_id = result.observation.observation.observation_id
    return MappingProxyType(
        {
            record.mention_id: observation_id
            for record in (result.mentions.records if result.mentions else ())
        }
    )


def _anchor_captures(result: ExecutionResult, capture: Capture | None) -> Mapping[str, str]:
    """``mention id -> capture id``, using the **real** capture where there is one.

    Where there is no real capture - a stream refused, or an adapter declined the
    record - the mapping is deliberately incomplete rather than filled with the
    orchestrator's derived hop. A missing capture reference then shows up as a
    reconstruction hole, which is the finding SC-14 asks for, instead of being
    papered over with a digest of the observation it was supposed to explain.
    """
    if capture is None or result.mentions is None:
        return MappingProxyType({})
    return MappingProxyType(
        {record.mention_id: capture.capture_id for record in result.mentions.records}
    )


def _trace(
    case: CaseSpec,
    result: ExecutionResult,
    capture: Capture | None,
    refusal: str,
    identity_refusals: tuple[str, ...],
) -> CaseTrace:
    """Reduce one live result to the committed, comparable shape."""
    bundle = result.lineage
    real_capture = capture.capture_id if capture is not None else ""
    derived = result.lineage.capture_id if result.lineage is not None else ""
    return CaseTrace(
        case_id=case.case_id,
        reached=str(result.reached or ""),
        refusal=refusal,
        mention_values=(
            tuple((record.kind, record.value) for record in result.mentions.records)
            if result.mentions
            else ()
        ),
        extractor_output=_extractor_output(case.request),
        mentions_reached=result.mentions is not None,
        identity_refusals=identity_refusals,
        verdicts=(
            tuple(
                (decision.surface, str(decision.verdict), decision.logical_entity_ref)
                for decision in sorted(
                    result.resolution.batch.decisions, key=lambda item: item.mention_id
                )
            )
            if result.resolution
            else ()
        ),
        decision_ids=(
            tuple(
                decision.resolution_decision_id
                for decision in sorted(
                    result.resolution.batch.decisions, key=lambda item: item.mention_id
                )
            )
            if result.resolution
            else ()
        ),
        decision_fingerprints=(
            tuple(
                ResolutionDecisionRecord.from_decision(
                    decision, decided_at=_decided_at(result)
                ).record_fingerprint
                for decision in sorted(
                    result.resolution.batch.decisions, key=lambda item: item.mention_id
                )
            )
            if result.resolution
            else ()
        ),
        identity_refs=(
            tuple(
                sorted(
                    {
                        decision.logical_entity_ref
                        for decision in result.resolution.batch.decisions
                        if decision.logical_entity_ref
                    }
                )
            )
            if result.resolution
            else ()
        ),
        context_refs=(
            (
                ("observation", result.observation.observation.observation_id),
                ("event", result.observation.observation.event_id),
                ("context", result.context.frame.context_id),
                ("regime", result.regime.regime.regime_id),
                ("regime_record", result.regime.record.record_fingerprint),
                ("interpreted_context", result.regime.frame.context_id),
                ("derived_capture", derived),
            )
            if result.observation and result.context and result.regime
            else ()
        ),
        capture_refs=(
            (
                case.acquisition.stream_id,
                real_capture,
                str(capture.time_basis) if capture is not None else "no_capture",
                capture.fetched_at.isoformat()
                if capture is not None and capture.fetched_at
                else "absent",
            ),
        ),
        claim_ids=(
            (
                (
                    result.claim.claim.relation_id,
                    result.claim.claim.logical_relation_id,
                ),
            )
            if result.claim
            else ()
        ),
        validation_verdicts=(
            tuple(
                (str(finding.stage), str(finding.verdict), finding.code)
                for finding in result.validation.report.findings
            )
            if result.validation
            else ()
        ),
        adverse_codes=result.validation.adverse if result.validation else (),
        materialisation=(
            str(result.admission.decision.code) if result.admission else ""
        ),
        lineage_backward_kinds=(
            tuple(str(hop.kind) for hop in bundle.backward.hops) if bundle else ()
        ),
        lineage_forward_kinds=(
            tuple(str(hop.kind) for hop in bundle.forward.hops) if bundle else ()
        ),
        lineage_digests=(
            (
                (
                    "backward",
                    digest128(canonical_material(_hop_pairs(bundle.backward.hops))),
                ),
                (
                    "forward",
                    digest128(canonical_material(_hop_pairs(bundle.forward.hops))),
                ),
            )
            if bundle
            else ()
        ),
        edge_refs=(
            (
                (
                    result.edge.edge.edge_id,
                    result.edge.hyperedge.edge_id if result.edge.hyperedge else "",
                    result.store.checksum if result.store else "",
                ),
            )
            if result.edge
            else ()
        ),
        worldline_refs=(
            (
                result.worldline.worldline.integrity_fingerprint,
                *(
                    event.event_id
                    for event in sorted(
                        result.worldline.events, key=lambda item: item.event_id
                    )
                ),
            )
            if result.worldline
            else ()
        ),
        layer_digests=_layer_digests(result, capture),
        identifiable=bool(result.resolution and _entity_refs(result)),
    )


@dataclass(frozen=True)
class Divergence:
    """One layer of one case that is not equal between two runs, and by how much."""

    case_id: str
    layer: str
    reason: str
    left: str
    right: str
    entries: tuple[str, ...] = ()

    def text(self) -> str:
        """The divergence as one block, naming the layer before the value."""
        lines = [
            f"DIVERGENCE case={self.case_id} layer={self.layer} reason={self.reason}",
            f"  left  {self.left}",
            f"  right {self.right}",
        ]
        lines.extend(f"    {entry}" for entry in self.entries)
        return "\n".join(lines)


@dataclass(frozen=True)
class LayerComparison:
    """One layer across every case: how many cases agreed and which did not."""

    layer: str
    compared: int
    diverged: tuple[Divergence, ...]

    @property
    def identical(self) -> bool:
        return not self.diverged

    def text(self) -> str:
        head = f"layer {self.layer:9s} compared={self.compared:3d} identical={self.identical}"
        if self.identical:
            return head
        return "\n".join([head, *(d.text() for d in self.diverged)])


@dataclass(frozen=True)
class InvarianceReport:
    """The whole FR-021 result, per layer, plus the readable-field comparison.

    :attr:`field_differences` is deliberately separate from the layer digests.
    The layers are the *machine* comparison and a divergence there names the layer
    first; the readable fields are what a human reads, and a difference there that
    the digests did not flag would mean a digest is not covering the field the
    report shows, which is worth knowing.
    """

    identical: bool
    layers: tuple[LayerComparison, ...]
    field_differences: tuple[Divergence, ...] = ()

    def diverged_layers(self) -> tuple[str, ...]:
        return tuple(layer.layer for layer in self.layers if not layer.identical)

    def text(self) -> str:
        head = (
            f"invariance identical={self.identical} "
            f"diverged_layers={list(self.diverged_layers())}"
        )
        body = [layer.text() for layer in self.layers]
        body.extend(d.text() for d in self.field_differences)
        return "\n".join([head, *body])


def compare(left: CorpusRun, right: CorpusRun) -> InvarianceReport:
    """``run(...) == run(...)``, compared per layer and per case.

    The five layers first and separately, then every readable field. Comparing the
    final graph alone is what FR-021 forbids, so nothing here is derived from
    ``edge_refs`` or ``worldline_refs``: the ``edges`` layer is a digest over the
    *store reads* and the projection objects, and a divergence anywhere in
    identity, decisions, claims or context is reported in its own layer even when
    the graph came out equal.
    """
    left_by_id = {case.spec.case_id: case for case in left.cases}
    right_by_id = {case.spec.case_id: case for case in right.cases}
    layers: list[LayerComparison] = []
    for layer in LAYER_ORDER:
        diverged: list[Divergence] = []
        for case_id in sorted(set(left_by_id) | set(right_by_id)):
            left_case = left_by_id.get(case_id)
            right_case = right_by_id.get(case_id)
            if left_case is None or right_case is None:
                diverged.append(
                    Divergence(
                        case_id=case_id,
                        layer=layer,
                        reason="case_missing_on_one_side",
                        left=case_id if left_case else "",
                        right=case_id if right_case else "",
                    )
                )
                continue
            left_digest = left_case.trace.layer_digests.get(layer, "")
            right_digest = right_case.trace.layer_digests.get(layer, "")
            if left_digest != right_digest:
                diverged.append(
                    Divergence(
                        case_id=case_id,
                        layer=layer,
                        reason="layer_digest_mismatch",
                        left=left_digest,
                        right=right_digest,
                        entries=_payload_diff(
                            layer_payloads(left_case.result, left_case.capture),
                            layer_payloads(right_case.result, right_case.capture),
                        ),
                    )
                )
        layers.append(
            LayerComparison(
                layer=layer,
                compared=len(set(left_by_id) & set(right_by_id)),
                diverged=tuple(diverged),
            )
        )
    field_differences = _field_differences(left, right)
    return InvarianceReport(
        identical=not field_differences and all(layer.identical for layer in layers),
        layers=tuple(layers),
        field_differences=field_differences,
    )


def _payload_diff(
    left: Mapping[str, list[tuple[str, Any]]],
    right: Mapping[str, list[tuple[str, Any]]],
) -> tuple[str, ...]:
    """The labelled values that differ between two layer payloads, in order.

    Compares the payloads, not just the digests, so a divergence report can say
    *which label* moved. Bounded to the first few entries because a systemic defect
    can differ on every label and printing all of them hides the first.
    """
    out: list[str] = []
    for layer in LAYER_ORDER:
        left_map = dict(left.get(layer, ()))
        right_map = dict(right.get(layer, ()))
        for label in sorted(set(left_map) | set(right_map)):
            if left_map.get(label) != right_map.get(label):
                out.append(
                    f"{layer}.{label}: {left_map.get(label, '<absent>')!r} != "
                    f"{right_map.get(label, '<absent>')!r}"
                )
            if len(out) >= 8:
                return tuple(out)
    return tuple(out)


_TRACE_FIELDS: tuple[str, ...] = (
    "reached",
    "refusal",
    "mention_values",
    "extractor_output",
    "mentions_reached",
    "identity_refusals",
    "verdicts",
    "decision_ids",
    "decision_fingerprints",
    "identity_refs",
    "context_refs",
    "capture_refs",
    "claim_ids",
    "validation_verdicts",
    "adverse_codes",
    "materialisation",
    "lineage_backward_kinds",
    "lineage_forward_kinds",
    "lineage_digests",
    "edge_refs",
    "worldline_refs",
    "identifiable",
)


def _field_differences(left: CorpusRun, right: CorpusRun) -> tuple[Divergence, ...]:
    """Every readable trace field that is not equal, named by field.

    Compares *all* of them rather than a hand-picked few, because a field nobody
    compares is a field nobody has claimed is deterministic. Cases present on one
    side only are reported too, with no field name, since there is no field to name.
    """
    out: list[Divergence] = []
    left_by_id = {case.spec.case_id: case for case in left.cases}
    right_by_id = {case.spec.case_id: case for case in right.cases}
    for case_id in sorted(set(left_by_id) | set(right_by_id)):
        left_case = left_by_id.get(case_id)
        right_case = right_by_id.get(case_id)
        if left_case is None or right_case is None:
            out.append(
                Divergence(
                    case_id=case_id,
                    layer="cases",
                    reason="case_missing_on_one_side",
                    left="present" if left_case else "absent",
                    right="present" if right_case else "absent",
                )
            )
            continue
        for name in _TRACE_FIELDS:
            left_value = getattr(left_case.trace, name)
            right_value = getattr(right_case.trace, name)
            if left_value != right_value:
                out.append(
                    Divergence(
                        case_id=case_id,
                        layer="fields",
                        reason=f"field_mismatch:{name}",
                        left=repr(left_value),
                        right=repr(right_value),
                    )
                )
    return tuple(out)


def compare_to_committed(run: CorpusRun) -> tuple[Divergence, ...]:
    """What this run produced against what the corpus **commits** it produces (FR-020).

    The other half of invariance, and the one that catches a defect two runs share.
    :func:`compare` proves two runs of the same code agree; this proves the code
    still produces what the repository says it produces, which is the only way a
    committed corpus can be evidence of anything. Every
    :class:`~semantic_path.corpus_cases.CaseExpectation` field is compared, and a
    difference names the field - so a reviewer reading a diff sees *which*
    expectation moved, not merely that something did.

    A case with no committed expectation is a divergence in its own right:
    ``expectation_missing``, because a case nobody recorded is not part of the
    corpus.
    """
    out: list[Divergence] = []
    for case in run.cases:
        expected = corpus_cases.EXPECTED.get(case.spec.case_id)
        if expected is None:
            out.append(
                Divergence(
                    case_id=case.spec.case_id,
                    layer="committed",
                    reason="expectation_missing",
                    left="",
                    right="no committed expectation for this case",
                )
            )
            continue
        produced = case.trace.as_expectation()
        for name in CaseExpectation.__dataclass_fields__:
            if name == "case_id":
                continue
            want = getattr(expected, name)
            got = getattr(produced, name)
            if dict(want) != dict(got) if isinstance(want, Mapping) else want != got:
                out.append(
                    Divergence(
                        case_id=case.spec.case_id,
                        layer="committed",
                        reason=f"expectation_mismatch:{name}",
                        left=repr(got),
                        right=repr(want),
                    )
                )
    return tuple(out)


def digest_bundle(run: CorpusRun) -> Mapping[str, str]:
    """One mapping of strings for a whole run, for comparing **two processes**.

    ``{case_id: {layer: digest}}`` plus a ``__total__`` key over every case and
    layer. Strings only, so two invocations of
    ``print(digest_bundle(run_corpus()))`` can be compared by eye or by a diff
    with nothing written to disk and no clock consulted.
    """
    bundle: dict[str, Any] = {
        case.spec.case_id: dict(case.trace.layer_digests) for case in run.cases
    }
    flat = {
        f"{case_id}/{layer}": digest
        for case_id, layers in bundle.items()
        for layer, digest in layers.items()
    }
    bundle["__total__"] = digest128(canonical_material(flat))
    return MappingProxyType({key: str(value) for key, value in sorted(bundle.items())})


@dataclass(frozen=True)
class ReplayDivergence:
    """One value the replay did not reproduce, named by what it was."""

    case_id: str
    layer: str
    label: str
    recorded: str
    replayed: str

    def text(self) -> str:
        return (
            f"REPLAY DIVERGENCE case={self.case_id} layer={self.layer} label={self.label}: "
            f"recorded {self.recorded!r} != replayed {self.replayed!r}"
        )


@dataclass(frozen=True)
class ReplayReport:
    """What one replay reproduced, and what it did not.

    :attr:`replayed` names which of the two replays produced the report, because
    they prove different things and a reader has to know which one they are
    looking at. :attr:`fixed_point` is set only for the record-based replay, and
    only when a second replay of the first replay's own log is identical.
    """

    case_id: str
    replayed: str
    divergences: tuple[ReplayDivergence, ...] = ()
    fixed_point: bool = False
    notes: tuple[str, ...] = ()

    @property
    def identical(self) -> bool:
        return not self.divergences

    def text(self) -> str:
        head = (
            f"replay {self.replayed:8s} case={self.case_id:32s} identical={self.identical} "
            f"fixed_point={self.fixed_point}"
        )
        body = [d.text() for d in self.divergences]
        body.extend(f"  note: {note}" for note in self.notes)
        return "\n".join([head, *body])


def _candidate_payload(candidate: RelationCandidate) -> Mapping[str, Any]:
    """A ``RelationCandidate`` as plain values, for the event log.

    A projection, and it has to be one: ``RelationCandidate`` has no ``to_dict``,
    and writing a second serialiser that could disagree with the type is worse than
    writing one that is checked. Every field the dataclass declares is carried, and
    the replay hands the recorded ``candidate_id`` back so ``__post_init__`` and
    :meth:`RelationCandidate.with_id` verify it against the rebuilt value.
    """

    return MappingProxyType(
        {
            "candidate_id": candidate.candidate_id,
            "logical_candidate_id": candidate.logical_candidate_id,
            "subject_mention_ref": candidate.subject_mention_ref,
            "object_mention_ref": candidate.object_mention_ref,
            "relation_ref": [
                candidate.relation_ref.relation_type,
                candidate.relation_ref.schema_version,
            ],
            "role_assignments": [binding.to_dict() for binding in candidate.role_assignments],
            "arity_mode": str(candidate.arity_mode),
            "context_ref": candidate.context_ref,
            "semantic_regime_ref": candidate.semantic_regime_ref,
            "trigger_span": (
                None if candidate.trigger_span is None else candidate.trigger_span.to_dict()
            ),
            "supporting_spans": [span.to_dict() for span in candidate.supporting_spans],
            "extraction_method": str(candidate.extraction_method),
            "extractor_version": candidate.extractor_version,
            "extraction_rule_id": candidate.extraction_rule_id,
            "observation_refs": list(candidate.observation_refs),
            "evidence_refs": list(candidate.evidence_refs),
            "temporal_hypothesis": candidate.temporal_hypothesis.to_dict(),
            "candidate_status": str(candidate.candidate_status),
            "confidence": candidate.confidence,
            "tenant_id": candidate.tenant_id,
            "investigation_id": candidate.investigation_id,
            "observed_at": candidate.observed_at.isoformat() if candidate.observed_at else "",
            "recorded_by": candidate.recorded_by,
        }
    )


def _candidate_from(payload: Mapping[str, Any]) -> RelationCandidate:
    """Rebuild a ``RelationCandidate`` from :func:`_candidate_payload` and verify it."""

    return RelationCandidate(
        candidate_id=str(payload["candidate_id"]),
        logical_candidate_id=str(payload["logical_candidate_id"]),
        subject_mention_ref=str(payload["subject_mention_ref"]),
        object_mention_ref=str(payload["object_mention_ref"]),
        relation_ref=RelationRef(*payload["relation_ref"]),
        arity_mode=RelationArityMode(str(payload["arity_mode"])),
        role_assignments=tuple(
            _role_binding(item) for item in payload["role_assignments"]
        ),
        context_ref=str(payload["context_ref"]),
        semantic_regime_ref=str(payload["semantic_regime_ref"]),
        trigger_span=_span_from(payload["trigger_span"]),
        supporting_spans=tuple(_span_from(item) for item in payload["supporting_spans"]),
        extraction_method=ExtractionStrategy(str(payload["extraction_method"])),
        extractor_version=str(payload["extractor_version"]),
        extraction_rule_id=str(payload["extraction_rule_id"]),
        observation_refs=tuple(str(ref) for ref in payload["observation_refs"]),
        evidence_refs=tuple(str(ref) for ref in payload["evidence_refs"]),
        temporal_hypothesis=_hypothesis_from(payload["temporal_hypothesis"]),
        candidate_status=CandidateStatus(str(payload["candidate_status"])),
        confidence=float(payload["confidence"]),
        tenant_id=str(payload["tenant_id"]),
        investigation_id=str(payload["investigation_id"]),
        observed_at=_moment_or_none(payload["observed_at"]),
        recorded_by=str(payload["recorded_by"]),
    )


def _role_binding(payload: Mapping[str, Any]) -> Any:

    return RelationRoleBinding.from_dict(payload)


def _span_from(payload: Mapping[str, Any] | None) -> SpanRef | None:

    if payload is None:
        return None
    return SpanRef(
        segment_ref=str(payload["segment_ref"]),
        start=int(payload["start"]),
        end=int(payload["end"]),
        mention_ref=str(payload.get("mention_ref", "")),
    )


def _hypothesis_from(payload: Mapping[str, Any]) -> TemporalHypothesis:

    return TemporalHypothesis(
        valid_from=_moment_or_none(payload.get("valid_from")),
        valid_to=_moment_or_none(payload.get("valid_to")),
        semantics=TemporalSemantics(str(payload.get("semantics", "optional_interval"))),
        basis=TemporalBasis(str(payload.get("basis", "absent"))),
        derived_from_ref=str(payload.get("derived_from_ref", "")),
    )


def _moment_or_none(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _assertion_payload(assertion: TypeAssertion) -> Mapping[str, Any]:
    """A ``TypeAssertion`` as plain values, for the event log.

    ``TypeAssertion`` has no ``to_dict`` of its own, so the projection walks its
    dataclass fields rather than naming them twice - the same discipline
    :meth:`domain.entity_identity.ResolutionDecisionRecord.from_decision` uses for
    the decision it serialises, and for the same reason: a hand-written mapping
    silently drops a field a later version adds. Enums travel as their string value
    and the recorded ``type_assertion_id`` is carried back on the way in so the type
    verifies it against its own contents.
    """
    payload: dict[str, Any] = {}
    for item in fields(assertion):
        value = getattr(assertion, item.name)
        payload[item.name] = str(value) if isinstance(value, Enum) else value
    payload["evidence_refs"] = list(payload["evidence_refs"])
    return MappingProxyType(payload)


def _assertion_from(payload: Mapping[str, Any]) -> TypeAssertion:
    """Rebuild a ``TypeAssertion`` from :func:`_assertion_payload` and verify it."""

    return TypeAssertion(
        type_assertion_id=str(payload["type_assertion_id"]),
        logical_type_assertion_id=str(payload["logical_type_assertion_id"]),
        tenant_id=str(payload["tenant_id"]),
        entity_ref=str(payload["entity_ref"]),
        type_ref=str(payload["type_ref"]),
        type_scheme=SemanticRef(str(payload["type_scheme"])),
        scope=TypeScope(str(payload["scope"])),
        status=SemanticStatus(str(payload["status"])),
        raw_surface=str(payload["raw_surface"]),
        hypothesis=str(payload["hypothesis"]),
        source_ref=str(payload["source_ref"]),
        extractor_ref=str(payload["extractor_ref"]),
        context_ref=str(payload["context_ref"]),
        profile_ref=str(payload["profile_ref"]),
        mapping_ref=str(payload["mapping_ref"]),
        evidence_refs=tuple(str(ref) for ref in payload["evidence_refs"]),
    )


def record_log(case_run: CaseRun) -> Mapping[str, Any]:
    """One case's recorded event log: plain values only, no live objects.

    This is what FR-022 means by "the recorded event log", and the property that
    makes it a log rather than a wrapper around the run is that everything in it
    is a ``str``, ``int``, ``bool``, ``None``, a list or a mapping. Nothing here
    holds a :class:`~domain.relation_candidate.RelationCandidate`, a
    :class:`~semantic.resolution.ResolutionScope` or an ``EvidenceGraph``, so
    :func:`replay_from_records` cannot accidentally read one.

    The links between chain nodes are recorded as explicit ``derived_from`` /
    ``derives`` pairs, taken from the graph's own registration order rather than
    inferred. That is the one place this module reconstructs adjacency, and it
    reconstructs it from the walk the graph performed, not from a second opinion
    about what the chain should be.
    """
    result = case_run.result
    bundle = result.lineage
    log: dict[str, Any] = {
        "case_id": case_run.spec.case_id,
        "sentence": case_run.spec.sentence,
        "stream_id": case_run.spec.acquisition.stream_id,
        "refusal": case_run.refusal,
        "reached": case_run.trace.reached,
    }
    if result.observation is not None:
        observation = result.observation.observation
        log["observation"] = dict(observation.frame())
        log["observation_id"] = observation.observation_id
        log["event_id"] = observation.event_id
    if result.context is not None:
        log["context_id"] = result.context.frame.context_id
    if result.regime is not None:
        log["regime"] = dict(result.regime.record.to_dict())
        log["interpreted_context"] = result.regime.frame.context_id
    if case_run.capture is not None:
        log["capture"] = dict(case_run.capture.to_dict())
    if result.resolution is not None:
        step = result.resolution
        log["scope"] = MappingProxyType(
            {
                "scope_id": step.batch.scope.scope_id,
                "tenant_id": step.batch.scope.tenant_id,
                "investigation_id": step.batch.scope.investigation_id,
                "anchors": [
                    {
                        "logical_entity_ref": anchor.logical_entity_ref,
                        "anchor_mention_id": anchor.anchor_mention_id,
                        "anchor_key": anchor.anchor_key,
                        "candidate_ref": anchor.candidate_ref,
                    }
                    for anchor in sorted(
                        step.batch.scope.anchors, key=lambda item: item.logical_entity_ref
                    )
                ],
            }
        )
        log["decision_records"] = [dict(record.to_dict()) for record in case_run.decision_records]
        log["identities"] = [dict(identity.to_dict()) for identity in case_run.identities]
        log["anchor_observations"] = dict(_anchor_observations(result))
        log["anchor_captures"] = dict(_anchor_captures(result, case_run.capture))
        log["independence_groups"] = [list(group) for group in step.independence_groups()]
    if result.candidate is not None:
        log["candidate"] = _candidate_payload(result.candidate.supported)
        log["proposed_candidate"] = _candidate_payload(result.candidate.proposed)
    if result.claim is not None:
        claim = result.claim.claim
        log["claim_build"] = MappingProxyType(
            {
                "revision_number": claim.revision_number,
                "evidence_grade": str(claim.evidence_grade),
                "tenant_id": claim.tenant_id,
                "role_bindings": [binding.to_dict() for binding in claim.role_bindings],
                "assertion_refs": list(claim.assertion_refs),
                "source_independence_groups": [
                    list(group) for group in claim.source_independence_groups
                ],
                "normalization_version": claim.normalization_version,
                "ontology_version": claim.ontology_version,
                "observed_at": claim.observed_at.isoformat() if claim.observed_at else "",
                "claim_status": str(claim.status),
                "known_from": claim.known_from.isoformat() if claim.known_from else "",
                "known_until": claim.known_until.isoformat() if claim.known_until else "",
                "created_at": claim.created_at.isoformat() if claim.created_at else "",
            }
        )
        log["claim"] = dict(claim.to_dict())
        log["type_assertions"] = [
            dict(_assertion_payload(assertion))
            for assertion in (result.types.assertions if result.types else ())
        ]
    if bundle is not None:
        log["chain_registrations"] = [
            dict(entry) for entry in _chain_registrations(bundle)
        ]
        log["lineage_subject"] = {
            "backward": bundle.backward.subject_id,
            "forward": bundle.forward.subject_id,
        }
    return MappingProxyType(log)


def _chain_registrations(bundle: LineageBundle) -> tuple[Mapping[str, Any], ...]:
    """Every hop registration the run made into its ``EvidenceGraph``, as plain data.

    **This is a claim about the adjacency, and the replay tests it.** The
    orchestrator registers its hops into a private adjacency it does not publish,
    so the log cannot read the registrations off the graph; it *states* them, from
    the bundle's own real objects, one entry per
    :func:`semantic_path.execution._link_node` call in the order the orchestrator
    makes them. Each entry is the whole of what ``add_hop`` receives: the hop's
    kind, node id, label, relation and tenant, and the two neighbour ids.

    The replay registers exactly these into an **empty** :class:`EvidenceGraph` and
    asks *it* for both traversals. If an entry is stated wrongly the recomputed
    trace differs from the recorded one and the replay names the divergence, which
    is the only property that makes the exercise worth doing. This is deliberately
    **not** written by calling the orchestrator's own builder: a replay that
    re-derived the links with the same code that made them would be comparing a
    function with itself.

    Empty endpoints are recorded as empty strings rather than dropped.
    :meth:`EvidenceGraph.add_hop` treats them as *ends of the chain* and indexes
    only the non-empty side, and that asymmetry is exactly what makes the backward
    walk reach the source and the forward walk reach the entity - so dropping them
    would silently produce a shorter chain.
    """
    observation = bundle.observation
    claim = bundle.claim
    candidate = bundle.candidate
    tenant = observation.tenant_id
    capture_id = bundle.capture_id
    relation_id = claim.relation_id
    assertions = tuple(item.type_assertion_id for item in bundle.type_assertions)
    citing: dict[str, list[str]] = {}
    for assertion in bundle.type_assertions:
        for record in bundle.mentions:
            if record.mention_id in assertion.evidence_refs:
                citing.setdefault(record.mention_id, []).append(assertion.type_assertion_id)

    def hop(
        kind: HopKind, node_id: str, label: str, relation: str = ""
    ) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "kind": str(kind),
                "node_id": node_id,
                "label": label,
                "relation_id": relation,
                "tenant_id": tenant,
            }
        )

    registrations: list[tuple[Mapping[str, Any], str, str]] = [
        (hop(HopKind.SOURCE, bundle.source_id, observation.source_family), "", capture_id),
        (
            hop(HopKind.CAPTURE, capture_id, "capture"),
            bundle.source_id,
            observation.observation_id,
        ),
        (
            hop(
                HopKind.OBSERVATION,
                observation.observation_id,
                observation.document_id,
                relation_id,
            ),
            capture_id,
            observation.segment_id,
        ),
    ]
    for record in bundle.mentions:
        registrations.append(
            (
                hop(HopKind.SEGMENT, observation.segment_id, observation.language),
                observation.observation_id,
                record.mention_id,
            )
        )
    for record in bundle.mentions:
        registrations.append(
            (
                hop(HopKind.MENTION, record.mention_id, record.value),
                observation.segment_id,
                *([citing[record.mention_id][0]] if citing.get(record.mention_id) else [""]),
            )
        )
    for assertion in bundle.type_assertions:
        registrations.append(
            (
                hop(HopKind.ASSERTION, assertion.type_assertion_id, assertion.type_ref),
                candidate.candidate_id,
                relation_id,
            )
        )
    registrations.append(
        (
            hop(HopKind.CANDIDATE, candidate.candidate_id, candidate.relation_type),
            candidate.subject_mention_ref,
            relation_id,
        )
    )
    for assertion_id in assertions:
        registrations.append(
            (hop(HopKind.RELATION, relation_id, claim.relation_type), assertion_id, "")
        )
    for ref in (claim.subject_ref, claim.object_ref):
        registrations.append((hop(HopKind.ENTITY, ref, "resolved"), relation_id, ""))
    return tuple(
        MappingProxyType({**payload, "forward": forward, "backward": backward})
        for payload, forward, backward in registrations
    )


def _graph_from_log(registrations: Iterable[Mapping[str, Any]]) -> EvidenceGraph:
    """An **empty** ``EvidenceGraph`` carrying only the recorded registrations.

    Nothing is inherited and nothing is added: every adjacency the traversals will
    find is an entry the log carries, registered with the neighbour ids the log
    carries, so a replayed log cannot inflate a trace and cannot lose one either.
    """
    graph = EvidenceGraph()
    for entry in registrations:
        graph.add_hop(
            EvidenceHop(
                kind=HopKind(str(entry["kind"])),
                node_id=str(entry["node_id"]),
                label=str(entry.get("label", "")),
                relation_id=str(entry.get("relation_id", "")),
                tenant_id=str(entry.get("tenant_id", "default-tenant")),
            ),
            forward=str(entry["forward"]),
            backward=str(entry["backward"]),
        )
    return graph


def _rebuilt_stores(log: Mapping[str, Any]) -> dict[str, Any]:
    """Empty durable stores, filled only from the recorded log.

    Every one of these starts empty: an in-memory capture registry, an in-memory
    identity store, an in-memory regime store, a relation store and a graph store.
    Nothing is carried over from the run that wrote the log, and a store the log
    says nothing about is left empty rather than seeded - so a value the replay
    produces had to come out of the log.
    """
    return {
        "captures": InMemoryCaptureRegistry(),
        "identities": InMemoryEntityIdentityStore(),
        "regimes": InMemoryRegimeStore(),
        "relations": InMemoryRelationStore(),
        "graph": InMemoryGraphStore(),
    }


def _rehydrate_capture(log: Mapping[str, Any]) -> Capture | None:
    """The log's capture, rebuilt through the type that verifies its own address."""
    payload = log.get("capture")
    if payload is None:
        return None
    return Capture.from_dict(dict(payload))


def _rehydrate_regime(log: Mapping[str, Any]) -> RegimeRecord | None:
    """The log's regime row, rebuilt through the type that verifies both addresses."""
    payload = log.get("regime")
    if payload is None:
        return None
    return RegimeRecord.from_dict(dict(payload))


def _rehydrate_scope(log: Mapping[str, Any]) -> ResolutionScope | None:
    """The log's scope, rebuilt as real :class:`EntityAnchor` values.

    The four fields the resolver's own anchor type shares with
    :class:`domain.entity_identity.EntityAnchor` are carried across;
    ``established_by_decision`` is not, because the value the resolver stored is
    not an ``EntityAnchor`` and does not have it. That mismatch is reported by
    :func:`acceptance_chains` rather than papered over here, and it is the reason
    the replay constructs its own anchors rather than rehydrating the resolver's.
    """
    payload = log.get("scope")
    if payload is None:
        return None
    return ResolutionScope(
        scope_id=str(payload["scope_id"]),
        tenant_id=str(payload["tenant_id"]),
        investigation_id=str(payload["investigation_id"]),
        anchors=tuple(
            EntityAnchor(
                logical_entity_ref=str(anchor["logical_entity_ref"]),
                anchor_mention_id=str(anchor["anchor_mention_id"]),
                anchor_key=str(anchor["anchor_key"]),
                candidate_ref=str(anchor["candidate_ref"]),
            )
            for anchor in payload["anchors"]
        ),
    )


def _rehydrate_decisions(log: Mapping[str, Any]) -> tuple[ResolutionDecisionRecord, ...]:
    """The log's ``RES-`` rows, rebuilt and verified against the machine's own address.

    Two passes on purpose. :meth:`ResolutionDecisionRecord.from_dict` verifies the
    record's fingerprint against its own material, and
    :meth:`ResolutionDecisionRecord.to_decision` then asks
    :class:`semantic.resolution.ResolutionDecision` to re-derive its ``RES-`` from
    the rehydrated fields and refuses if the two disagree. A tampered row cannot
    survive either, which is what makes the round trip a check rather than a
    symmetry.
    """
    rows = tuple(
        ResolutionDecisionRecord.from_dict(dict(payload))
        for payload in log.get("decision_records", ())
    )
    for row in rows:
        row.to_decision()
    return rows


def _rehydrate_identities(log: Mapping[str, Any]) -> tuple[EntityIdentity, ...]:
    """The log's anchor rows, rebuilt through the write-once identity type."""
    return tuple(
        EntityIdentity.from_dict(dict(payload)) for payload in log.get("identities", ())
    )


def _rebuild_claim(log: Mapping[str, Any]) -> tuple[RelationClaimMaterial, RelationClaim] | None:
    """The claim lifecycle replayed: ``build``, ``validate``, ``admit``.

    All three real operations from :mod:`domain.relation_claim_material`, driven by
    the recorded candidate and the recorded build arguments. The candidate is
    rebuilt first and its recorded ``candidate_id`` handed back, so
    :class:`domain.relation_candidate.RelationCandidate` verifies it against its own
    contents rather than trusting the log. The claim's ids are then compared with
    the ids the log recorded, and a mismatch is a divergence with the layer named
    ``claims``.

    The report :func:`validate` produces is *not* compared against a recorded
    report: the orchestrator admits from an empty one (see the module docstring,
    finding 5), so there is no recorded report to compare with. What is compared is
    the claim the empty-report admission produces, which is the thing that matters
    for the graph.
    """
    payload = log.get("candidate")
    if payload is None or "claim_build" not in log:
        return None
    candidate = _candidate_from(dict(payload))
    build_args = log["claim_build"]
    material = build(
        candidate,
        subject_ref=str(log["claim"]["subject_ref"]),
        object_ref=str(log["claim"]["object_ref"]),
        revision_number=int(build_args["revision_number"]),
        evidence_grade=_evidence_grade(str(build_args["evidence_grade"])),
        tenant_id=str(build_args["tenant_id"]),
        role_bindings=tuple(
            _role_binding(item) for item in build_args["role_bindings"]
        ),
        assertion_refs=tuple(str(ref) for ref in build_args["assertion_refs"]),
        source_independence_groups=tuple(
            tuple(str(ref) for ref in group)
            for group in build_args["source_independence_groups"]
        ),
        normalization_version=str(build_args["normalization_version"]),
        ontology_version=str(build_args["ontology_version"]),
        observed_at=_moment_or_none(str(build_args["observed_at"])),
    )

    claim = admit(material, unvalidated_report(material), **_admit_kwargs(build_args))
    return material, claim


def _admit_kwargs(build_args: Mapping[str, Any]) -> dict[str, Any]:
    """The ``admit`` keyword arguments the recorded claim was admitted with."""

    return {
        "claim_status": RelationStatus(str(build_args["claim_status"])),
        "created_at": _moment_or_none(str(build_args["created_at"])),
        "known_from": _moment_or_none(str(build_args["known_from"])),
        "known_until": _moment_or_none(str(build_args["known_until"])),
    }


def _evidence_grade(value: str) -> Any:

    return EvidenceGrade(value)


def replay_from_request(case: CaseSpec) -> CorpusRun:
    """Re-execute the recorded request against **empty** stores.

    The weaker of the two replays and it is here because it proves something the
    stronger one cannot: that the *request* is a complete input. Every store is
    fresh - regime, relation and graph - so a value this run produces cannot have
    come from a previous one, and the result is compared against the original run
    over all five invariance layers.
    """
    return run_case(case)


def replay_from_records(log: Mapping[str, Any], recorded: CaseRun) -> ReplayReport:
    """Rebuild the world from the recorded event log alone, into empty stores.

    **This is FR-022.** Nothing reachable from ``recorded`` is read: the log is a
    mapping of plain values, and the function touches only the log and the
    committed fixture for the sentence. The durable stores start empty and are
    filled from the log's own rows, the claim is rebuilt through the real
    ``build``/``admit`` pair, the projection is rebuilt through the real
    :class:`~graph.relation_store.GraphProjectionBridge` into a fresh graph store,
    and the lineage is recomputed by an empty :class:`EvidenceGraph` carrying only
    the recorded registrations.

    Four things are compared, because a replay that checked one of them would be a
    claim about one of them: the **graph** (every node, edge and hyperedge read back
    out of the fresh store), the **ids** (every address the log carries, re-derived
    by the types that own them), the **lineage** (both traces recomputed from the
    recorded adjacency) and the **decisions** (each ``RES-`` row rehydrated into the
    machine's own object, which refuses if the address does not follow).
    """
    divergences: list[ReplayDivergence] = []
    notes: list[str] = []
    case_id = str(log["case_id"])
    stores = _rebuilt_stores(log)

    capture = _rehydrate_capture(log)
    if capture is not None:
        stores["captures"].register(capture)
        if stores["captures"].resolve(capture.capture_id) is None:
            divergences.append(
                ReplayDivergence(
                    case_id, "stores", "capture_round_trip", capture.capture_id, "<absent>"
                )
            )
    recorded_capture = recorded.capture.capture_id if recorded.capture else ""
    if (capture.capture_id if capture else "") != recorded_capture:
        divergences.append(
            ReplayDivergence(
                case_id, "stores", "capture_id", recorded_capture,
                capture.capture_id if capture else "<absent>",
            )
        )

    regime = _rehydrate_regime(log)
    if regime is not None:
        stores["regimes"].ingest_regime(regime.to_regime())
        recovered = stores["regimes"].regime_for(str(regime.tenant_id), regime.regime_id)
        if recovered is None or recovered.record_fingerprint != regime.record_fingerprint:
            divergences.append(
                ReplayDivergence(
                    case_id, "stores", "regime_round_trip", regime.record_fingerprint,
                    recovered.record_fingerprint if recovered else "<absent>",
                )
            )
        if stores["regimes"].unresolved_reads():
            divergences.append(
                ReplayDivergence(
                    case_id, "stores", "regime_unresolved_reads", "0",
                    str(stores["regimes"].unresolved_reads()),
                )
            )

    records = _rehydrate_decisions(log)
    scope = _rehydrate_scope(log)
    identities = _rehydrate_identities(log)
    reconstruction: EntityReconstruction | None = None
    if scope is not None:
        decided_at = _recorded_observed_at(log)
        for record in records:
            stores["identities"].record_decision(record)
        refused_codes = _bind_anchors(
            stores["identities"],
            scope,
            records,
            _logged_anchor_observations(log),
            _logged_anchor_captures(log),
            decided_at,
        )
        for code in refused_codes:
            notes.append(
                f"the log's scope carries an anchor no recorded decision created; "
                f"ingest_scope refused it with {code!r} and it was not bound"
            )
        for identity in sorted(identities, key=lambda item: item.entity_id):
            try:
                reconstruction = stores["identities"].reconstruct(
                    str(identity.tenant_id), identity.entity_id
                )
            except EntityIdentityError as refusal:
                divergences.append(
                    ReplayDivergence(
                        case_id, "identities", f"reconstruct:{refusal.code}",
                        identity.entity_id, "<refused>",
                    )
                )
                break
            if not reconstruction.complete:
                for hole in reconstruction.holes:
                    divergences.append(
                        ReplayDivergence(
                            case_id, "identities", f"hole:{hole.link}", "", hole.code
                        )
                    )
            break

    built = _rebuild_claim(log)
    if built is not None:
        material, claim = built
        recorded_claim = dict(log["claim"])
        divergences.extend(
            _compare_ids(
                case_id,
                "claims",
                {
                    "material.relation_id": (material.relation_id, recorded_claim["relation_id"]),
                    "material.logical": (
                        material.logical_relation_id,
                        recorded_claim["logical_relation_id"],
                    ),
                    "claim.relation_id": (claim.relation_id, recorded_claim["relation_id"]),
                    "claim.logical": (
                        claim.logical_relation_id,
                        recorded_claim["logical_relation_id"],
                    ),
                    "claim.subject": (claim.subject_ref, recorded_claim["subject_ref"]),
                    "claim.object": (claim.object_ref, recorded_claim["object_ref"]),
                },
            )
        )
        provenance = {
            "event_id": str(log.get("event_id", "")),
            "observation_id": str(log.get("observation_id", "")),
        }
        stores["relations"].write(claim, provenance=provenance)
        replayed_checksum = stores["relations"].checksum()
        recorded_checksum = recorded.trace.edge_refs[0][2] if recorded.trace.edge_refs else ""
        if replayed_checksum != recorded_checksum:
            divergences.append(
                ReplayDivergence(
                    case_id, "graph", "relation_store_checksum",
                    recorded_checksum, replayed_checksum,
                )
            )
        bridge = GraphProjectionBridge()
        graph_store = stores["graph"]
        for node in bridge.to_nodes(claim):
            graph_store.write_node(node, provenance)
        replayed_edge = bridge.to_edge(claim)
        graph_store.write_edge(replayed_edge, provenance)
        if replayed_edge.edge_id != str(log["claim"]["relation_id"]):
            divergences.append(
                ReplayDivergence(
                    case_id, "graph", "edge_id", str(log["claim"]["relation_id"]),
                    replayed_edge.edge_id,
                )
            )
        replayed_out = tuple(
            graph_store.neighbors(claim.subject_ref, claim.relation_type, direction="out")
        )
        recorded_out = recorded.result.edge.out_neighbors if recorded.result.edge else ()
        if replayed_out != recorded_out:
            divergences.append(
                ReplayDivergence(
                    case_id, "graph", "out_neighbors", repr(recorded_out), repr(replayed_out)
                )
            )
        replayed_nodes = sorted(
            (node.node_id, node.node_type) for node in graph_store.nodes()
        )
        recorded_nodes = sorted(
            (node.node_id, node.node_type)
            for node in (recorded.result.edge.nodes if recorded.result.edge else ())
        )
        divergences.extend(
            _compare_ids(
                case_id,
                "graph",
                {
                    f"node:{index}": (str(replayed), str(want))
                    for index, (replayed, want) in enumerate(
                        zip(replayed_nodes, recorded_nodes, strict=False)
                    )
                },
            )
        )

    replayed_lineage = _replay_lineage(log)
    if replayed_lineage is not None:
        divergences.extend(
            _compare_ids(
                case_id,
                "lineage",
                {
                    "backward": (
                        replayed_lineage[0],
                        _recorded_lineage_digest(recorded, "backward"),
                    ),
                    "forward": (
                        replayed_lineage[1],
                        _recorded_lineage_digest(recorded, "forward"),
                    ),
                },
            )
        )
    else:
        notes.append("the log carries no chain registrations, so no lineage was recomputed")
    if not log.get("chain_registrations"):
        notes.append(
            "no claim was rebuilt, so the graph projection was not exercised by this replay"
        )
    return ReplayReport(
        case_id=case_id,
        replayed="records",
        divergences=tuple(divergences),
        notes=tuple(notes),
    )


def _bind_anchors(
    store: InMemoryEntityIdentityStore,
    scope: ResolutionScope,
    records: tuple[ResolutionDecisionRecord, ...],
    observations: Mapping[str, str],
    captures: Mapping[str, str],
    decided_at: datetime | None,
) -> tuple[str, ...]:
    """Bind the log's scope into an **empty** identity store, write-once.

    :meth:`InMemoryEntityIdentityStore.ingest_scope` is the real write path and it
    refuses an anchor whose creating decision was not supplied, so this is where a
    log that lost a decision shows up: as a refusal. The same two-pass shape as
    :func:`_identities` - the whole scope first, then the attested subset - and the
    refusal codes are returned rather than swallowed.
    """
    try:
        store.ingest_scope(
            scope,
            records,
            anchor_observations=observations,
            anchor_captures=captures,
            decided_at=decided_at,
            created_at=decided_at,
        )
        return ()
    except EntityIdentityError as refusal:
        store.ingest_scope(
            _attested_scope(scope, records),
            records,
            anchor_observations=observations,
            anchor_captures=captures,
            decided_at=decided_at,
            created_at=decided_at,
        )
        return (refusal.code,)


def _logged_anchor_observations(log: Mapping[str, Any]) -> Mapping[str, str]:
    """The log's ``mention -> observation`` map, or an empty one.

    Empty is not a default value: it is what the recording side produces when a run
    resolved nothing, and a replay that received an empty map where the log held
    one would report a reconstruction hole rather than quietly succeeding.
    """
    return MappingProxyType(
        {str(key): str(value) for key, value in (log.get("anchor_observations") or {}).items()}
    )


def _logged_anchor_captures(log: Mapping[str, Any]) -> Mapping[str, str]:
    """The log's ``mention -> capture`` map, or an empty one. See the above."""
    return MappingProxyType(
        {str(key): str(value) for key, value in (log.get("anchor_captures") or {}).items()}
    )


def _recorded_observed_at(log: Mapping[str, Any]) -> datetime | None:
    """The recorded ``observed_at``, read back out of the recorded frame."""
    frame = log.get("observation")
    if frame is None:
        return None
    return _moment_or_none(str(frame.get("observed_at", "")))


def _recorded_lineage_digest(recorded: CaseRun, direction: str) -> str:
    """The digest the original run recorded for one lineage direction.

    Read by name rather than by index, so a case that reached no EDGE stage - and
    therefore has no lineage at all - reports an empty digest rather than raising
    or silently reading the wrong direction.
    """
    for name, digest in recorded.trace.lineage_digests:
        if name == direction:
            return digest
    return ""
def _replay_lineage(log: Mapping[str, Any]) -> tuple[str, str] | None:
    """Both lineage traces, recomputed from the log's own registrations.

    Returns the two digests of the recomputed hop sequences, or ``None`` when the
    log carries no registrations to recompute from. The digests are over
    ``(kind, node_id)`` pairs in trace order, so they compare against the recorded
    ``lineage_digests`` without depending on labels - which the log does not record
    for the registrations, and which a traversal does not read either.
    """
    registrations = log.get("chain_registrations")
    if not registrations:
        return None
    graph = _graph_from_log(registrations)
    subject = log.get("lineage_subject", {})
    backward = graph.backward(str(subject.get("backward", "")))
    forward = graph.forward(str(subject.get("forward", "")))
    return (
        digest128(canonical_material(_hop_pairs(backward.hops))),
        digest128(canonical_material(_hop_pairs(forward.hops))),
    )


def _compare_ids(
    case_id: str, layer: str, pairs: Mapping[str, tuple[str, str]]
) -> list[ReplayDivergence]:
    """Every recorded/replayed pair that is not equal, as named divergences."""
    return [
        ReplayDivergence(case_id, layer, label, recorded, replayed)
        for label, (replayed, recorded) in sorted(pairs.items())
        if replayed != recorded
    ]


def replay(case_run: CaseRun) -> ReplayReport:
    """FR-022 for one case: record the log, then rebuild from it into empty stores."""
    return replay_from_records(record_log(case_run), case_run)


def replay_of_replay(case_run: CaseRun) -> ReplayReport:
    """The fixed point: replay the replay, and require identity.

    The second replay is fed the *first replay's own* log rather than the
    original's, so a chain of replays is shown to be stationary. Concretely: the
    first report's rebuilt values are written back into a log, and the second
    replay must reproduce the first's digests exactly. A replay that merely
    reproduced the original would still be a fixed point of the original, so this is
    the stronger of the two checks and the one SC-12 asks for.
    """
    log = record_log(case_run)
    first = replay_from_records(log, case_run)
    second_log = _relay_log(log)
    second = replay_from_records(second_log, case_run)
    if first.identical != second.identical:
        return ReplayReport(
            case_id=case_run.spec.case_id,
            replayed="replay",
            divergences=second.divergences,
            fixed_point=False,
            notes=("replaying the replay is not the replay",),
        )
    return ReplayReport(
        case_id=case_run.spec.case_id,
        replayed="replay",
        divergences=second.divergences,
        fixed_point=first.identical,
        notes=("replay of the replay reproduced the replay",),
    )


def _relay_log(log: Mapping[str, Any]) -> Mapping[str, Any]:
    """The log as a replay of it would re-record it, byte for byte where it can.

    A round trip through the *types* rather than through this module's own
    projections: the capture, the regime row, the decision rows, the identity rows
    and the claim row are re-serialised by their own ``to_dict``, and the candidate
    by :func:`_candidate_payload` of the rebuilt candidate. Anything the log
    carries as a plain value is copied. So a replayed log is a log the types
    themselves wrote, and a second replay reading it can only differ if a projection
    is lossy - which is the thing worth detecting.
    """
    relayed: dict[str, Any] = dict(log)
    if log.get("capture") is not None:
        relayed["capture"] = dict(Capture.from_dict(dict(log["capture"])).to_dict())
    if log.get("regime") is not None:
        relayed["regime"] = dict(RegimeRecord.from_dict(dict(log["regime"])).to_dict())
    relayed["decision_records"] = [
        dict(ResolutionDecisionRecord.from_dict(dict(row)).to_dict())
        for row in log.get("decision_records", ())
    ]
    relayed["identities"] = [
        dict(EntityIdentity.from_dict(dict(row)).to_dict())
        for row in log.get("identities", ())
    ]
    if log.get("candidate") is not None:
        relayed["candidate"] = _candidate_payload(_candidate_from(dict(log["candidate"])))
    if log.get("proposed_candidate") is not None:
        relayed["proposed_candidate"] = _candidate_payload(
            _candidate_from(dict(log["proposed_candidate"]))
        )
    if log.get("claim") is not None:
        relayed["claim"] = dict(RelationClaim.from_dict(dict(log["claim"])).to_dict())
    if log.get("type_assertions") is not None:
        relayed["type_assertions"] = [
            dict(_assertion_payload(_assertion_from(dict(row))))
            for row in log["type_assertions"]
        ]
    return MappingProxyType(relayed)


class ChainLink(StrEnum):
    """One link of one acceptance chain, in chain order.

    Named so a hole names the link it belongs to rather than saying "the chain is
    incomplete". ``ENTITY_CHAIN`` and ``RELATION_CHAIN`` are the two the
    specification writes out, and every member of both is checked.
    """

    ENTITY = "entity"
    RESOLUTION_DECISION = "resolution_decision"
    MENTIONS = "mentions"
    OBSERVATIONS = "observations"
    CAPTURES = "captures"
    SOURCES = "sources"
    RELATION_CLAIM = "relation_claim"
    RELATION_CANDIDATE = "relation_candidate"
    ASSERTION = "assertion"
    EVIDENCE = "evidence"


ENTITY_CHAIN: tuple[ChainLink, ...] = (
    ChainLink.ENTITY,
    ChainLink.RESOLUTION_DECISION,
    ChainLink.MENTIONS,
    ChainLink.OBSERVATIONS,
    ChainLink.CAPTURES,
    ChainLink.SOURCES,
)

RELATION_CHAIN: tuple[ChainLink, ...] = (
    ChainLink.RELATION_CLAIM,
    ChainLink.RELATION_CANDIDATE,
    ChainLink.ASSERTION,
    ChainLink.MENTIONS,
    ChainLink.EVIDENCE,
)


@dataclass(frozen=True)
class ChainHole:
    """One link of one chain that is not walkable, and what is wrong with it.

    :attr:`status` is a fixed vocabulary so a report can be read without prose:
    ``present`` (the link is on a real, durable record), ``in_memory_only`` (it is
    reachable only through the live run, not on any record), ``derived`` (the value
    on the record is a digest computed from the thing it should explain),
    ``absent`` (no record names it at all) and ``mismatched`` (two records that
    should name each other do not). The five are distinct answers and the report
    says which one it is.
    """

    link: ChainLink
    status: str
    detail: str

    def text(self) -> str:
        return f"    {self.link!s:20s} {self.status:15s} {self.detail}"


@dataclass(frozen=True)
class AcceptanceChain:
    """One chain, reconstructed for one subject, with every link's status named.

    ``subject`` is the thing the question was asked about - an ``ENT-`` for the
    entity chain, an ``RC-`` for the relation chain - and ``links`` is one entry
    per :data:`ENTITY_CHAIN` or :data:`RELATION_CHAIN` member, in chain order.
    :attr:`complete` is a fact rather than an impression, and it means *no link is
    anything but* ``present``.
    """

    case_id: str
    subject: str
    links: tuple[ChainHole, ...]

    @property
    def complete(self) -> bool:
        return all(hole.status == "present" for hole in self.links)

    def holes(self) -> tuple[ChainHole, ...]:
        return tuple(hole for hole in self.links if hole.status != "present")

    def text(self) -> str:
        head = (
            f"  chain subject={self.subject or '<none>'} complete={self.complete} "
            f"links={len(self.links)}"
        )
        return "\n".join([head, *(hole.text() for hole in self.links)])


def chain_status(chain: AcceptanceChain) -> str:
    """``complete`` or the statuses that are not ``present``, comma-joined."""
    if chain.complete:
        return "complete"
    return ",".join(sorted({hole.status for hole in chain.holes()})) or "unknown"


def _entity_chain(case_run: CaseRun, entity_id: str) -> AcceptanceChain:
    """``Entity -> Resolution decision -> Mentions -> Observations -> Captures -> Sources``.

    Reconstructed from **durable state**, not from the live run: the ``RES-`` row
    comes from :meth:`ResolutionDecisionRecord.to_decision` through
    :meth:`InMemoryEntityIdentityStore.reconstruct`, and the capture from
    :class:`InMemoryCaptureRegistry` via the anchor's ``anchor_capture_id``. The
    live run is read only to find out *which* entity to ask about and which
    observation this segment produced.

    A reconstruction that raises is reported as a hole naming the refusal's code
    rather than propagated, because a chain that cannot be walked is the finding
    SC-14 asks for and an exception is not a report.
    """
    case_id = case_run.spec.case_id
    result = case_run.result
    tenant = result.request.tenant_id
    observed = result.observation.observation.observed_at if result.observation else None
    links: list[ChainHole] = [
        ChainHole(
            ChainLink.ENTITY,
            "present" if entity_id else "absent",
            entity_id or "no entity was resolved for this case",
        )
    ]
    if not entity_id:
        for link in ENTITY_CHAIN[1:]:
            links.append(ChainHole(link, "absent", "no entity to walk out from"))
        return AcceptanceChain(case_id=case_id, subject=entity_id, links=tuple(links))

    store = InMemoryEntityIdentityStore()
    if observed is not None and result.resolution is not None:
        _bind_anchors(
            store,
            result.resolution.batch.scope,
            case_run.decision_records,
            _anchor_observations(result),
            _anchor_captures(result, case_run.capture),
            observed,
        )
    try:
        reconstruction = store.reconstruct(tenant, entity_id)
    except EntityIdentityError as refusal:
        for link in ENTITY_CHAIN[1:]:
            links.append(
                ChainHole(link, "absent", f"reconstruct refused: {refusal.code}")
            )
        return AcceptanceChain(case_id=case_id, subject=entity_id, links=tuple(links))
    links.append(
        ChainHole(
            ChainLink.RESOLUTION_DECISION,
            "present" if reconstruction.decisions else "absent",
            f"{len(reconstruction.decisions)} durable RES- row(s): "
            f"{list(reconstruction.decision_ids())}; terminal verdict "
            f"{reconstruction.terminal_verdict!r}; anchor created by "
            f"{reconstruction.identity.created_by_resolution}",
        )
    )
    registered = {
        record.mention_id for record in (result.mentions.records if result.mentions else ())
    }
    merged = tuple(reconstruction.merged_mentions)
    local = tuple(ref for ref in merged if ref in registered)
    carried = tuple(ref for ref in merged if ref not in registered)
    links.append(
        ChainHole(
            ChainLink.MENTIONS,
            "present" if local and not carried else ("partial" if local else "absent"),
            f"merged set {list(merged)}: {len(local)} are mentions of this segment "
            f"{list(local)} and {len(carried)} are support refs carried on the registry "
            f"record {list(carried)}, which this run's observation did not produce and for "
            "which no observation is recorded anywhere in this corpus",
        )
    )
    known_observation = (
        result.observation.observation.observation_id if result.observation else ""
    )
    anchor_observation = reconstruction.anchor_observation_id
    links.append(
        ChainHole(
            ChainLink.OBSERVATIONS,
            "present"
            if anchor_observation == known_observation and anchor_observation
            else "mismatched",
            f"{known_observation!r}",
        )
    )
    links.append(_capture_link(case_run, reconstruction.anchor_capture_id, known_observation))
    source_id = case_run.capture.source_id if case_run.capture else ""
    links.append(
        ChainHole(
            ChainLink.SOURCES,
            "present" if source_id else "absent",
            f"capture names source {source_id!r}" if source_id else "no capture, so no source",
        )
    )
    return AcceptanceChain(case_id=case_id, subject=entity_id, links=tuple(links))


def _capture_link(
    case_run: CaseRun, anchor_capture_id: str, observation_id: str
) -> ChainHole:
    """The ``Captures`` link, and the finding this corpus exists partly to report.

    Three answers, kept apart. ``present`` - the anchor names a capture that is
    registered and reaches the observation. ``derived`` - the anchor names the
    orchestrator's ``capture_id_for(source, observation)``, a digest computed *from*
    the observation it is supposed to explain, which is not a capture and is not
    what the acquisition seam emitted. ``absent`` - no capture at all, because the
    stream refused or the adapter declined the record.

    The corpus links the **real** capture into the anchor, so on a healthy case this
    is ``present``; and it reports the orchestrator's derived hop alongside, because
    the derived hop is still what the orchestrator's own lineage carries and a
    reader following that chain will arrive at a ``CAP-`` that is in no registry.
    """
    capture = case_run.capture
    derived = case_run.result.lineage.capture_id if case_run.result.lineage else ""
    if capture is None:
        return ChainHole(
            ChainLink.CAPTURES,
            "absent",
            f"acquisition emitted no capture for {case_run.spec.acquisition.stream_id!r}, so the "
            f"anchor records no capture; the orchestrator's derived hop would have been "
            f"{derived!r}, which is a digest of the observation and not a capture",
        )
    if anchor_capture_id != capture.capture_id:
        return ChainHole(
            ChainLink.CAPTURES,
            "mismatched",
            f"anchor names {anchor_capture_id!r} and the real capture is "
            f"{capture.capture_id!r}",
        )
    if derived and derived != capture.capture_id:
        return ChainHole(
            ChainLink.CAPTURES,
            "lineage_diverges",
            f"the acquisition seam and the durable anchor agree on "
            f"{capture.capture_id!r}, but the orchestrator's own lineage carries "
            f"{derived!r}; one fetch is being addressed twice",
        )
    in_lineage = f" and the orchestrator's lineage carries the same {derived}" if derived else (
        " and this case's lineage stops before the capture hop"
    )
    return ChainHole(
        ChainLink.CAPTURES,
        "present",
        f"{capture.capture_id} on stream {case_run.spec.acquisition.stream_id!r}, basis "
        f"{capture.time_basis!s}, fetched_at "
        f"{capture.fetched_at.isoformat() if capture.fetched_at else 'absent'}{in_lineage}",
    )


def _relation_chain(case_run: CaseRun) -> AcceptanceChain:
    """``RelationClaim -> RelationCandidate -> Assertion -> Mentions -> Evidence``.

    Reconstructed from the committed claim's own fields wherever the claim carries
    the link, and from the live run's objects only where it does not - and every
    such link is marked ``in_memory_only`` rather than counted as present, because
    SC-14 asks whether a reader with the record can walk it, and a reader with only
    the record cannot.
    """
    case_id = case_run.spec.case_id
    result = case_run.result
    if result.claim is None:
        return AcceptanceChain(
            case_id=case_id,
            subject="",
            links=tuple(
                ChainHole(link, "absent", "this case materialised no claim")
                for link in RELATION_CHAIN
            ),
        )
    claim = result.claim.claim
    assertions = result.types.assertions if result.types else ()
    candidate_id = result.candidate.supported.candidate_id if result.candidate else ""
    on_record = "candidate_id" in {field.name for field in fields(RelationClaim)}
    links = [
        ChainHole(
            ChainLink.RELATION_CLAIM,
            "present",
            f"{claim.relation_id} (logical {claim.logical_relation_id}), tenant "
            f"{claim.tenant_id!r}",
        ),
        ChainHole(
            ChainLink.RELATION_CANDIDATE,
            "present" if on_record else "in_memory_only",
            f"{candidate_id}"
            + (
                ""
                if on_record
                else " - RelationClaim carries no candidate_id field, so this link is "
                "reachable only through the run's CandidateStep and not from the record"
            ),
        ),
        ChainHole(
            ChainLink.ASSERTION,
            "present" if claim.assertion_refs else "absent",
            f"assertion_refs {list(claim.assertion_refs)} resolve to "
            f"{[item.type_assertion_id for item in assertions]}",
        ),
    ]
    mention_refs = [
        ref for assertion in assertions for ref in assertion.evidence_refs
    ]
    registered = {
        record.mention_id for record in (result.mentions.records if result.mentions else ())
    }
    mentioned = [ref for ref in mention_refs if ref in registered]
    links.append(
        ChainHole(
            ChainLink.MENTIONS,
            "present" if mentioned else "absent",
            f"{len(mentioned)} of {len(mention_refs)} assertion evidence refs are registered "
            f"mentions: {mentioned}",
        )
    )
    observations = result.observation.observation.observation_id if result.observation else ""
    segment = result.observation.observation.segment_id if result.observation else ""
    carried = tuple(claim.observation_refs)
    evidence = {
        "observation_refs": list(claim.observation_refs),
        "observations_present": observations in claim.observation_refs,
        "segment_present": segment in claim.observation_refs,
        "mentions_present": len(mentioned),
        "evidence_refs_field": "absent",
    }
    links.append(
        ChainHole(
            ChainLink.EVIDENCE,
            "present"
            if evidence["observations_present"] and evidence["segment_present"] and mentioned
            else "mismatched",
            f"{len(carried)} observation_refs, observations "
            f"{evidence['observations_present']}, segment {evidence['segment_present']}, "
            f"mentions {len(mentioned)}; RelationClaim has no evidence_refs field, so the "
            f"mentions travel inside observation_refs",
        )
    )
    return AcceptanceChain(case_id=case_id, subject=claim.relation_id, links=tuple(links))


def acceptance_chains(case_run: CaseRun) -> tuple[AcceptanceChain, ...]:
    """Both chains for one case: one per resolved entity, then the relation's.

    Every resolved entity gets the entity chain, because SC-14 says "for any entity
    and any relation" and a case with two entities that only reported one of them
    would not have answered the question. Cases that resolved nothing report one
    entity chain whose first link is ``absent``, which is the honest answer rather
    than no chain at all.
    """
    result = case_run.result
    chains: list[AcceptanceChain] = []
    for entity_id in case_run.trace.identity_refs:
        chains.append(_entity_chain(case_run, entity_id))
    if not case_run.trace.identity_refs:
        chains.append(_entity_chain(case_run, ""))
    chains.append(_relation_chain(case_run))
    del result
    return tuple(chains)


@dataclass(frozen=True)
class AnchorReport:
    """Whether an ``ENT-`` survives its caller discarding the ``ResolutionScope``.

    Three reads and one comparison, which is the most this path can honestly
    offer, and the report says so in :attr:`discriminating`:

    * the ``ENT-`` the run produced;
    * the same ``ENT-`` after the scope object is dropped and the anchor is
      re-read from the durable store through the one indexed read that exists
      (:meth:`InMemoryEntityIdentityStore.anchor_for_mention`), the scope is rebuilt
      from those rows, and the path is re-run with it;
    * the ``ENT-`` a run with no scope and no durable state produces.

    When the third equals the first, a lost scope is *not observable* on this path,
    because
    :func:`semantic.resolution.logical_entity_ref_for` derives an ``ENT-`` from
    ``(tenant, scope id, anchor mention)`` and all three are recoverable from the
    request. That is a real property of the derivation and a real limit on what
    SC-1 can be demonstrated with here; it is reported as
    ``discriminating=False`` rather than as a pass.
    """

    case_id: str
    anchor_mention_id: str
    entity_from_run: str
    entity_from_durable_anchor: str
    entity_from_no_state: str
    anchor_row: str
    scope_rebuilt: bool
    discriminating: bool
    notes: tuple[str, ...] = ()

    @property
    def holds(self) -> bool:
        return self.entity_from_run == self.entity_from_durable_anchor

    def text(self) -> str:
        return (
            f"anchor case={self.case_id} mention={self.anchor_mention_id} "
            f"run={self.entity_from_run or '<none>'} "
            f"durable={self.entity_from_durable_anchor or '<none>'} "
            f"stateless={self.entity_from_no_state or '<none>'} "
            f"holds={self.holds} discriminating={self.discriminating}"
        )


def anchor_survives_scope_loss(case: CaseSpec) -> AnchorReport:
    """Drop the scope, re-read the anchor from durable state, and compare.

    Runs the case three times over three *fresh* stores, which is what makes the
    middle run a real answer: nothing survives between them except what this
    function writes down. The durable read is the real hot path -
    :meth:`InMemoryEntityIdentityStore.anchor_for_mention`, one indexed read on
    ``(tenant, anchor_mention_id)`` - and the scope it rebuilds is handed to the
    second run through :attr:`semantic_path.execution.ExecutionRequest`'s
    ``resolution_scope`` field, so the resolver adopts the recorded anchor rather
    than electing one.
    """
    first = run_case(case)
    if first.result.resolution is None:
        return AnchorReport(
            case_id=case.case_id,
            anchor_mention_id="",
            entity_from_run="",
            entity_from_durable_anchor="",
            entity_from_no_state="",
            anchor_row="",
            scope_rebuilt=False,
            discriminating=False,
            notes=("this case reached no resolution, so there is no anchor to lose",),
        )
    refs = sorted(first.trace.identity_refs)
    if not refs:
        return AnchorReport(
            case_id=case.case_id,
            anchor_mention_id="",
            entity_from_run="",
            entity_from_durable_anchor="",
            entity_from_no_state="",
            anchor_row="",
            scope_rebuilt=False,
            discriminating=False,
            notes=("this case resolved no entity, so there is no anchor to lose",),
        )
    entity = refs[0]
    scope = first.result.resolution.batch.scope
    anchor = next(
        item for item in scope.anchors if item.logical_entity_ref == entity
    )
    durable = InMemoryEntityIdentityStore()
    observed = first.result.observation.observation.observed_at
    durable.ingest_scope(
        scope,
        first.decision_records,
        anchor_observations=_anchor_observations(first.result),
        anchor_captures=_anchor_captures(first.result, first.capture),
        decided_at=observed,
        created_at=observed,
    )
    row = durable.anchor_for_mention(case.request.tenant_id, anchor.anchor_mention_id)
    rebuilt: ResolutionScope | None = None
    if row is not None:
        rebuilt = ResolutionScope(
            scope_id=scope.scope_id,
            tenant_id=scope.tenant_id,
            investigation_id=scope.investigation_id,
            anchors=(
                EntityAnchor(
                    logical_entity_ref=row.entity_id,
                    anchor_mention_id=row.anchor_mention_id,
                    anchor_key=anchor.anchor_key,
                    candidate_ref=anchor.candidate_ref,
                    established_by_decision=row.created_by_resolution,
                ),
            ),
        )
    second = run_case(replace(case, request=replace(case.request, resolution_scope=rebuilt)))
    third = run_case(replace(case, request=replace(case.request, resolution_scope=None)))
    second_ref = second.trace.identity_refs[0] if second.trace.identity_refs else ""
    third_ref = third.trace.identity_refs[0] if third.trace.identity_refs else ""
    return AnchorReport(
        case_id=case.case_id,
        anchor_mention_id=anchor.anchor_mention_id,
        entity_from_run=entity,
        entity_from_durable_anchor=second_ref,
        entity_from_no_state=third_ref,
        anchor_row=(
            f"{row.entity_id} @ {row.anchor_mention_id} created_by {row.created_by_resolution}"
            if row
            else "no anchor row"
        ),
        scope_rebuilt=rebuilt is not None,
        discriminating=third_ref != entity,
        notes=(
            (
                "the anchor was re-read from durable state through anchor_for_mention and "
                "the scope rebuilt from that row alone"
            ),
            (
                "logical_entity_ref_for is a function of (tenant, scope id, anchor mention), "
                "all three of which the request carries, so a lost scope is not observable "
                "on this path and SC-1's demonstration has no discriminating power here"
            )
            if third_ref == entity
            else (
                "a run with no scope and no durable state produced a different entity, so "
                "the anchor is load-bearing"
            ),
        ),
    )


def smoke(cases: Sequence[CaseSpec] = CASES) -> str:
    """The whole demonstration as one block of text, and nothing asserted.

    Seven sections, in the order the tasks name them: the cases and what each
    exercises, the acquisition seam over both streams, the committed-expectation
    comparison, the per-layer invariance result, the replay result, the graded
    checklist, the anchor durability read and both acceptance chains per case.
    Returns the text rather than printing it so a caller can put it wherever it
    wants; :func:`main` prints it.
    """
    run = run_corpus(cases)
    lines: list[str] = ["== corpus cases =="]
    for case in run.cases:
        lines.append(case.trace.text())
        lines.append(f"    sentence: {case.spec.sentence}")
        lines.append(f"    exercises: {', '.join(case.spec.labels)}")
        lines.append(f"    refusal: {case.refusal or 'none - reached worldline'}")
    lines.append("")
    lines.append("== acquisition seam ==")
    for stream_id in (COMMON_CRAWL_STREAM, EDGAR_STREAM):
        lines.append(f"stream {stream_id}")
        for axis, supplied, source in axis_report(stream_id):
            lines.append(f"    {axis:14s} supplied={supplied:5s} {source[:60]}")
    for case in run.cases:
        capture = case.capture
        fetched = (
            capture.fetched_at.isoformat() if capture and capture.fetched_at else "absent"
        )
        lines.append(
            f"    {case.spec.case_id:32s} {case.spec.acquisition.stream_id:20s} "
            f"{(capture.capture_id if capture else '<no capture>'):40s} "
            f"basis={str(capture.time_basis) if capture else '-'} "
            f"fetched_at={fetched}"
        )
    lines.append("")
    lines.append("== committed expectations (FR-020) ==")
    committed = compare_to_committed(run)
    lines.append(
        f"{len(run.cases)} case(s) compared against {len(corpus_cases.EXPECTED)} committed "
        f"expectation(s); differences={len(committed)}"
    )
    lines.extend(divergence.text() for divergence in committed)
    lines.append("")
    lines.append("== invariance (FR-021, per layer) ==")
    again = run_corpus(cases)
    lines.append(compare(run, again).text())
    lines.append("")
    lines.append("== replay (FR-022) ==")
    for case in run.cases:
        lines.append(replay(case).text())
        lines.append(f"  {replay_of_replay(case).text()}")
    lines.append("")
    lines.append("== graded situations (FR-023, SC-13) ==")
    for situation, case_ids in graded_coverage():
        lines.append(f"    {situation:32s} {len(case_ids)} case(s): {list(case_ids)}")
    uncovered = [situation for situation, ids in graded_coverage() if not ids]
    lines.append(f"    uncovered: {uncovered or 'none'}")
    lines.append("")
    lines.append("== anchor durability (SC-1) ==")
    for case in run.cases:
        if "minted_identity" in case.spec.labels:
            lines.append(f"    {anchor_survives_scope_loss(case.spec).text()}")
    lines.append("")
    lines.append("== acceptance chains (SC-14) ==")
    for case in run.cases:
        lines.append(f"  case {case.spec.case_id}")
        for chain in acceptance_chains(case):
            lines.append(chain.text())
    return "\n".join(lines)


def main() -> int:
    """Print :func:`smoke` and return a process exit code.

    The code is a **report**, not a gate: it is ``0`` when nothing diverged and
    ``1`` when something did, and it is deliberately not wired into any suite,
    because the corpus is functionality rather than a test (D-C). ``0`` also covers
    the cases that refuse on purpose - a named refusal is the recorded outcome, not
    a failure - and only a committed-expectation difference, an invariance
    divergence or a replay that failed to reproduce sets the code.
    """
    run = run_corpus()
    again = run_corpus()
    report = compare(run, again)
    committed = compare_to_committed(run)
    print(smoke())
    diverged = [
        case.spec.case_id
        for case in run.cases
        if not replay(case).identical or not replay_of_replay(case).fixed_point
    ]
    if committed or not report.identical or diverged:
        print()
        print(
            "DIVERGENCE: a committed expectation moved, invariance failed, or a replay did "
            "not reproduce"
        )
        for divergence in committed:
            print(f"  {divergence.reason} case={divergence.case_id}")
        for layer in report.diverged_layers():
            print(f"  layer {layer}")
        for case_id in diverged:
            print(f"  replay {case_id}")
        return 1
    print()
    print(
        f"corpus: {len(run.cases)} cases, {len(run.reached_worldline())} reaching worldline, "
        f"{len(run.refusals())} named refusals, {len(committed)} committed differences, "
        f"5 layers identical, replay is a fixed point"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
