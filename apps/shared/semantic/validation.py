"""Layered graded validation: six stages, five verdicts, and no deletion anywhere.

Feature 017, T019 / T020, FR-011 / FR-012, SC-4 / SC-8 / SC-9.

Three properties are load-bearing and each of them is structural - there is no method here that a
future change could quietly turn into a gate.

**One. Every stage returns a graded verdict, never a boolean.** The five values in
:class:`~semantic.contracts.Verdict` are kept apart because two of them mean completely different
things. ``INVALID`` and ``CONFLICTING`` are *contradictions*: something asserted is wrong, or two
sources disagree. ``UNKNOWN`` and ``UNSUPPORTED`` are *inability to evaluate*: no profile declares
this type, the operator declared no domain/range hint, the required evidence pattern is one this
build does not know, or a capability is not installed. Collapsing the second pair into the first
is how a platform ends up deleting real evidence, so :func:`~semantic.contracts.is_adverse` is the
only predicate that decides something is wrong and a stage that cannot answer says
``UNKNOWN``/``UNSUPPORTED`` with a machine-readable ``code``. The canonical case is
``not_declared_in_profile``: a profile that does not list ``local:shell_company_shell`` is not a
profile that refutes it (US1, FR-001), and a validator that reported ``INVALID`` there would be
re-creating the admission gate this feature was written to remove.

**Two. A finding is data, and the assertion survives it (FR-012).** This module has no method
that filters, rejects, deprojects or drops a claim, and the absence is deliberate: the only
outward-facing results are a :class:`~semantic.contracts.ValidationReport` and a
:class:`MaterialisationDecision`, both of which are *records*. The decision is the answer to the
one question an operator may legitimately ask - "does this claim belong in **my** view?" - and it
returns a named, scoped value rather than a boolean precisely because a bare ``False`` is read as
"no". Reading a refused :class:`MaterialisationDecision` means one thing only: *this operator does
not admit this claim into this operator's materialised view.* It is not a claim that the relation
does not exist, and it is never a deletion (see :attr:`MaterialisationDecision.scope_statement`).
Under the default :attr:`~semantic.operators.DomainRangePolicy.WARN` a ``works_for`` whose object
is a ``Document`` produces a finding and the claim is still materialised and still projected, which
is SC-8 and US4 exactly. :attr:`~semantic.operators.DomainRangePolicy.EXCLUDE_FROM_VIEW` exists at
all because an operator author sometimes needs a derived, curated dataset where a domain/range
violation means the extractor is broken rather than the world is; it is opt-in per operator, it is
never the default (D1), and even then it decides one projection and nothing else - it does not
delete the claim, and no finding produced anywhere in this file carries the authority to.

**Three. Stages are independent.** :meth:`LayeredValidator.evaluate_stage` evaluates exactly one
stage, so a caller that has no profile to check against can still run structural and temporal
checks, and a caller that wants to know what was *not* checked reads
:meth:`~semantic.contracts.ValidationReport.unevaluated_stages`. A stage that declined to run
produces no finding at all rather than a passing one, which is what makes that report honest: a
stage appears there iff it was never evaluated, and a stage that ran and passed says so
explicitly with a ``VALID`` finding.

**What a verdict is and is not.** The verdict grades the *check*, never the claim's fate. A
domain/range hint is a declaration the platform made about its own operator (FR-006, FR-013), so a
member outside it is a genuine contradiction of that contract and is reported ``INVALID`` with the
policy named in the message. What that policy does to one particular view is
:func:`decide_materialisation`'s business, and it answers with a named, operator-scoped decision
rather than a boolean. Keeping those two separate - a contract contradiction is a finding, an
admission outcome is a projection decision - is the whole reason a failure can be a finding and
not a deletion, and it is why a refusal is never itself an adverse verdict
(:attr:`MaterialisationDecision.is_adverse`).

**Bounded and deterministic.** No I/O, no network, no LLM, no clock: the temporal and graph
stages read the claim's own recorded times and a caller-supplied claim set, and the graph walks
are bounded by :data:`MAX_GRAPH_NODES` / :data:`MAX_GRAPH_WALK_STEPS` and refuse to grow without
limit (constitution VI, VIII).

**What the validator examines: material or claim (FR-011, D5, SC-6).** Every stage takes a
:class:`ValidatableRelation`, which is :class:`domain.relation_claim_material.RelationClaimMaterial`
(an unadmitted, self-consistent value carrying its own derived ids) *or* a
:class:`domain.relation_claim.RelationClaim`. Before 018 the input was a ``RelationClaim`` alone,
which made admission a precondition of examination: the only value this module could be handed
was one already in the graph, so a hypothesis could not be graded, quoted or reported, and a
task-scoped consumer had nothing to look at. Widening the input changes **what may be examined**,
not **what is checked**, and the three reasons it is not a weakening are structural rather than
promised:

* The validator is a reader. It reads a fixed, enumerated surface off its subject - the endpoint
  pair, the arity mode, the role bindings, the validity window, the evidence and context refs,
  the independence groups, the schema version and the two derived ids. It assigns to none of them
  and returns no reduced set of subjects, so accepting a second value with the same read surface
  grants it no capability a claim did not have.
* Every stage's *logic* is untouched, including the ones that only make sense for an admitted
  value. A relation with no ``status`` is not a relation the graph has thrown away, because a
  :class:`~domain.relation_claim_material.RelationClaimMaterial` has no ``status`` field to throw
  away - the absence is the point, and it is checked at import in
  :mod:`domain.relation_claim_material`.
* Nothing that requires a *committed* claim was widened. :func:`decide_materialisation` still
  receives no claim and therefore still cannot delete one, and
  :func:`domain.relation_claim_material.require_committed` remains the typed boundary for
  consumers that can only read the graph.

The one place the input's shape genuinely differs is :func:`_subject_contradicts`, and the
difference is a fact rather than a fallback: ``contradicts`` links *committed claims*, so an
unadmitted reading has none - a claim contradicting it cannot exist yet, because nothing about
it has been admitted.

Dependency reality: this module imports nothing that is not already in the workspace. SHACL is
somewhere else entirely - see :mod:`semantic.shacl`, an opt-in sidecar that this module neither
calls nor depends on.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias

from domain.evidence_context import EvidenceContext
from domain.relation_claim import RelationClaim
from semantic.contracts import (
    TypeAssertion,
    ValidationFinding,
    ValidationReport,
    ValidationStage,
    Verdict,
)
from semantic.operators import DomainRangePolicy, RelationOperator
from semantic.profiles import ProfileResolution
from semantic.regime import SemanticRegime
from semantic.vocabularies import normalize_surface_form

if TYPE_CHECKING:
    from domain.relation_claim_material import RelationClaimMaterial

#: Everything this module will accept as the subject of a check: unadmitted claim material or a
#: committed claim. Named rather than repeated inline because it appears on every stage signature
#: and the name is the documentation - "a validatable relation" says the input is read and graded
#: without saying anything about whether it is in the graph.
#:
#: A string alias on purpose: the material type lives in
#: :mod:`domain.relation_claim_material`, which imports *this* module to delegate
#: :func:`~domain.relation_claim_material.validate`, so a runtime import here would close a cycle.
#: ``from __future__ import annotations`` means no signature is ever evaluated, and the type
#: checker resolves the alias through the ``TYPE_CHECKING`` import above.
ValidatableRelation: TypeAlias = "RelationClaimMaterial | RelationClaim"

__all__ = [
    "MAX_GRAPH_NODES",
    "MAX_GRAPH_WALK_STEPS",
    "STAGE_ORDER",
    "Endpoint",
    "LayeredValidator",
    "MaterialisationCode",
    "MaterialisationDecision",
    "MaterialisationScope",
    "StageOutcome",
    "ValidatableRelation",
    "decide_materialisation",
    "worst_verdict",
]

#: Ceiling on how many claims a graph-level stage will consider. Past it the stage reports
#: ``UNSUPPORTED`` rather than walking a graph nobody bounded (constitution VIII).
MAX_GRAPH_NODES = 4096

#: Ceiling on one transitivity walk. A cycle in relation data is legitimate input, so the walk
#: is bounded rather than trusted to terminate, and hitting the bound is reported as
#: ``UNKNOWN`` with ``truncated`` spelled out rather than guessed at.
MAX_GRAPH_WALK_STEPS = 1024

#: The fixed stage order FR-011 specifies, taken from the enum's own declaration order so the two
#: cannot drift apart.
STAGE_ORDER: tuple[ValidationStage, ...] = tuple(ValidationStage)

#: Graded precedence, worst first. Mirrors
#: :meth:`semantic.contracts.ValidationReport.verdict_for` so a per-stage answer and a per-report
#: answer never disagree about what "worst" means. Note where ``UNSUPPORTED`` sits: below
#: ``UNKNOWN``, because "we could not evaluate this" and "the capability is missing" are both
#: non-findings and neither outranks the other.
_VERDICT_PRECEDENCE: tuple[Verdict, ...] = (
    Verdict.INVALID,
    Verdict.CONFLICTING,
    Verdict.UNKNOWN,
    Verdict.UNSUPPORTED,
    Verdict.VALID,
)

#: Which evidence-requirement tokens this build can actually check, keyed by their
#: :func:`~semantic.vocabularies.normalize_surface_form` form. A token outside this table is
#: reported ``UNKNOWN`` rather than assumed satisfied - an unrecognised requirement is a check
#: this build cannot perform, and assuming it passed would be a false ``VALID`` (SC-9).
_EVIDENCE_TOKENS: frozenset[str] = frozenset(
    {
        "assertion",
        "assertions",
        "context",
        "evidence context",
        "independent source",
        "mention pair",
        "observation",
        "relation pattern",
        "source",
        "source document",
    }
)


def worst_verdict(findings: Iterable[ValidationFinding]) -> Verdict:
    """The most serious verdict among ``findings``, or ``VALID`` for none.

    "Most serious" is the order in :data:`_VERDICT_PRECEDENCE`, and the two middle entries are
    both *not* failures - a stage that answered ``UNSUPPORTED`` is not worse than one that
    answered ``UNKNOWN``, and neither is worse than a real contradiction.
    """
    seen = {Verdict(finding.verdict) for finding in findings}
    for verdict in _VERDICT_PRECEDENCE:
        if verdict in seen:
            return verdict
    return Verdict.VALID


class MaterialisationCode(StrEnum):
    """The stable identity of one materialisation decision.

    Written out in full because these values are the contract with anything that reads a decision
    back - a log line, a stored record, a test - and an abbreviation would be free to drift. Each
    names an *admission* outcome for one operator and view; none of them describes the claim's
    fate, and none is reachable from a default-constructed
    :class:`~semantic.operators.RelationOperator` (D1).
    """

    ADMITTED_BY_VIEW = "operator_view_admits_claim"
    EXCLUDED_BY_VIEW = "operator_view_excludes_claim"
    UNCONSTRAINED = "operator_view_unconstrained_admits_claim"


class MaterialisationScope(StrEnum):
    """What a materialisation decision is *about*, so it cannot be read as being about more.

    The only two answers are "this operator's view" and "no operator's view", because the only
    thing an operator can decide about a claim is whether its own projection of that relation
    type carries it. Neither value is a claim about the world: not that the relation does not
    exist, not that the claim is false, and never a deletion. The scope is a *recorded field* of
    :class:`MaterialisationDecision` rather than a convention, so a decision that is read back
    months later still states its own reach.
    """

    THIS_OPERATOR_VIEW = "this_operator_view"
    NO_OPERATOR_VIEW = "no_operator_view"

    @property
    def statement(self) -> str:
        """The scope spelled out in full, for a message, a log line or a stored record."""
        return _SCOPE_STATEMENTS[self]


_SCOPE_STATEMENTS: dict[MaterialisationScope, str] = {
    MaterialisationScope.THIS_OPERATOR_VIEW: (
        "scoped to this operator's materialised view: this operator does not admit this claim "
        "into this view, the claim object and its evidence are unchanged, this is not a claim "
        "that the relation does not exist, and nothing was deleted"
    ),
    MaterialisationScope.NO_OPERATOR_VIEW: (
        "scoped to no operator's view: no operator is declared for this relation type, so no "
        "operator withholds the claim, the claim object and its evidence are unchanged, and "
        "nothing was deleted"
    ),
}


@dataclass(frozen=True)
class MaterialisationDecision:
    """One operator's admission decision about one claim, scoped to one materialised view.

    This exists because a bare boolean could not say *what* was refused, and ``False`` is read as
    "no" - as "the relation is not real", as "the claim was rejected", as "something was dropped".
    Reading :attr:`refused` here means exactly one thing:

    **this operator does not admit this claim into this operator's materialised view.**

    It is not a statement that the relation does not exist, it is not a verdict that the claim is
    false, and it is not a deletion. The claim, its evidence and the :attr:`findings` that
    motivated the decision are all still present, still queryable and still resolvable (FR-012,
    SC-4). A second operator with a different policy reaches a different - equally correct -
    decision about the same claim, and both decisions are representable at once, because
    :attr:`scope` is part of the value rather than an assumption made by the reader.

    **A refusal is an operator decision, not a failing check.** :attr:`is_adverse` is a hard-wired
    ``False``: it is not a field and not derived, so no caller can make an admission decision
    reportable as a validation failure. If a refusal could be counted as adverse it would be read
    as "the claim is bad", which is a different claim - about the world - that an operator is not
    entitled to make. The :attr:`findings` carried here may individually be adverse, and correctly
    so: a domain/range hint is a contract the platform declared about its own operator (FR-006),
    and a member outside it genuinely contradicts that contract. The decision those findings
    motivated is not itself a verdict about the claim (FR-011, FR-012).

    Deliberately has no ``__bool__``. Truthiness would collapse this back into the bare boolean
    this type exists to replace, and the default truthiness would read an exclusion as an
    admission - the one failure mode worth engineering against.
    """

    materialisable: bool
    code: MaterialisationCode
    scope: MaterialisationScope
    policy: DomainRangePolicy
    operator_ref: str = ""
    findings: tuple[ValidationFinding, ...] = ()

    @property
    def refused(self) -> bool:
        """Whether this operator withheld the claim from its own view.

        The inverse of :attr:`materialisable`, under a name that says the subject is the operator's
        admission rather than the claim's standing.
        """
        return not self.materialisable

    @property
    def is_adverse(self) -> bool:
        """Always ``False``: a refusal is an operator decision, not a verdict on the claim.

        Invariant rather than a field so that no value a caller can supply turns a projection
        decision into a failing validation finding.
        """
        return False

    @property
    def scope_statement(self) -> str:
        """The recorded scope in words, including the three things it is not."""
        return self.scope.statement


def decide_materialisation(
    operator: RelationOperator | DomainRangePolicy | None,
    *,
    findings: Iterable[ValidationFinding] = (),
) -> MaterialisationDecision:
    """The admission decision one operator makes about a claim for its own view.

    Three inputs, three answers, and no path to a refusal that a default operator can take:

    * no operator at all -> :attr:`MaterialisationCode.UNCONSTRAINED` and materialisable. An
      undeclared relation is unconstrained, not vetoed (FR-001, FR-013).
    * an operator declaring :attr:`~semantic.operators.DomainRangePolicy.WARN` or
      :attr:`~semantic.operators.DomainRangePolicy.IGNORE` ->
      :attr:`MaterialisationCode.ADMITTED_BY_VIEW` and materialisable. This is the only path a
      default-constructed :class:`~semantic.operators.RelationOperator` can take, because
      ``WARN`` is its default (D1).
    * an operator that explicitly opted into
      :attr:`~semantic.operators.DomainRangePolicy.EXCLUDE_FROM_VIEW` ->
      :attr:`MaterialisationCode.EXCLUDED_BY_VIEW` and **not materialisable in that operator's
      view**, with :attr:`MaterialisationScope.THIS_OPERATOR_VIEW` recorded on the decision.

    **Why the claim is not a parameter.** The function never receives the claim, so no branch
    inside it can delete, filter, mutate or withhold one. ``findings`` are recorded and never
    consumed - they travel with the decision so a reader can see what the operator reacted to, and
    passing them changes nothing about the outcome. The claim is not consulted, copied away or
    marked; the caller keeps the object it already had, evidence and all (FR-012).
    """
    reasons = tuple(findings)
    if operator is None:
        return MaterialisationDecision(
            materialisable=True,
            code=MaterialisationCode.UNCONSTRAINED,
            scope=MaterialisationScope.NO_OPERATOR_VIEW,
            policy=DomainRangePolicy.WARN,
            findings=reasons,
        )
    if isinstance(operator, DomainRangePolicy):
        policy = DomainRangePolicy(operator)
        operator_ref = ""
    else:
        policy = DomainRangePolicy(operator.domain_range_policy)
        operator_ref = f"{operator.relation_type}@{operator.schema_version}"
    refused = policy.excludes_from_view
    return MaterialisationDecision(
        materialisable=not refused,
        code=(
            MaterialisationCode.EXCLUDED_BY_VIEW
            if refused
            else MaterialisationCode.ADMITTED_BY_VIEW
        ),
        scope=MaterialisationScope.THIS_OPERATOR_VIEW,
        policy=policy,
        operator_ref=operator_ref,
        findings=reasons,
    )


class Endpoint(StrEnum):
    """Which end of a relation a check is about. Local so this module depends on nothing extra."""

    SUBJECT = "subject"
    OBJECT = "object"


@dataclass(frozen=True)
class StageOutcome:
    """What one stage decided, and whether it decided anything at all.

    ``findings`` empty means the stage **did not evaluate** - an operator with no domain/range
    hints, a stage outside the caller's requested subset, a policy of ``ignore``. It never means
    "passed". :attr:`evaluated` exists so a caller does not have to infer that from a tuple, and
    so a stage that answered ``VALID`` (one finding) is distinguishable from a stage that was
    never asked (:data:`STAGE_ORDER` subsets, and
    :meth:`~semantic.contracts.ValidationReport.unevaluated_stages` in the assembled report).
    """

    stage: ValidationStage
    findings: tuple[ValidationFinding, ...] = ()
    note: str = ""

    @property
    def evaluated(self) -> bool:
        return bool(self.findings)

    @property
    def verdict(self) -> Verdict:
        return worst_verdict(self.findings)

    @property
    def adverse(self) -> tuple[ValidationFinding, ...]:
        """Only the findings that indicate a real problem (FR-012)."""
        return tuple(finding for finding in self.findings if finding.is_adverse)


class LayeredValidator:
    """Runs the six stages in order and returns graded findings. Never removes anything.

    The validator is a **reader**. It is handed what exists - the material or the claim, the
    operator contract bound to it, the profile regime, the type assertions, the frames, the other
    claims - and it reports. It holds no mutable state of its own, mutates nothing it is given,
    and has no method that returns a filtered or reduced set of claims. The name
    ``LayeredValidator`` means "produces a layered report", not "decides what survives".

    **Admission is not a precondition of examination (FR-011, SC-6).** The subject is a
    :data:`ValidatableRelation`: a :class:`domain.relation_claim_material.RelationClaimMaterial`
    will do, and a material that no admission would ever accept is graded by exactly the same
    six stages as a committed claim. The report's ``target_ref`` is the subject's own derived id
    either way, and because those ids are settled before admission, a report written against
    material is a report written against the claim that will exist. What is *not* widened:
    :func:`decide_materialisation` still takes no claim, and nothing here creates, deletes or
    rewrites one (FR-013).

    Every input is optional except the subject, and each omission has one honest consequence
    rather than a default guess:

    * no ``operator`` for the relation type -> ``UNKNOWN``/``operator_not_declared``. An unknown
      relation is admissible (FR-001) and an undeclared one is unconstrained, which is not the
      same as being right (FR-013).
    * no ``resolution`` -> profile-dependent checks are skipped rather than assumed. Supplying a
      profile is how a caller says "check against *this* regime"; omitting it says nothing was
      declared, and ``not_declared_in_profile`` is only reported when a profile was actually
      supplied and did not list the type.
    * no ``type_assertions`` for a member -> ``UNKNOWN``/``member_kind_unknown``. Pruning on an
      absent fact is an assertion by omission, the same discipline
      :attr:`~semantic.blocking.UnknownKindPolicy.RETAIN` applies.
    * no ``contexts`` -> provenance cannot be resolved and says so.
    """

    def __init__(
        self,
        *,
        operators: Mapping[str, RelationOperator] | None = None,
        resolution: ProfileResolution | None = None,
        type_assertions: Mapping[str, Sequence[TypeAssertion]] | None = None,
        contexts: Mapping[str, EvidenceContext] | None = None,
        claims: Iterable[RelationClaim] = (),
        regime: SemanticRegime | None = None,
        max_graph_nodes: int = MAX_GRAPH_NODES,
    ) -> None:
        self._operators: dict[str, RelationOperator] = {
            str(key): value for key, value in (operators or {}).items()
        }
        self._resolution = resolution
        self._type_assertions: dict[str, tuple[TypeAssertion, ...]] = {
            str(key): tuple(value) for key, value in (type_assertions or {}).items()
        }
        self._contexts: dict[str, EvidenceContext] = {
            str(key): value for key, value in (contexts or {}).items()
        }
        self._claims: tuple[RelationClaim, ...] = tuple(claims)
        self._regime = regime
        self._max_graph_nodes = int(max_graph_nodes)

    @property
    def regime(self) -> SemanticRegime | None:
        """The regime this validator attributes its findings to, if one was supplied."""
        return self._regime

    @property
    def resolution(self) -> ProfileResolution | None:
        """The profile regime the semantic stage checks against, if one was supplied."""
        return self._resolution

    def operator_for(self, relation_type: str) -> RelationOperator | None:
        """The closed contract for one relation type, or ``None`` when none was declared.

        ``None`` is a normal answer and never a failure. A relation type no operator describes is
        exactly US1's case for relations: it is admitted, it is materialised, and the only
        consequence is that the structural, temporal, provenance and semantic stages have no
        contract to check it against and say ``UNKNOWN`` (FR-013).
        """
        return self._operators.get(str(relation_type))

    def type_refs_for(self, entity_ref: str) -> tuple[str, ...]:
        """Every type reference asserted for one member, across all layers, canonically ordered.

        Deliberately across all four :class:`~semantic.contracts.TypeScope` layers: an entity is
        ``core:Entity`` observed and ``schema:Person`` mapped at the same time (US2, FR-003), and
        a domain/range check that only looked at one layer would be reading a partial record as a
        whole one.
        """
        return tuple(
            sorted(
                {
                    assertion.type_ref
                    for assertion in self._type_assertions.get(str(entity_ref), ())
                    if assertion.type_ref
                }
            )
        )

    def admission_decision(self, claim: ValidatableRelation) -> MaterialisationDecision:
        """This relation's operator's admission decision for ``claim``, in its own view.

        Runs the semantic stage to obtain the findings that motivate the decision and returns the
        decision carrying them, so a caller has one value to record instead of a boolean to
        interpret. The subject is read and never rewritten: the same object, with the same
        evidence and the same identity, is what the caller holds afterwards whether the answer is
        admission or exclusion (FR-012, SC-4).

        The decision is operator-scoped, so two validators holding two operators with different
        policies reach two different decisions about the same subject and **both are correct** -
        there is no global answer to return, and this method does not pretend to give one. That
        is also why it is safe to call on unadmitted material: it decides one operator's view and
        commits nothing, so it is the same call before and after :func:`admit`.
        """
        operator = self.operator_for(claim.relation_type)
        outcome = self._check_semantic(claim)
        return decide_materialisation(operator, findings=outcome.findings)

    def evaluate(
        self,
        claim: ValidatableRelation,
        *,
        stages: Iterable[ValidationStage] = STAGE_ORDER,
    ) -> ValidationReport:
        """Run the requested stages in fixed order and assemble one content-addressed report.

        Defaults to all six. The ``stages`` argument exists so a caller can evaluate a subset -
        and then read :meth:`~semantic.contracts.ValidationReport.unevaluated_stages` to see
        exactly which stages were not checked, rather than inferring coverage from a clean
        report. Ordering is normalised to :data:`STAGE_ORDER` regardless of how the subset was
        written, so two callers asking for the same subset get byte-identical reports
        (constitution VI).

        The subject may be unadmitted material (FR-011), and it is passed through untouched.
        Nothing in this call, or anywhere else in this module, deletes or rewrites it, and the
        returned report is a *separate* object that references it (FR-012, SC-4).
        """
        wanted = _ordered_stages(stages)
        findings: list[ValidationFinding] = []
        for stage in wanted:
            findings.extend(self.evaluate_stage(stage, claim).findings)
        return self.report_for(claim, findings)

    def evaluate_stage(
        self, stage: ValidationStage, claim: ValidatableRelation
    ) -> StageOutcome:
        """Evaluate exactly one stage. Independently callable, for partial validation.

        The point of exposing each stage: a caller with no profile can still run structural and
        temporal checks, a caller that has already been told about a domain/range problem need
        not re-derive it, and a stage that cannot be evaluated reports that without the other
        five being suppressed (FR-011). The subject is material or a claim alike (FR-011, SC-6).
        """
        wanted = ValidationStage(stage)
        checkers: dict[ValidationStage, Callable[[ValidatableRelation], StageOutcome]] = {
            ValidationStage.STRUCTURAL: self._check_structural,
            ValidationStage.SEMANTIC: self._check_semantic,
            ValidationStage.TEMPORAL: self._check_temporal,
            ValidationStage.PROVENANCE: self._check_provenance,
            ValidationStage.CROSS_SOURCE: self._check_cross_source,
            ValidationStage.GRAPH_LEVEL: self._check_graph_level,
        }
        return checkers[wanted](claim)

    def evaluate_all(
        self,
        claims: Iterable[ValidatableRelation],
        *,
        stages: Iterable[ValidationStage] = STAGE_ORDER,
    ) -> tuple[ValidationReport, ...]:
        """Validate several subjects, in the order supplied, returning every report.

        Returns a report per subject and never fewer, and never a subject that was dropped for
        having failed. A caller wanting only the clean ones filters the *reports* - and
        :meth:`~semantic.contracts.ValidationReport.adverse_findings` is the honest way to ask -
        but the subjects themselves are untouched (FR-012).
        """
        return tuple(self.evaluate(claim, stages=stages) for claim in claims)

    def report_for(
        self, claim: ValidatableRelation, findings: Iterable[ValidationFinding]
    ) -> ValidationReport:
        """Assemble a report from findings, carrying the regime context onto it.

        The report is content-addressed via :meth:`~semantic.contracts.ValidationReport.with_id`,
        so the same subject validated under the same regime with the same outcome is provably the
        same report - which is what makes an event-sourced rebuild able to detect a validation
        that changed its mind (constitution VII).

        ``target_ref`` is the subject's own derived id, and for material that id is already the
        id the claim will carry, so a report built before admission is the report
        :func:`domain.relation_claim_material.admit` will be asked to decide against.
        """
        return ValidationReport(
            tenant_id=claim.tenant_id,
            target_ref=claim.relation_id,
            profile_ref=self._resolution.profile.profile_id if self._resolution else "",
            profile_version=self._resolution.profile.version if self._resolution else "",
            mapping_set_version=self._regime.mapping_set_version_ref if self._regime else "",
            findings=tuple(findings),
        ).with_id()

    def _finding(
        self,
        claim: ValidatableRelation,
        stage: ValidationStage,
        verdict: Verdict,
        code: str,
        message: str,
        *,
        constraint_ref: str = "",
        evidence_refs: Iterable[str] = (),
    ) -> ValidationFinding:
        """One graded finding, attributed to the regime that produced it.

        The ``profile_ref`` and ``context_ref`` it carries are the regime context a reader needs
        to reproduce the check - not a statement that the check was authorised by them. A finding
        with no profile attached is still a valid finding, and that is the case an open world
        produces constantly (FR-001).
        """
        return ValidationFinding(
            tenant_id=claim.tenant_id,
            assertion_ref=claim.relation_id,
            stage=stage,
            verdict=verdict,
            code=code,
            message=message,
            constraint_ref=constraint_ref,
            profile_ref=(
                self._resolution.profile.version_ref if self._resolution else ""
            ),
            context_ref=claim.context_ref,
            evidence_refs=tuple(evidence_refs),
        ).with_id()

    def _undeclared_operator(
        self, claim: ValidatableRelation, stage: ValidationStage
    ) -> ValidationFinding:
        return self._finding(
            claim,
            stage,
            Verdict.UNKNOWN,
            "operator_not_declared",
            f"no operator contract is declared for {claim.relation_type!r}; this stage has no "
            "contract to check the claim against, which is unevaluable rather than wrong "
            "(FR-013)",
        )

    def _check_structural(self, claim: ValidatableRelation) -> StageOutcome:
        """Arity, direction and role bindings against the operator's own shape (FR-006).

        The only stage that compares structure to structure. A relation type with no declared
        operator is admitted and reported ``UNKNOWN``; a claim whose arity contradicts a declared
        operator is a genuine ``INVALID``, because the contract is the platform's own statement
        and the world did not make it.
        """
        stage = ValidationStage.STRUCTURAL
        operator = self.operator_for(claim.relation_type)
        if operator is None:
            return StageOutcome(stage, (self._undeclared_operator(claim, stage),))

        findings: list[ValidationFinding] = []
        if claim.arity_mode is not operator.arity_mode:
            findings.append(
                self._finding(
                    claim,
                    stage,
                    Verdict.INVALID,
                    "arity_mismatch",
                    f"claim is {claim.arity_mode} but operator {operator.relation_type}@"
                    f"{operator.schema_version} declares {operator.arity_mode}",
                    constraint_ref=operator.relation_type,
                )
            )
        if operator.roles and claim.role_bindings:
            declared = set(operator.roles)
            for binding in claim.role_bindings:
                if binding.role not in declared:
                    findings.append(
                        self._finding(
                            claim,
                            stage,
                            Verdict.INVALID,
                            "role_not_declared",
                            f"role {binding.role!r} is not one of the operator's declared roles "
                            f"{sorted(declared)}",
                            constraint_ref=f"{operator.relation_type}.{binding.role}",
                        )
                    )
        if not findings:
            findings.append(
                self._finding(
                    claim,
                    stage,
                    Verdict.VALID,
                    "structural_contract_satisfied",
                    f"claim shape is consistent with operator {operator.relation_type}@"
                    f"{operator.schema_version}",
                    constraint_ref=operator.relation_type,
                )
            )
        return StageOutcome(stage, tuple(findings), "arity, direction and roles")

    def _check_semantic(self, claim: ValidatableRelation) -> StageOutcome:
        """Domain and range hints, graded, with the operator's policy attached to the finding.

        The ordering of the refusals is the substance of SC-9. Before anything can be called a
        violation, three things must hold: an operator must declare a hint for that end; the
        member must actually have a type asserted; and - when a profile was supplied - the
        regime must have declared that type. Each failure is ``UNKNOWN`` with its own code,
        because each is a *limit on what we know*, not a contradiction. Only a member whose
        asserted types are all known to the regime and all outside the declared hints produces
        ``INVALID``, and even then :attr:`DomainRangePolicy.WARN` - the default - leaves the claim
        materialisable (D1, FR-012).

        Kinds are compared as **opaque references, case-preserving and exact**, so an operator's
        hint and a member's assertion have to be spelled in the same vocabulary to meet. That is
        deliberate and it is the same discipline :func:`normalize_surface_form` /
        :func:`~semantic.vocabularies.normalize_type_ref` keep apart: deciding that
        ``local:Influencer`` and ``schema:Person`` are close enough to satisfy a hint *is* a
        mapping assertion, and mappings are recorded in :mod:`semantic.mappings` with provenance
        and then cited - never inferred by a validator to make its own check pass.

        The ``VALID`` finding is emitted **only when the stage produced no other finding at all**.
        A stage that answered ``not_declared_in_profile`` for one end has established nothing, and
        a ``VALID`` emitted beside it would put two contradictory findings in one stage and make
        :meth:`~semantic.contracts.ValidationReport.verdict_for` answer a question nobody should be
        asking. Silence is the honest output when there is nothing to add.
        """
        stage = ValidationStage.SEMANTIC
        operator = self.operator_for(claim.relation_type)
        if operator is None:
            return StageOutcome(stage, (self._undeclared_operator(claim, stage),))
        if operator.domain_range_policy is DomainRangePolicy.IGNORE:
            return StageOutcome(
                stage,
                (),
                f"operator {operator.relation_type} declares domain_range=ignore; the stage was "
                "not run rather than passed",
            )

        findings: list[ValidationFinding] = []
        constrained = False
        for endpoint, member_ref, declared in (
            (Endpoint.SUBJECT, claim.subject_ref, operator.subject_kinds),
            (Endpoint.OBJECT, claim.object_ref, operator.object_kinds),
        ):
            if not declared:
                continue
            constrained = True
            findings.extend(
                self._endpoint_findings(claim, operator, endpoint, member_ref, declared)
            )
        if constrained and not findings:
            findings.append(
                self._finding(
                    claim,
                    stage,
                    Verdict.VALID,
                    "domain_range_satisfied",
                    "every constrained end was asserted within the operator's declared hints",
                    constraint_ref=operator.relation_type,
                )
            )
        return StageOutcome(stage, tuple(findings), "domain and range hints")

    def _endpoint_findings(
        self,
        claim: ValidatableRelation,
        operator: RelationOperator,
        endpoint: Endpoint,
        member_ref: str,
        declared_kinds: Sequence[str],
    ) -> tuple[ValidationFinding, ...]:
        """One end's domain/range verdict, in refusal order: undeclared, then unknown, then judged.

        The order is what makes SC-9 hold. A type the profile never declared cannot be judged
        against a hint, so it is ``UNKNOWN``/``not_declared_in_profile`` and no ``INVALID`` is
        produced for that end - the world being unfamiliar is not the world being wrong (US1).
        """
        stage = ValidationStage.SEMANTIC
        asserted = self.type_refs_for(member_ref)
        if not asserted:
            return (
                self._finding(
                    claim,
                    stage,
                    Verdict.UNKNOWN,
                    "member_kind_unknown",
                    f"{endpoint} {member_ref!r} has no asserted type, so it can be neither "
                    "confirmed nor contradicted against the declared hints",
                    constraint_ref=f"{operator.relation_type}.{endpoint}_kinds",
                ),
            )
        if self._resolution is not None:
            known = tuple(t for t in asserted if self._resolution.has_type(t))
            if not known:
                return (
                    self._finding(
                        claim,
                        stage,
                        Verdict.UNKNOWN,
                        "not_declared_in_profile",
                        f"{endpoint} {member_ref!r} is typed {list(asserted)}, none of which "
                        f"profile {self._resolution.profile.version_ref!r} declares; an "
                        "undeclared type is unknown to this regime, not refuted by it (FR-001)",
                        constraint_ref=f"{operator.relation_type}.{endpoint}_kinds",
                    ),
                )
            asserted = known
        satisfied = [t for t in asserted if t in set(declared_kinds)]
        if satisfied:
            return ()
        return (
            self._finding(
                claim,
                stage,
                Verdict.INVALID,
                "domain_range_not_satisfied",
                f"{endpoint} {member_ref!r} is typed {list(asserted)}, outside the operator's "
                f"declared {endpoint}_kinds {list(declared_kinds)}; the finding is recorded, "
                f"and {_admission_clause(operator)}",
                constraint_ref=f"{operator.relation_type}.{endpoint}_kinds",
            ),
        )

    def _check_temporal(self, claim: ValidatableRelation) -> StageOutcome:
        """The claim's validity window against the operator's declared temporal semantics.

        Constitution V is why this is checkable at all: ``observed_at`` (when the platform
        learned it) and ``valid_from``/``valid_to`` (when it was true) are different fields, so a
        claim whose window contradicts the operator's declared mode is a real contradiction while
        a claim that simply never stated a window is only an incomplete record.
        """
        stage = ValidationStage.TEMPORAL
        operator = self.operator_for(claim.relation_type)
        if operator is None:
            return StageOutcome(stage, (self._undeclared_operator(claim, stage),))

        semantics = str(operator.temporal)
        constraint = f"{operator.relation_type}.temporal"
        if claim.valid_from and claim.valid_to and claim.valid_to < claim.valid_from:
            return StageOutcome(
                stage,
                (
                    self._finding(
                        claim,
                        stage,
                        Verdict.INVALID,
                        "validity_interval_inverted",
                        f"valid_to {claim.valid_to.isoformat()} precedes valid_from "
                        f"{claim.valid_from.isoformat()}",
                        constraint_ref=constraint,
                    ),
                ),
                "validity window",
            )
        if semantics == "required_interval" and not (claim.valid_from and claim.valid_to):
            return StageOutcome(
                stage,
                (
                    self._finding(
                        claim,
                        stage,
                        Verdict.INVALID,
                        "required_temporal_interval_missing",
                        f"operator declares temporal={semantics} but the claim records no "
                        "validity interval",
                        constraint_ref=constraint,
                    ),
                ),
                "validity window",
            )
        if semantics == "point":
            if claim.valid_from is None:
                return StageOutcome(
                    stage,
                    (
                        self._finding(
                            claim,
                            stage,
                            Verdict.UNKNOWN,
                            "temporal_point_unknown",
                            "operator declares temporal=point but the claim records no instant, "
                            "so the point cannot be checked",
                            constraint_ref=constraint,
                        ),
                    ),
                    "validity window",
                )
            if claim.valid_to is not None and claim.valid_to != claim.valid_from:
                return StageOutcome(
                    stage,
                    (
                        self._finding(
                            claim,
                            stage,
                            Verdict.INVALID,
                            "interval_on_point_claim",
                            "operator declares temporal=point but the claim records a span",
                            constraint_ref=constraint,
                        ),
                    ),
                    "validity window",
                )
        return StageOutcome(
            stage,
            (
                self._finding(
                    claim,
                    stage,
                    Verdict.VALID,
                    "temporal_contract_satisfied",
                    f"validity window is consistent with the operator's temporal={semantics}",
                    constraint_ref=constraint,
                ),
            ),
            "validity window",
        )

    def _check_provenance(self, claim: ValidatableRelation) -> StageOutcome:
        """Whether the claim carries the evidence its operator demands, and a resolvable frame.

        Evidence requirements are checked against a small table of tokens this build understands.
        A token outside it is reported ``UNKNOWN``/``evidence_requirement_unknown`` rather than
        assumed satisfied, which is the difference between an honest instrument and one that
        rubber-stamps requirements it never read.
        """
        stage = ValidationStage.PROVENANCE
        operator = self.operator_for(claim.relation_type)
        if operator is None:
            return StageOutcome(stage, (self._undeclared_operator(claim, stage),))

        findings: list[ValidationFinding] = []
        for requirement in operator.evidence_requirements:
            satisfied = _evidence_satisfied(claim, requirement)
            if satisfied is None:
                findings.append(
                    self._finding(
                        claim,
                        stage,
                        Verdict.UNKNOWN,
                        "evidence_requirement_unknown",
                        f"evidence requirement {requirement!r} is not one this build can check; "
                        "assuming it passed would be a false VALID (SC-9)",
                        constraint_ref=f"{operator.relation_type}.{requirement}",
                    )
                )
            elif not satisfied:
                findings.append(
                    self._finding(
                        claim,
                        stage,
                        Verdict.INVALID,
                        "evidence_requirement_unmet",
                        f"evidence requirement {requirement!r} is unmet: the claim carries "
                        f"{len(claim.observation_refs)} observation refs and "
                        f"{len(claim.assertion_refs)} assertion refs",
                        constraint_ref=f"{operator.relation_type}.{requirement}",
                        evidence_refs=claim.observation_refs,
                    )
                )

        context = self._contexts.get(claim.context_ref)
        if claim.context_ref and self._contexts is not None and context is None:
            findings.append(
                self._finding(
                    claim,
                    stage,
                    Verdict.UNKNOWN,
                    "context_unresolved",
                    f"evidence context {claim.context_ref!r} is not held by this validator, so "
                    "provenance cannot be read; no default frame is substituted (FR-016)",
                )
            )
        elif context is not None:
            findings.extend(self._frame_findings(claim, context))
        if not claim.extraction_version:
            findings.append(
                self._finding(
                    claim,
                    stage,
                    Verdict.UNKNOWN,
                    "extraction_version_unknown",
                    "the claim records no extraction version, so reproducibility cannot be "
                    "established (constitution VII)",
                )
            )
        if not findings:
            findings.append(
                self._finding(
                    claim,
                    stage,
                    Verdict.VALID,
                    "provenance_established",
                    "the claim carries the evidence its operator requires and a resolvable frame",
                    constraint_ref=operator.relation_type,
                    evidence_refs=claim.observation_refs,
                )
            )
        return StageOutcome(stage, tuple(findings), "evidence and frame")

    def _frame_findings(
        self, claim: ValidatableRelation, context: EvidenceContext
    ) -> tuple[ValidationFinding, ...]:
        """What a resolved frame says about the claim's provenance.

        ``DISPUTED`` is a contradiction - the frame declares its own content has been challenged -
        and ``PARTIAL``/``FRAGMENT`` is only an incomplete record. The two are deliberately not
        given the same verdict, because a disputed frame and a fragmentary one call for different
        amounts of scepticism and only one of them is a defect.
        """
        findings: list[ValidationFinding] = []
        if str(context.trust_state) == "disputed":
            findings.append(
                self._finding(
                    claim,
                    ValidationStage.PROVENANCE,
                    Verdict.INVALID,
                    "context_trust_disputed",
                    f"the evidence context {context.context_id} is disputed, so provenance is "
                    "not established; the claim and its evidence remain intact (FR-012)",
                    constraint_ref=context.context_id,
                )
            )
        if str(context.completeness) != "complete":
            findings.append(
                self._finding(
                    claim,
                    ValidationStage.PROVENANCE,
                    Verdict.UNKNOWN,
                    "context_incomplete",
                    f"the evidence context {context.context_id} declares completeness="
                    f"{context.completeness}, so provenance cannot be fully evaluated",
                    constraint_ref=context.context_id,
                )
            )
        return tuple(findings)

    def _check_cross_source(self, claim: ValidatableRelation) -> StageOutcome:
        """Corroboration across independent sources, and contradictions between claims.

        Two counts stay apart here for the reason they are kept apart in the store:
        ``publication_count`` is how many observations were published and
        ``independent_source_count`` is how many source families stand behind them. One
        independent group with three publications is *one* source syndicated three times, and
        reporting it as ``VALID`` corroboration would grade evidence on volume (constitution IV).
        """
        stage = ValidationStage.CROSS_SOURCE
        declared = _subject_contradicts(claim)
        contradicting = tuple(
            sibling.logical_relation_id
            for sibling in self._claims
            if sibling.relation_id != claim.relation_id
            and sibling.logical_relation_id == claim.logical_relation_id
            and claim.relation_id in _subject_contradicts(sibling)
        )
        if contradicting:
            return StageOutcome(
                stage,
                (
                    self._finding(
                        claim,
                        stage,
                        Verdict.CONFLICTING,
                        "cross_source_conflict",
                        f"{len(contradicting)} claim(s) of the same logical relation contradict "
                        f"this one; disagreement is reported and never resolved by deletion "
                        "(FR-012)",
                        evidence_refs=declared,
                    ),
                ),
                "independent corroboration",
            )
        if claim.independent_source_count == 0:
            return StageOutcome(
                stage,
                (
                    self._finding(
                        claim,
                        stage,
                        Verdict.UNKNOWN,
                        "no_independence_recorded",
                        "the claim records no independence group, so corroboration cannot be "
                        "evaluated; that is an unrecorded fact, not a failed one",
                    ),
                ),
                "independent corroboration",
            )
        if claim.independent_source_count == 1 and claim.publication_count > 1:
            return StageOutcome(
                stage,
                (
                    self._finding(
                        claim,
                        stage,
                        Verdict.UNKNOWN,
                        "single_independence_group",
                        f"{claim.publication_count} publications rest on one independence group, "
                        "which is repetition rather than corroboration (constitution IV)",
                        evidence_refs=claim.observation_refs,
                    ),
                ),
                "independent corroboration",
            )
        return StageOutcome(
            stage,
            (
                self._finding(
                    claim,
                    stage,
                    Verdict.VALID,
                    "cross_source_agreement",
                    f"{claim.independent_source_count} independent source groups stand behind "
                    "the claim",
                    evidence_refs=claim.observation_refs,
                ),
            ),
            "independent corroboration",
        )

    def _check_graph_level(self, claim: ValidatableRelation) -> StageOutcome:
        """Checks that are only decidable against other claims: versions, inverses, cycles.

        A single claim cannot contradict itself, so with no claim set the honest answer is
        ``UNKNOWN``/``graph_view_absent`` rather than a clean bill of health. That distinction
        matters more than it looks: a graph-level stage that reported ``VALID`` on an isolated
        claim would be claiming to have checked consistency it had no material to check with.
        """
        stage = ValidationStage.GRAPH_LEVEL
        if len(self._claims) > self._max_graph_nodes:
            return StageOutcome(
                stage,
                (
                    self._finding(
                        claim,
                        stage,
                        Verdict.UNSUPPORTED,
                        "graph_view_too_large",
                        f"the claim set holds {len(self._claims)} claims, over the "
                        f"{self._max_graph_nodes}-node bound; no graph-level check was run "
                        "(constitution VIII)",
                    ),
                ),
                "graph-wide consistency",
            )
        others = tuple(c for c in self._claims if c.relation_id != claim.relation_id)
        if not others:
            return StageOutcome(
                stage,
                (
                    self._finding(
                        claim,
                        stage,
                        Verdict.UNKNOWN,
                        "graph_view_absent",
                        "no other claim is in view, so graph-level consistency has nothing to "
                        "check against; one claim cannot contradict itself",
                    ),
                ),
                "graph-wide consistency",
            )

        findings: list[ValidationFinding] = []
        operator = self.operator_for(claim.relation_type)
        same_type = tuple(c for c in others if c.relation_type == claim.relation_type)
        versions = {claim.schema_version} | {c.schema_version for c in same_type}
        if len(versions) > 1:
            findings.append(
                self._finding(
                    claim,
                    stage,
                    Verdict.UNKNOWN,
                    "mixed_schema_versions",
                    f"claims of {claim.relation_type!r} are recorded under schema versions "
                    f"{sorted(versions)}; which contract applies is not decidable here",
                    constraint_ref=claim.relation_type,
                )
            )
        if operator is not None:
            findings.extend(self._inverse_findings(claim, operator, others))
            cycle = _transitivity_cycle(claim, same_type)
            if cycle:
                findings.append(
                    self._finding(
                        claim,
                        stage,
                        Verdict.INVALID,
                        "transitivity_cycle",
                        f"{claim.relation_type} is declared transitive but the claims close a "
                        f"cycle through {claim.subject_ref!r}: {' -> '.join(cycle)}",
                        constraint_ref=claim.relation_type,
                    )
                )
        if not findings:
            findings.append(
                self._finding(
                    claim,
                    stage,
                    Verdict.VALID,
                    "graph_consistent",
                    "no contradiction found against the other claims in view",
                    constraint_ref=claim.relation_type,
                )
            )
        return StageOutcome(stage, tuple(findings), "graph-wide consistency")

    def _inverse_findings(
        self,
        claim: ValidatableRelation,
        operator: RelationOperator,
        others: Sequence[RelationClaim],
    ) -> tuple[ValidationFinding, ...]:
        """Inverse consistency, only when the operator declares an inverse to check against.

        An operator that declares no inverse produces nothing here: the absence of a declared
        inverse is not a claim that the relation is symmetric, and inventing one would be the
        platform asserting a fact about the operator nobody declared.
        """
        if not operator.inverse_relation_type:
            return ()
        forward = tuple(
            c
            for c in others
            if c.relation_type == operator.inverse_relation_type
            and (c.subject_ref, c.object_ref) == (claim.subject_ref, claim.object_ref)
        )
        if forward:
            return (
                self._finding(
                    claim,
                    ValidationStage.GRAPH_LEVEL,
                    Verdict.CONFLICTING,
                    "inverse_direction_conflict",
                    f"{len(forward)} claim(s) assert the inverse relation "
                    f"{operator.inverse_relation_type!r} in the same direction as "
                    f"{claim.relation_type!r}; both are recorded and neither is deleted (FR-012)",
                    constraint_ref=f"{claim.relation_type}~{operator.inverse_relation_type}",
                ),
            )
        return ()


def _ordered_stages(stages: Iterable[ValidationStage]) -> tuple[ValidationStage, ...]:
    """The requested stages, de-duplicated and in the fixed order, whatever order they came in."""
    wanted = {ValidationStage(stage) for stage in stages}
    return tuple(stage for stage in STAGE_ORDER if stage in wanted)


def _admission_clause(operator: RelationOperator) -> str:
    """What this operator's policy does, as a clause for a finding's message.

    Rendered from the decision rather than from the policy name so a finding's text carries the
    *scope* of the consequence next to the contradiction that produced it: this operator's view,
    not the world (FR-012, D1). The clause therefore also carries the negative space - the claim
    is unchanged, the relation is not denied to exist, nothing was deleted - so a reader of the
    finding alone cannot come away thinking the claim was rejected.
    """
    decision = decide_materialisation(operator)
    return (
        f"under domain_range={operator.domain_range_policy} the admission decision is "
        f"{decision.scope_statement}"
    )


def _subject_contradicts(subject: ValidatableRelation) -> tuple[str, ...]:
    """The committed claim ids a subject declares itself to contradict.

    The one place the widened input is genuinely shaped differently from a claim, and the answer
    is a fact rather than a fallback. ``contradicts`` links *committed claims*, and it is written
    when a claim is admitted that disputes this one - so an unadmitted
    :class:`domain.relation_claim_material.RelationClaimMaterial` holds none, not because a
    default was supplied but because a claim contradicting it cannot exist yet. Reading
    ``()`` for material is therefore the correct value, and the empty tuple is the honest answer
    rather than an unevaluated one: a hypothesis is contradicted by nothing, because it has not
    entered the graph to be contradicted.

    Read through this one function for the subject *and* for each peer, so the same rule is
    applied symmetrically and no call site can reintroduce an ``AttributeError`` by reaching for
    the field directly.
    """
    return tuple(str(ref) for ref in getattr(subject, "contradicts", ()) or ())


def _evidence_satisfied(claim: ValidatableRelation, requirement: str) -> bool | None:
    """Whether one evidence requirement is met, or ``None`` when this build cannot check it.

    ``None`` is the load-bearing return: it is what turns an unrecognised requirement into
    ``UNKNOWN`` rather than a silent pass. The checkable tokens are deliberately few and every
    one of them is a fact the claim itself carries, so nothing here has to be inferred.
    """
    token = normalize_surface_form(requirement)
    if token not in _EVIDENCE_TOKENS:
        return None
    if token == "mention pair":
        return len(claim.observation_refs) >= 2
    if token in {"observation", "relation pattern", "source document"}:
        return len(claim.observation_refs) >= 1
    if token in {"assertion", "assertions"}:
        return len(claim.assertion_refs) >= 1
    if token in {"context", "evidence context"}:
        return bool(claim.context_ref)
    return claim.independent_source_count >= 1


def _transitivity_cycle(
    claim: ValidatableRelation, peers: Sequence[RelationClaim]
) -> tuple[str, ...]:
    """A path back to ``claim.subject_ref`` through declared-transitive claims, or ``()``.

    A cycle in relation data is legitimate input - people are employed by companies that are
    subsidiaries of each other - so the walk is bounded (:data:`MAX_GRAPH_WALK_STEPS`) and
    deterministic (neighbours visited in sorted order) rather than trusted to terminate, and
    returns the path it took so the finding can show its work. An empty result means no cycle
    *within the walk budget*, which is exactly what the finding claims.
    """
    if not peers:
        return ()
    edges: dict[str, set[str]] = {}
    for peer in peers:
        edges.setdefault(peer.subject_ref, set()).add(peer.object_ref)
    start = claim.subject_ref
    path: list[str] = [start]
    frontier = [start]
    visited: set[str] = {start}
    for _ in range(MAX_GRAPH_WALK_STEPS):
        if not frontier:
            return ()
        current = frontier.pop(0)
        for neighbour in sorted(edges.get(current, ())):
            if neighbour == start and len(path) > 1:
                return tuple([*path, start])
            if neighbour in visited:
                continue
            visited.add(neighbour)
            path.append(neighbour)
            frontier.append(neighbour)
    return ()
