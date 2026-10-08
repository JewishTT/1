"""The context fabric: every layer of spec 025 composed into one pass.

Each layer exists and is tested on its own -- cells, scope lattice, compatibility,
gluing, truth states, contradictions, independence, coverage-qualified absence,
dialectics, ranking, completeness, saturation. What no per-layer suite can show is
whether they compose, and composition is where the real defects live: a gluing
verdict that ignores independence is not wrong, it is a different kind of wrong.

This module is the composition point. It takes the durable state of a context plus
a batch of incoming observations and runs every layer in the order §I.7 fixes, then
reports what the investigation now owes.

Layer order is not cosmetic. Two orderings are load-bearing:

* **Observation before belief.** Cells grow from evidence before truth states are
  computed, because a truth state is a statement about a proposition and a
  proposition must live in a cell to be located later.
* **Independence before saturation.** Saturation consumes ``n_eff``, so computing it
  first would judge a syndication cluster as broad coverage.

This module deliberately emits neutral ``Finding`` objects rather than the engine's
own ``GapSignal``. ``GapSignal`` lives in ``context_engine.engine`` -- a *lower*
layer -- and ``apps/science`` may not import downward. The translation happens in
``control_plane/context_engine/fabric_bridge.py``, which is where the layer
direction permits it.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from context.argumentation import Candidate, GainTier, rank_candidates
from context.completeness import (
    RequestedMode,
    ResultSet,
    UniverseDefinition,
    assess_completeness,
)
from context.coverage import (
    CoverageQualifiedAbsence,
    IndependenceAssessment,
    SaturationState,
    assess_independence,
    assess_saturation,
)
from context.dialectics import (
    CounterHypothesisOutcome,
    DialecticalPair,
    Exhaustive,
    Hypothesis,
    HypothesisSpace,
    SteelmanParity,
    generate_counter_hypotheses,
)
from context.epistemic import (
    Contradiction,
    EvidenceContribution,
    Proposition,
    contradiction_for_both,
    derive_truth_state,
)
from context.growth import GrowthResult, extend_or_recompute_cells
from context.locality import ContextCell, Scope
from context.operators.compatibility import CompatibilityAssessment, assess_pair
from context.operators.gluing import GluingProfile, GluingResult, glue


class FindingKind(enum.StrEnum):
    """What a finding asks the investigation to do.

    Deliberately not the engine's ``TriggerKind``: this layer cannot import it, and
    duplicating its vocabulary would let the two drift. ``fabric_bridge`` maps one
    onto the other in one place.
    """

    CONTRADICTION = "contradiction"
    COVERAGE_GAP = "coverage_gap"
    OPERATOR_INTENT = "operator_intent"
    ANOMALY = "anomaly"
    LOW_CONFIDENCE = "low_confidence"
    SATURATION_SHORTFALL = "saturation_shortfall"
    UNRESOLVED_IDENTITY = "unresolved_identity"
    CONTESTED_LOCALITY = "contested_locality"


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing the investigation now owes, stated without engine vocabulary."""

    kind: FindingKind
    question: str
    rationale: str
    priority: float = 0.5
    refs: tuple[str, ...] = ()
    rule_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "question": self.question,
            "rationale": self.rationale,
            "priority": self.priority,
            "refs": list(self.refs),
            "rule_id": self.rule_id,
        }


@dataclass(frozen=True, slots=True)
class Observation:
    """One incoming observation, in the form the fabric consumes."""

    observation_id: str
    #: Entity referents this observation names; the scope derives from them.
    entities: tuple[str, ...] = ()
    #: Evidence ids supporting and refuting, for the truth-state derivation.
    supporting: tuple[str, ...] = ()
    refuting: tuple[str, ...] = ()
    #: The proposition this observation bears on, if any.
    subject: str = ""
    predicate: str = ""
    object: str = ""
    #: The cell that revealed this observation's scope; empty means nothing did.
    revealed_by: str = ""

    @property
    def scope(self) -> Scope:
        from context.locality import ScopeKind

        if self.entities:
            return Scope(ScopeKind.ENTITY, frozenset(self.entities))
        # No referents means no determination was made. That is a refusal to guess,
        # not an empty membership, and §7.2 distinguishes them.
        return Scope(ScopeKind.ENTITY, frozenset(), unknown=True)

    def contributions(self) -> tuple[EvidenceContribution, ...]:
        items = [
            EvidenceContribution(evidence_id, positive=True) for evidence_id in self.supporting
        ]
        items += [
            EvidenceContribution(evidence_id, positive=False) for evidence_id in self.refuting
        ]
        return tuple(items)


@dataclass(frozen=True, slots=True)
class FabricInput:
    """Everything one pass needs. Nothing is read from a store here."""

    context_id: str
    observations: tuple[Observation, ...] = ()
    existing_cells: tuple[ContextCell, ...] = ()
    #: hypothesis id -> Hypothesis, supplied by the caller so the fabric never
    #: invents a candidate the analyst did not put on the table.
    hypotheses: tuple[Hypothesis, ...] = ()
    question: str = ""
    coverage_evidence: Mapping[str, bool] = field(default_factory=dict)
    #: The scope the investigation declared, used only to bootstrap a first cell. It
    #: warrants the root; it is never used to place an observation.
    root_scope: Scope | None = None
    universe: UniverseDefinition = UniverseDefinition.REGISTERED_SOURCES
    parity: SteelmanParity | None = None
    gluing_profile: GluingProfile | None = None


@dataclass(frozen=True, slots=True)
class FabricReport:
    """The whole pass, every layer's output carried through."""

    context_id: str
    findings: tuple[Finding, ...] = ()
    growth: GrowthResult | None = None
    compatibility: tuple[CompatibilityAssessment, ...] = ()
    gluing: GluingResult | None = None
    propositions: tuple[Proposition, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    independence: IndependenceAssessment | None = None
    space: HypothesisSpace | None = None
    pairs: tuple[DialecticalPair, ...] = ()
    counterhypothesis_outcome: CounterHypothesisOutcome | None = None
    ranking: Mapping[str, Any] = field(default_factory=dict)
    completeness: Any = None
    saturation: SaturationState | None = None
    absences: tuple[CoverageQualifiedAbsence, ...] = ()
    result_set: ResultSet | None = None

    @property
    def cell_ids(self) -> tuple[str, ...]:
        return tuple(cell.cell_id for cell in (self.growth.cells if self.growth else ()))

    @property
    def has_contradictions(self) -> bool:
        return bool(self.contradictions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "findings": [finding.as_dict() for finding in self.findings],
            "cell_ids": list(self.cell_ids),
            "compatibility": [
                assessment.as_dict() for assessment in self.compatibility
            ],
            "gluing": self.gluing.as_dict() if self.gluing else {},
            "propositions": [item.as_dict() for item in self.propositions],
            "contradictions": [item.as_dict() for item in self.contradictions],
            "independence": self.independence.as_dict() if self.independence else {},
            "space": self.space.as_dict() if self.space else {},
            "pairs": [pair.as_dict() for pair in self.pairs],
            "counterhypothesis_outcome": (
                self.counterhypothesis_outcome.value if self.counterhypothesis_outcome else ""
            ),
            "ranking": dict(self.ranking),
            "completeness": self.completeness.as_dict() if self.completeness else {},
            "saturation": self.saturation.as_dict() if self.saturation else {},
            "absences": [absence.as_dict() for absence in self.absences],
            "result_set": self.result_set.as_dict() if self.result_set else {},
        }


def _pair_by_cell(cells: Sequence[ContextCell]) -> Mapping[tuple[str, str], tuple]:
    index = {cell.cell_id: cell for cell in cells}
    pairs = []
    for left_id, right_id in ((a.cell_id, b.cell_id) for a in cells for b in cells):
        if left_id == right_id:
            continue
        key = (left_id, right_id) if left_id < right_id else (right_id, left_id)
        if key in {existing for existing, _ in pairs}:
            continue
        left, right = index[key[0]], index[key[1]]
        pairs.append((key, (left, right)))
    return {key: value for key, value in pairs}


def run_fabric(payload: FabricInput) -> FabricReport:
    """Run every layer over one batch, in §I.7 order, and report the obligations."""
    cells = list(payload.existing_cells)
    findings: list[Finding] = []

    # -- §35/§I.7 growth -----------------------------------------------------
    incoming = {observation.observation_id: observation.scope for observation in payload.observations}
    revealed = {
        observation.observation_id: observation.revealed_by
        for observation in payload.observations
        if observation.revealed_by
    }
    growth = extend_or_recompute_cells(
        payload.context_id,
        tuple(cells),
        incoming,
        revealed_by=revealed,
        root_scope=payload.root_scope,
    )
    cells = list(growth.cells)

    for placement in growth.refused:
        findings.append(
            Finding(
                kind=(
                    FindingKind.UNRESOLVED_IDENTITY
                    if placement.outcome.value == "scope_undetermined"
                    else FindingKind.COVERAGE_GAP
                ),
                question=(
                    f"place observation {placement.observation_id}: no defensible scope"
                ),
                rationale=placement.reason,
                priority=0.6,
                refs=(placement.observation_id,),
                rule_id="growth.refused@1.0",
            )
        )

    # -- §9/§10 compatibility and gluing ------------------------------------
    compatibility = [
        assess_pair(left, right, overlap_id=f"OVL-{left.cell_id[4:12]}{right.cell_id[4:12]}",
                    method_fingerprint="compatibility.operator.v1")
        for left, right in _pair_by_cell(cells).values()
    ]
    gluing = glue(
        tuple(cells),
        context_id=payload.context_id,
        profile=payload.gluing_profile or GluingProfile(),
    )
    for assessment in compatibility:
        for dimension in assessment.blocking_dimensions:
            findings.append(
                Finding(
                    kind=FindingKind.CONTRADICTION,
                    question=(
                        f"resolve {dimension.value} conflict between two cells of "
                        f"{payload.context_id}"
                    ),
                    rationale=(
                        f"{dimension.value} is refuted; cells disagree on a dimension "
                        "the gluing rule cannot reconcile"
                    ),
                    priority=0.85,
                    refs=tuple(assessment.overlap_id for _ in (0,)),
                    rule_id="compatibility.blocking@1.0",
                )
            )
    for obstruction in gluing.obstructions:
        if obstruction.kind.value in {"triple_inconsistency", "source_conflict"}:
            findings.append(
                Finding(
                    kind=(
                        FindingKind.CONTRADICTION
                        if obstruction.kind.value == "source_conflict"
                        else FindingKind.CONTESTED_LOCALITY
                    ),
                    question=(
                        "explain joint inconsistency across cells that agree pairwise"
                        if obstruction.kind.value == "triple_inconsistency"
                        else "resolve conflicting evidence between overlapping cells"
                    ),
                    rationale=obstruction.detail,
                    priority=0.8,
                    refs=obstruction.subject_refs,
                    rule_id="gluing.obstruction@1.0",
                )
            )
        elif obstruction.kind.value == "missing_coverage":
            findings.append(
                Finding(
                    kind=FindingKind.COVERAGE_GAP,
                    question=f"determine the undetermined dimensions for {payload.context_id}",
                    rationale=obstruction.detail,
                    priority=0.4,
                    refs=obstruction.subject_refs,
                    rule_id="compatibility.unknown@1.0",
                )
            )

    # -- §13 truth states and contradictions ---------------------------------
    propositions: list[Proposition] = []
    contradictions: list[Contradiction] = []
    by_proposition: dict[str, tuple[Proposition, tuple[EvidenceContribution, ...]]] = {}
    for observation in payload.observations:
        if not (observation.subject and observation.predicate):
            continue
        proposition = Proposition(
            subject=observation.subject,
            predicate=observation.predicate,
            object=observation.object,
            scope=payload.context_id,
        )
        propositions.append(proposition)
        existing = by_proposition.get(proposition.proposition_id)
        contributions = observation.contributions()
        by_proposition[proposition.proposition_id] = (
            proposition,
            (existing[1] if existing else ()) + contributions,
        )

    for proposition, contributions in by_proposition.values():
        truth = derive_truth_state(contributions)
        settled = proposition.with_truth(truth)
        propositions = [
            settled if item.proposition_id == proposition.proposition_id else item
            for item in propositions
        ]
        contradiction = contradiction_for_both(
            settled,
            positive_refs=tuple(c.evidence_id for c in contributions if c.positive),
            negative_refs=tuple(c.evidence_id for c in contributions if not c.positive),
        )
        if contradiction is not None:
            contradictions.append(contradiction)
            findings.append(
                Finding(
                    kind=FindingKind.CONTRADICTION,
                    question=f"explain why {settled.subject} {settled.predicate} {settled.object}",
                    rationale=contradiction.detail,
                    priority=0.9,
                    refs=contradiction.subject_refs,
                    rule_id="epistemic.both@1.0",
                )
            )

    # -- §14A independence, before saturation -------------------------------
    evidence_items: list[str] = []
    lineage: dict[str, str] = {}
    for observation in payload.observations:
        for contribution in observation.contributions():
            evidence_items.append(contribution.evidence_id)
            lineage[contribution.evidence_id] = observation.observation_id
    independence = (
        assess_independence(evidence_items, lineage, assessed_by="independence.assess@1.0")
        if evidence_items
        else assess_independence([], {})
    )
    if not independence.independence_known:
        findings.append(
            Finding(
                kind=FindingKind.LOW_CONFIDENCE,
                question="establish lineage for evidence whose independence is unknown",
                rationale=independence.obstruction,
                priority=0.5,
                rule_id="independence.unknown@1.0",
            )
        )

    # -- §15/§18 hypothesis space and dialectics -----------------------------
    space: HypothesisSpace | None = None
    pairs: tuple[DialecticalPair, ...] = ()
    outcome: CounterHypothesisOutcome | None = None
    if payload.hypotheses:
        candidates = tuple(payload.hypotheses)
        residual = Hypothesis.residual(
            max(1e-6, 1.0 - sum(member.posterior for member in candidates))
        )
        ids = [member.local_id for member in candidates]
        space = HypothesisSpace(
            context_id=payload.context_id,
            question=payload.question or "what explains the observations?",
            members=candidates + (residual,),
            exclusivity_groups=(frozenset(ids),) if len(ids) > 1 else (),
            exhaustive=Exhaustive.FALSE,
        )
        thesis = candidates[0]
        pairs, outcome = generate_counter_hypotheses(
            space,
            thesis,
            templates=tuple(
                (member.local_id, member)
                for member in candidates
                if member.local_id != thesis.local_id
            ),
            parity=payload.parity,
        )
        if outcome is not CounterHypothesisOutcome.GENERATED:
            findings.append(
                Finding(
                    kind=FindingKind.LOW_CONFIDENCE,
                    question="no counter-hypothesis could be constructed for the leading explanation",
                    rationale=outcome.value,
                    priority=0.45,
                    refs=(thesis.local_id,),
                    rule_id="dialectics.no_counter@1.0",
                )
            )
        for pair in pairs:
            if not pair.parity.is_parity:
                findings.append(
                    Finding(
                        kind=FindingKind.LOW_CONFIDENCE,
                        question=(
                            f"rebuild counter-hypothesis for {pair.thesis.local_id} under "
                            "equal conditions"
                        ),
                        rationale=f"steelman parity failed on {list(pair.parity.failures)}",
                        priority=0.5,
                        refs=(pair.pair_id,),
                        rule_id="dialectics.parity@1.0",
                    )
                )

    # -- §20.3 ranking --------------------------------------------------------
    ranking: dict[str, Any] = {}
    if pairs:
        candidates = [
            Candidate(
                candidate_id=pair.pair_id,
                criteria={"contradictions": float(len(findings))},
                gain_tier=GainTier.UNKNOWN,
                feasible=not any(
                    finding.kind is FindingKind.CONTRADICTION for finding in findings
                ),
            )
            for pair in pairs
        ]
        if candidates:
            ranking = rank_candidates(candidates, mode="LEXICOGRAPHIC")

    # -- §33 completeness -----------------------------------------------------
    completeness = assess_completeness(
        universe=payload.universe,
        requested_mode=(
            RequestedMode.UNIVERSAL
            if any(finding.kind is FindingKind.OPERATOR_INTENT for finding in findings)
            else RequestedMode.BEST_EFFORT
        ),
        catalogue_exhausted=bool(payload.coverage_evidence.get("source_catalogue_exhausted")),
        temporal_scope_defined=bool(payload.coverage_evidence.get("temporal_scope_defined")),
        identity_resolution_complete=bool(
            payload.coverage_evidence.get("identity_resolution_complete")
        ),
        pagination_complete=bool(payload.coverage_evidence.get("pagination_complete")),
        source_errors_zero_or_accounted=bool(
            payload.coverage_evidence.get("source_errors_zero_or_accounted")
        ),
    )

    # -- §22 saturation, last, because it consumes n_eff ----------------------
    saturation = assess_saturation(
        obligation_id=f"OBL-{payload.context_id[4:12]}",
        assessment=independence,
        coverage=completeness.conditions[0].satisfied and 1.0 or None,
        source_families=len({lineage[item] for item in lineage}),
        contradiction_count=len(contradictions),
        unresolved_obstruction_count=len(gluing.obstructions),
    )
    for reason in saturation.reason_codes:
        if reason.value.startswith("insufficient") or reason.value == "unexplored_capability":
            findings.append(
                Finding(
                    kind=(
                        FindingKind.COVERAGE_GAP
                        if "coverage" in reason.value
                        else FindingKind.SATURATION_SHORTFALL
                    ),
                    question=f"close saturation gap: {reason.value}",
                    rationale=(
                        f"saturation is {saturation.verdict.value}; "
                        f"n_eff={saturation.effective_independent_sources} "
                        f"of {saturation.distinct_sources} items"
                    ),
                    priority=0.35,
                    rule_id="saturation.reason@1.0",
                )
            )

    return FabricReport(
        context_id=payload.context_id,
        findings=tuple(findings),
        growth=growth,
        compatibility=tuple(compatibility),
        gluing=gluing,
        propositions=tuple(propositions),
        contradictions=tuple(contradictions),
        independence=independence,
        space=space,
        pairs=pairs,
        counterhypothesis_outcome=outcome,
        ranking=ranking,
        completeness=completeness,
        saturation=saturation,
    )