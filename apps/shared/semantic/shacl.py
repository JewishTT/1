"""SHACL over a disposable RDF projection of the native graph, as an opt-in sidecar.

Feature 017, T022 / T023, FR-010, decisions D4 and constitution II/VIII.

**The native store is not an RDF database and is not required to become one.** The graph's
foundation is Observation/Mention/Assertion/Relation/Entity/TemporalWorldline, addressed by
``digest128`` content ids, and it stays exactly that way. :func:`build_rdf_view` is a
**projection**: it reads frozen records and emits triples into a throwaway
:class:`rdflib.Graph`, and nothing is written back. The RDF view is *derived and disposable* -
delete it, rebuild it from the native graph, and the native graph is bit-identical. That is what
"no second backbone" means operationally: RDF appears where an external instrument needs it and
goes away again, and there is no path by which a triple becomes authoritative (constitution II,
spec "Out of Scope": no triplestore, no Jena, RDF never canonical).

**pySHACL is optional, and its absence is specified behaviour, not a gap.** It is not installed
here and :func:`validate_with_shacl` does not care: the import happens **inside the call**, in a
``try: ... except ImportError``, and an absent library produces a report whose finding is
``Verdict.UNSUPPORTED`` with code ``pyshacl_unavailable``. Three things it will never do, and each
of them would be a serious defect:

* **never raise** for a missing capability - a sidecar that takes the caller down is a sidecar
  that ends up on the write path, which is the one place it must not be;
* **never report ``VALID``** because it did not run - that is the false-clean-bill-of-health this
  whole design exists to prevent, and it is why a missing *shapes graph* is also ``UNSUPPORTED``
  rather than vacuously conformant;
* **never mutate the canonical graph** - the input graph is read-only for the duration, results
  come back in a separate report, and no function here has a parameter that would let a caller
  write back.

**Off the write path, and bounded (constitution VIII).** :class:`ShaclSidecar` is opt-in by
construction: it is ``enabled=False`` by default and a disabled sidecar reports
``UNSUPPORTED``/``sidecar_disabled`` without building anything, so the cheapest way to have this
instrument on a write path is a flag someone has to deliberately set. The view it builds is
capped by :class:`RdfViewBudget` in both nodes and edges, and the cap **raises
:class:`RdfViewTooLarge` rather than truncating**. Truncating would be the single worst outcome
available here: SHACL would validate a subset of the graph and report the subset as conformant,
which is a false ``VALID`` arrived at by a different route. Refusing is loud, and only the
opt-in entry point :meth:`ShaclSidecar.validate` degrades that refusal into a graded
``UNSUPPORTED`` report, because that is the boundary where "an instrument was not run" is a
normal answer. Nothing ingests, extracts or projects through here.

**Deterministic and open-world-safe.** No network, no I/O, no LLM: the view is a pure function of
the records handed in, minted from a synthetic ``urn:`` namespace with percent-encoded local parts
so an internal id can never be mistaken for a resolvable IRI (spec open question 3 - a synthetic
namespace, deliberately, and never the internal id space pretending to be a URI). An entity with
no asserted type is projected *untyped* rather than defaulted to something plausible, because the
view's job is to carry the facts a shape can check, not to pre-empt the shape's verdict. And
nothing in the projection asserts that two references denote one thing; a mapping is emitted as a
recorded correspondence, if at all, and never as identity.

This is the only module permitted to import ``rdflib`` (FR-005).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import SH

from domain.evidence_context import EvidenceContext
from domain.relation_claim import RelationClaim
from semantic.contracts import (
    TypeAssertion,
    ValidationFinding,
    ValidationReport,
    ValidationStage,
    Verdict,
)
from semantic.operators import RelationOperator
from semantic.regime import SemanticRegime

__all__ = [
    "DEFAULT_MAX_EDGES",
    "DEFAULT_MAX_NODES",
    "RDF_VIEW_BASE",
    "RdfViewBudget",
    "RdfViewTooLarge",
    "ShaclSidecar",
    "ShaclSidecarError",
    "build_rdf_view",
    "pyshacl_available",
    "validate_with_shacl",
]

#: Synthetic, non-resolvable base for every IRI the view mints. A ``urn:`` namespace is chosen
#: over an ``http:`` one so nothing in the view can ever be mistaken for a fetchable address, and
#: over the internal id space so an internal id is never dressed up as an ontology IRI.
RDF_VIEW_BASE = "urn:cognitive:semantic:view:"

#: The view's own vocabulary, for shapes to target.
RDF_VIEW_NS = Namespace(f"{RDF_VIEW_BASE}ns#")

#: Node ceiling on a projected view. Sized for a validation batch and small enough that a runaway
#: loop cannot turn one sidecar call into an unbounded allocation (constitution VIII).
DEFAULT_MAX_NODES = 20_000

#: Edge (triple) ceiling on a projected view, tracked as the view is built rather than afterwards.
DEFAULT_MAX_EDGES = 100_000

#: Local names minted in the view's namespace, in one place so a shape author can read them here.
_CLASSES: dict[str, str] = {
    "relation": "Relation",
    "entity": "Entity",
    "operator": "RelationOperator",
    "context": "EvidenceContext",
    "regime": "SemanticRegime",
    "typing": "TypeAssertion",
}


class ShaclSidecarError(Exception):
    """Base for the typed failures this module raises.

    Every one of them is about *the instrument*, never about content: an oversized projection, a
    shapes graph that will not parse, an engine that failed. None is ever a reason a claim is
    refused or removed (FR-012), and a caller can catch the whole class with one ``except``.
    """


class RdfViewTooLarge(ShaclSidecarError):
    """The projection exceeded its node or edge budget and was abandoned.

    Raised, never truncated. A view that stopped half-way would let a shape report a subset of
    the graph as conformant, and a conformant subset is a false ``VALID`` - the precise failure
    FR-011 and D4 forbid. Refusing costs a re-run with a larger :class:`RdfViewBudget`; silently
    trimming costs correctness nobody would notice.
    """

    def __init__(self, what: str, observed: int, limit: int) -> None:
        self.what = what
        self.observed = int(observed)
        self.limit = int(limit)
        super().__init__(
            f"{what} reached {observed}, over the {limit} bound; the view was abandoned rather "
            "than truncated, because a truncated view validates a subset and would report a "
            "false VALID (constitution VIII)"
        )


@dataclass(frozen=True)
class RdfViewBudget:
    """The node and edge ceiling a projection is held to.

    ``check`` is called as the view is built, so an oversized view is abandoned before it is
    materialised rather than measured after the memory was already spent. The bounds are
    constructor arguments with package-level defaults, so a caller with a genuinely large graph
    can raise them deliberately and leave a record of having done so.
    """

    max_nodes: int = DEFAULT_MAX_NODES
    max_edges: int = DEFAULT_MAX_EDGES

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_nodes", int(self.max_nodes))
        object.__setattr__(self, "max_edges", int(self.max_edges))
        if self.max_nodes < 1 or self.max_edges < 1:
            raise ValueError(
                f"a view budget must be positive, got nodes={self.max_nodes}, "
                f"edges={self.max_edges}"
            )

    def exceeded_by(self, nodes: int, edges: int) -> str:
        """Which bound the given sizes break, or ``""`` when they fit. The one place the two
        bounds are compared, so :meth:`check` and any caller asking the same question cannot
        disagree about what "too large" means."""
        if edges > self.max_edges:
            return f"edges {edges} > {self.max_edges}"
        if nodes > self.max_nodes:
            return f"nodes {nodes} > {self.max_nodes}"
        return ""

    def check(self, nodes: int, edges: int) -> None:
        """Refuse the view if it has outgrown either bound. Nothing is truncated, ever."""
        breach = self.exceeded_by(nodes, edges)
        if not breach:
            return
        edges_breached = edges > self.max_edges
        raise RdfViewTooLarge(
            "rdf view edge count" if edges_breached else "rdf view node count",
            edges if edges_breached else nodes,
            self.max_edges if edges_breached else self.max_nodes,
        )


def _minted(kind: str, reference: str) -> URIRef:
    """One view-local IRI for a native reference.

    Percent-encoded with no safe characters, so a reference containing ``/``, ``#`` or a colon
    cannot forge a different path or smuggle a fragment into the IRI. The mapping is injective,
    so two distinct native refs can never collapse into one node - which matters because a
    collapsed node would be validated as a single subject and hide a real violation.
    """
    return URIRef(f"{RDF_VIEW_BASE}{kind}/{quote(str(reference), safe='')}")


def _literal(value: object) -> Literal | None:
    """One plain literal, or ``None`` for an absent value. Absence stays absence, not ``""``."""
    if value is None:
        return None
    text = str(value)
    return Literal(text) if text else None


def _moment(value: datetime | None) -> str | None:
    """One timestamp as canonical text."""
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value else None)


class _BudgetedView:
    """Accumulates triples while holding the budget, so the guard runs as the view is built.

    Small and private on purpose: the counting is bookkeeping, and the public contract is
    :func:`build_rdf_view` returning a ``Graph`` or raising.
    """

    def __init__(self, graph: Graph, budget: RdfViewBudget) -> None:
        self._graph = graph
        self._budget = budget
        self._nodes: set[URIRef] = set()
        self._edges = 0

    def add(self, subject: URIRef, predicate: URIRef, obj: object) -> None:
        """Add one triple, counting the edge first so the budget trips before the allocation."""
        self._edges += 1
        self._budget.check(0, self._edges)
        self._nodes.add(subject)
        self._nodes.add(obj if isinstance(obj, URIRef) else subject)
        self._graph.add((subject, predicate, obj))
        self._budget.check(len(self._nodes), self._edges)

    def bind(self, subject: URIRef, name: str) -> None:
        self.add(subject, RDF.type, RDF_VIEW_NS[_CLASSES[name]])


def _member_view(
    view: _BudgetedView, entity_ref: str, assertions: Sequence[TypeAssertion]
) -> URIRef:
    """Project one member: its identity, every asserted type across all layers, and its typing.

    Every :class:`~semantic.contracts.TypeScope` layer is projected, because an entity is
    ``core:Entity`` observed and ``schema:Person`` mapped simultaneously (US2, FR-003) and a view
    showing one of them would be showing a partial record. A member with no assertions is
    projected with ``view:typed false`` and **no** type at all - the view reports what is missing
    rather than inventing something a shape could then pass.
    """
    node = _minted("node", entity_ref)
    view.bind(node, "entity")
    view.add(node, RDF_VIEW_NS.ref, Literal(str(entity_ref)))
    typed = False
    for assertion in sorted(assertions, key=lambda a: (a.type_ref, str(a.scope), str(a.status))):
        if not assertion.type_ref:
            continue
        typed = True
        view.add(node, RDF_VIEW_NS.kind, Literal(assertion.type_ref))
        view.add(node, RDF_VIEW_NS.typing, _typed_node(view, assertion))
    view.add(node, RDF_VIEW_NS.typed, Literal(typed, datatype=XSD.boolean))
    return node


def _typed_node(view: _BudgetedView, assertion: TypeAssertion) -> URIRef:
    """A node for one typing, so a shape can constrain scope and status per layer.

    Minted from the assertion's content key rather than its id, so it is derived rather than
    stored and the same typing always projects to the same node (constitution VI). Scope and
    status travel with it because a mapped type and an observed type of the same reference are
    different claims, and a shape that could not tell them apart would be reading a partial
    record (US2, FR-003).
    """
    node = _minted("typing", assertion.content_key())
    view.bind(node, "typing")
    view.add(node, RDF_VIEW_NS.typeRef, Literal(assertion.type_ref))
    view.add(node, RDF_VIEW_NS.scope, Literal(str(assertion.scope)))
    view.add(node, RDF_VIEW_NS.status, Literal(str(assertion.status)))
    return node


def build_rdf_view(
    claims: Iterable[RelationClaim],
    relations: Mapping[str, RelationOperator] | Iterable[RelationOperator] = (),
    *,
    type_assertions: Mapping[str, Sequence[TypeAssertion]] | None = None,
    contexts: Mapping[str, EvidenceContext] | None = None,
    regime: SemanticRegime | None = None,
    budget: RdfViewBudget | None = None,
) -> Graph:
    """Project native records into a disposable :class:`rdflib.Graph` for shapes to check.

    ``relations`` accepts either a mapping keyed by relation type or a plain iterable of
    operators, because a caller holding a registry and a caller holding a list should not have to
    know which shape this function prefers. Each operator is projected as a node carrying its
    **declared** hints (``view:domainKind``, ``view:rangeKind``, ``view:requiresEvidence``) and
    *not* applied to the members. This is deliberate: a view that already agreed with the operator
    would make every shape a tautology, and the whole point of the sidecar is to check a
    projection against something written independently of it.

    The return value is a fresh graph holding only what these records say. There is no parameter
    that writes back, no reference to the native records is retained, and dropping the graph
    loses nothing. Passing an oversized input raises :class:`RdfViewTooLarge` from the budget
    rather than returning a partial view (constitution VIII).
    """
    operators = _operator_map(relations)
    assertions = {
        str(key): tuple(value) for key, value in (type_assertions or {}).items()
    }
    frames = {str(key): value for key, value in (contexts or {}).items()}
    graph = Graph()
    graph.bind("view", RDF_VIEW_NS)
    graph.bind("sh", SH)
    view = _BudgetedView(graph, budget or RdfViewBudget())

    for key in sorted(operators):
        _project_operator(view, operators[key])

    ordered_claims = tuple(sorted(claims, key=lambda c: c.relation_id))
    for claim in ordered_claims:
        relation = _project_claim(view, claim, assertions, frames)
        if regime is not None and claim.context_ref:
            view.add(relation, RDF_VIEW_NS.regime, _project_regime(view, regime))

    return graph


def _operator_map(
    relations: Mapping[str, RelationOperator] | Iterable[RelationOperator],
) -> dict[str, RelationOperator]:
    """Operators keyed by relation type, from either a mapping or an iterable of them."""
    if isinstance(relations, Mapping):
        return {str(key): value for key, value in relations.items()}
    return {operator.relation_type: operator for operator in relations}


def _project_operator(view: _BudgetedView, operator: RelationOperator) -> URIRef:
    """Project one operator's contract, as declarations a shape can point at."""
    node = _minted("operator", f"{operator.relation_type}@{operator.schema_version}")
    view.bind(node, "operator")
    view.add(node, RDF_VIEW_NS.relationType, Literal(operator.relation_type))
    view.add(node, RDF_VIEW_NS.schemaVersion, Literal(operator.schema_version))
    view.add(node, RDF_VIEW_NS.arityMode, Literal(str(operator.arity_mode)))
    view.add(node, RDF_VIEW_NS.domainRangePolicy, Literal(str(operator.domain_range_policy)))
    view.add(node, RDF_VIEW_NS.temporalSemantics, Literal(str(operator.temporal)))
    for kind in operator.subject_kinds:
        view.add(node, RDF_VIEW_NS.domainKind, Literal(kind))
    for kind in operator.object_kinds:
        view.add(node, RDF_VIEW_NS.rangeKind, Literal(kind))
    for requirement in operator.evidence_requirements:
        view.add(node, RDF_VIEW_NS.requiresEvidence, Literal(requirement))
    if operator.inverse_relation_type:
        view.add(node, RDF_VIEW_NS.inverseRelation, Literal(operator.inverse_relation_type))
    return node


def _project_claim(
    view: _BudgetedView,
    claim: RelationClaim,
    assertions: Mapping[str, Sequence[TypeAssertion]],
    frames: Mapping[str, EvidenceContext],
) -> URIRef:
    """Project one claim and everything it points at, in that order.

    Claims are visited in ``relation_id`` order by the caller, so the view - and therefore its
    ``content_key``-shaped consumers and any diff between two runs - is reproducible regardless of
    the order the claims arrived in (constitution VI).
    """
    relation = _minted("relation", claim.relation_id)
    view.bind(relation, "relation")
    view.add(relation, RDF_VIEW_NS.relationId, Literal(claim.relation_id))
    view.add(relation, RDF_VIEW_NS.logicalRelationId, Literal(claim.logical_relation_id))
    view.add(relation, RDF_VIEW_NS.relationType, Literal(claim.relation_type))
    view.add(relation, RDF_VIEW_NS.schemaVersion, Literal(claim.schema_version))
    view.add(relation, RDF_VIEW_NS.status, Literal(str(claim.status)))
    view.add(relation, RDF_VIEW_NS.evidenceGrade, Literal(str(claim.evidence_grade)))
    view.add(relation, RDF_VIEW_NS.tenantId, Literal(claim.tenant_id))
    view.add(
        relation,
        RDF_VIEW_NS.subject,
        _member_view(view, claim.subject_ref, assertions.get(claim.subject_ref, ())),
    )
    view.add(
        relation,
        RDF_VIEW_NS.object,
        _member_view(view, claim.object_ref, assertions.get(claim.object_ref, ())),
    )
    for name, moment in (
        ("observedAt", _moment(claim.observed_at)),
        ("validFrom", _moment(claim.valid_from)),
        ("validTo", _moment(claim.valid_to)),
    ):
        if moment:
            view.add(relation, RDF_VIEW_NS[name], Literal(moment, datatype=XSD.dateTime))
    for reference in claim.observation_refs:
        view.add(relation, RDF_VIEW_NS.observation, Literal(reference))
    for reference in claim.assertion_refs:
        view.add(relation, RDF_VIEW_NS.assertion, Literal(reference))
    for group in claim.source_independence_groups:
        for reference in group:
            view.add(relation, RDF_VIEW_NS.independenceGroup, Literal(reference))
    if claim.context_ref:
        frame = frames.get(claim.context_ref)
        view.add(relation, RDF_VIEW_NS.context, _project_context(view, frame))
    return relation


def _project_context(view: _BudgetedView, frame: EvidenceContext | None) -> URIRef:
    """Project the evidence frame, or an unresolvable placeholder when it is not held.

    A ``context_ref`` naming a frame this caller does not hold still projects - as a node marked
    ``view:resolved false``. Substituting nothing at all would make an unresolved reference look
    absent, and substituting a default frame would make it look licensed, and
    :class:`~domain.evidence_context.EvidenceContext` is explicit that neither is acceptable
    (FR-016).
    """
    if frame is None:
        node = _minted("context", "unresolved")
        view.bind(node, "context")
        view.add(node, RDF_VIEW_NS.resolved, Literal(False, datatype=XSD.boolean))
        return node
    node = _minted("context", frame.context_id)
    view.bind(node, "context")
    view.add(node, RDF_VIEW_NS.resolved, Literal(True, datatype=XSD.boolean))
    view.add(node, RDF_VIEW_NS.contextId, Literal(frame.context_id))
    view.add(node, RDF_VIEW_NS.ontologyVersion, Literal(frame.ontology_version))
    view.add(node, RDF_VIEW_NS.extractionVersion, Literal(frame.extraction_version))
    view.add(node, RDF_VIEW_NS.normalizationVersion, Literal(frame.normalization_version))
    view.add(node, RDF_VIEW_NS.completeness, Literal(str(frame.completeness)))
    view.add(node, RDF_VIEW_NS.trustState, Literal(str(frame.trust_state)))
    for name, value in (
        ("language", frame.language),
        ("locationContext", frame.location_context),
        ("policySnapshot", frame.policy_snapshot_ref),
    ):
        literal = _literal(value)
        if literal is not None:
            view.add(node, RDF_VIEW_NS[name], literal)
    for name, moment in (
        ("observedAt", _moment(frame.observed_at)),
        ("publishedAt", _moment(frame.published_at)),
        ("validFrom", _moment(frame.valid_from)),
        ("validTo", _moment(frame.valid_to)),
    ):
        if moment:
            view.add(node, RDF_VIEW_NS[name], Literal(moment, datatype=XSD.dateTime))
    return node


def _project_regime(view: _BudgetedView, regime: SemanticRegime) -> URIRef:
    """Project the semantic regime the claim was read under, including "no instruments" (FR-014).

    An uncommitted regime projects as a node with ``view:semanticCommitment "uncommitted"`` and
    **no** profile or mapping-set reference, so a shape that wants to see an interpretation
    regime can, and one that does not is unaffected. The view never fills the gap with a default
    profile (FR-001).
    """
    node = _minted("regime", regime.regime_id or regime.content_key())
    view.bind(node, "regime")
    view.add(node, RDF_VIEW_NS.semanticCommitment, Literal(str(regime.commitment)))
    view.add(node, RDF_VIEW_NS.validationProfile, Literal(regime.validation_profile))
    for name, value in (
        ("profile", regime.profile_version_ref),
        ("mappingSet", regime.mapping_set_version_ref),
        ("ontologyVersion", regime.ontology_version),
        ("operator", regime.operator_ref),
        ("language", regime.language),
        ("localization", regime.localization),
    ):
        literal = _literal(value)
        if literal is not None:
            view.add(node, RDF_VIEW_NS[name], literal)
    return node


def pyshacl_available() -> bool:
    """Whether pySHACL can be imported, probed without importing it.

    Uses :func:`importlib.util.find_spec` so a caller can ask the question - a health check, a
    capability banner, a test that skips - without paying for the import or, more importantly,
    without a missing dependency turning into an exception at the wrong moment. The real import
    still happens inside :func:`validate_with_shacl`; this is a probe, not a cache.
    """
    try:
        return importlib.util.find_spec("pyshacl") is not None
    except (ImportError, ValueError):
        return False


def validate_with_shacl(
    graph: Graph,
    shapes_graph: Graph | None = None,
    *,
    target_ref: str = "",
    tenant_id: str = "default-tenant",
    stage: ValidationStage = ValidationStage.GRAPH_LEVEL,
    profile_ref: str = "",
) -> ValidationReport:
    """Validate an RDF view against SHACL Core shapes and return graded findings (FR-010).

    The three ways this returns without having run, in order, and **none of them is ``VALID``**:

    1. pySHACL is not importable -> ``UNSUPPORTED``/``pyshacl_unavailable``. Checked first,
       because it is the honest headline about the environment; a caller who fixes the shapes
       still has to install the library.
    2. no shapes graph was supplied -> ``UNSUPPORTED``/``shacl_shapes_absent``. Validating
       against nothing conforms vacuously, and reporting that as a pass is the false ``VALID``
       this sidecar exists to avoid.
    3. the engine raised -> ``UNSUPPORTED``/``shacl_engine_error``. An opt-in instrument does not
       get to take the caller down, and a run that did not finish is unevaluable rather than
       passing (SC-9).

    A genuine run is reported as reported: conformant yields one ``VALID`` finding, and each
    ``sh:result`` becomes its own ``INVALID`` finding carrying the constraint component, the
    focus node, the result path and the engine's own message. Those findings attach to the
    report; they never remove the claim they describe, and nothing here writes to ``graph``
    (FR-012, SC-4).

    ``stage`` lets a caller attribute the findings to a stage other than the default
    :attr:`~semantic.contracts.ValidationStage.GRAPH_LEVEL` - SHACL shapes written as domain and
    range constraints read better as ``SEMANTIC``. The default is graph-level because the sidecar
    sees the whole projection and a shape may constrain anything in it.
    """
    try:
        from pyshacl import validate as pyshacl_validate
    except ImportError:
        return _report(
            Verdict.UNSUPPORTED,
            "pyshacl_unavailable",
            "pySHACL is not installed; SHACL Core validation is an optional sidecar and its "
            "absence is reported as unsupported rather than passed (D4, FR-010)",
            target_ref=target_ref,
            tenant_id=tenant_id,
            stage=stage,
            profile_ref=profile_ref,
        )

    if shapes_graph is None:
        return _report(
            Verdict.UNSUPPORTED,
            "shacl_shapes_absent",
            "no shapes graph was supplied; validating against no shapes conforms vacuously, and "
            "a vacuous pass must never be reported as VALID (SC-9)",
            target_ref=target_ref,
            tenant_id=tenant_id,
            stage=stage,
            profile_ref=profile_ref,
        )

    try:
        conforms, results_graph, _results_text = pyshacl_validate(
            data_graph=graph,
            shacl_graph=shapes_graph,
            inference="none",
            advanced=False,
            abort_on_first=False,
            allow_infos=False,
            allow_warnings=False,
            meta_shacl=False,
            debug=False,
        )
        if conforms:
            return _report(
                Verdict.VALID,
                "shacl_conforms",
                "pySHACL reports the projected view conforms to the supplied shapes",
                target_ref=target_ref,
                tenant_id=tenant_id,
                stage=stage,
                profile_ref=profile_ref,
            )
        return _report(
            Verdict.INVALID,
            "shacl_violation",
            "pySHACL reports violations against the supplied shapes",
            target_ref=target_ref,
            tenant_id=tenant_id,
            stage=stage,
            profile_ref=profile_ref,
            findings=_read_results(results_graph, target_ref, tenant_id, stage, profile_ref),
        )
    except Exception as error:
        return _report(
            Verdict.UNSUPPORTED,
            "shacl_engine_error",
            f"pySHACL did not complete ({type(error).__name__}: {error}); an unfinished run is "
            "unevaluable, never passing (SC-9)",
            target_ref=target_ref,
            tenant_id=tenant_id,
            stage=stage,
            profile_ref=profile_ref,
        )


def _read_results(
    results_graph: Graph,
    target_ref: str,
    tenant_id: str,
    stage: ValidationStage,
    profile_ref: str,
) -> tuple[ValidationFinding, ...]:
    """One graded finding per ``sh:result``, carrying the engine's own detail.

    Read defensively: a result node missing its component or its focus still yields a finding
    rather than raising, because losing one violation to a parse error would be a quieter and
    worse failure than reporting the violation thinly.
    """
    findings: list[ValidationFinding] = []
    for result in sorted(results_graph.subjects(RDF.type, SH.result), key=str):
        component = _first_text(results_graph, result, SH.sourceConstraintComponent)
        focus = _first_ref(results_graph, result, SH.focusNode)
        path = _first_ref(results_graph, result, SH.resultPath)
        message = _first_text(results_graph, result, SH.resultMessage)
        code = component.rsplit("#", 1)[-1].rsplit(":", 1)[-1] if component else "shacl_result"
        detail = message or f"{code} at {focus}"
        findings.append(
            ValidationFinding(
                tenant_id=tenant_id,
                assertion_ref=target_ref or (str(focus) if focus else ""),
                stage=stage,
                verdict=Verdict.INVALID,
                code=code,
                message=detail,
                constraint_ref=component or (str(path) if path else ""),
                profile_ref=profile_ref,
            ).with_id()
        )
    return tuple(findings)


def _first_text(graph: Graph, subject: URIRef, predicate: URIRef) -> str:
    for value in graph.objects(subject, predicate):
        return str(value)
    return ""


def _first_ref(graph: Graph, subject: URIRef, predicate: URIRef) -> str:
    for value in graph.objects(subject, predicate):
        return str(value)
    return ""


def _report(
    verdict: Verdict,
    code: str,
    message: str,
    *,
    target_ref: str,
    tenant_id: str,
    stage: ValidationStage,
    profile_ref: str,
    findings: Sequence[ValidationFinding] = (),
) -> ValidationReport:
    """A one-finding report, or a report that carries the engine's findings.

    The single-finding shape is what makes "the sidecar did not run" queryable: an
    ``UNSUPPORTED`` finding is present, has a code and has a stage, so it appears in
    :meth:`~semantic.contracts.ValidationReport.at_stage` and keeps
    :meth:`~semantic.contracts.ValidationReport.unevaluated_stages` honest about the fact that
    something was attempted and could not be.
    """
    supplied = tuple(findings)
    if supplied:
        report_findings = supplied
    else:
        report_findings = (
            ValidationFinding(
                tenant_id=tenant_id,
                assertion_ref=target_ref,
                stage=stage,
                verdict=verdict,
                code=code,
                message=message,
                profile_ref=profile_ref,
            ).with_id(),
        )
    return ValidationReport(
        tenant_id=tenant_id,
        target_ref=target_ref,
        profile_ref=profile_ref,
        findings=report_findings,
    ).with_id()


@dataclass(frozen=True)
class ShaclSidecar:
    """The opt-in entry point: build a bounded view, validate it, and never touch the graph.

    ``enabled`` defaults to ``False`` and a disabled sidecar reports
    ``UNSUPPORTED``/``sidecar_disabled`` **without building anything**. That is the structural
    form of D4 and constitution VIII: putting this on a write path is not the default state, it
    requires a flag somebody set deliberately, and the disabled path does no work that could slow
    an ingestion down. Nothing in the write path constructs an enabled sidecar, and no
    constructor here has an argument that could make validation happen implicitly.

    :meth:`validate` is the one place a :class:`RdfViewTooLarge` is allowed to become a graded
    report instead of a raise. That boundary is where "an optional instrument did not run" is a
    normal answer worth recording; :func:`build_rdf_view` itself still raises, so a caller who
    wants the refusal loud can have it loud.
    """
    shapes_graph: Graph | None = None
    budget: RdfViewBudget = RdfViewBudget()
    enabled: bool = False
    tenant_id: str = "default-tenant"
    target_ref: str = ""
    stage: ValidationStage = ValidationStage.GRAPH_LEVEL
    profile_ref: str = ""

    @property
    def available(self) -> bool:
        """Whether a call would actually run an engine: enabled, and pySHACL importable.

        A capability query, not a gate. It exists so a caller can label a report as "SHACL was not
        available" before asking, and so a health check does not have to raise.
        """
        return self.enabled and pyshacl_available()

    def view(
        self,
        claims: Iterable[RelationClaim],
        relations: Mapping[str, RelationOperator] | Iterable[RelationOperator] = (),
        **kwargs: object,
    ) -> Graph:
        """The projection this sidecar would validate, with its own budget applied.

        Exposed so a caller can inspect, hash or ship the view somewhere without running an
        engine over it. Raises :class:`RdfViewTooLarge` like :func:`build_rdf_view` does.
        """
        return build_rdf_view(claims, relations, budget=self.budget, **kwargs)  # type: ignore[arg-type]

    def run(
        self,
        claims: Iterable[RelationClaim],
        relations: Mapping[str, RelationOperator] | Iterable[RelationOperator] = (),
        **kwargs: object,
    ) -> ValidationReport:
        """Build the view and validate it, degrading an oversized view to ``UNSUPPORTED``.

        The budget refusal is caught here and nowhere else, and it is caught rather than
        propagated because a sidecar reporting "I could not check this" is a usable answer while a
        sidecar raising into a caller is how optional instruments end up mandatory (D4).
        """
        if not self.enabled:
            return _report(
                Verdict.UNSUPPORTED,
                "sidecar_disabled",
                "the SHACL sidecar is opt-in and this instance is disabled; it is off the write "
                "path by construction (D4, constitution VIII)",
                target_ref=self.target_ref,
                tenant_id=self.tenant_id,
                stage=self.stage,
                profile_ref=self.profile_ref,
            )
        try:
            graph = self.view(claims, relations, **kwargs)
        except RdfViewTooLarge as refusal:
            return _report(
                Verdict.UNSUPPORTED,
                "view_budget_exceeded",
                str(refusal),
                target_ref=self.target_ref,
                tenant_id=self.tenant_id,
                stage=self.stage,
                profile_ref=self.profile_ref,
            )
        return validate_with_shacl(
            graph,
            self.shapes_graph,
            target_ref=self.target_ref,
            tenant_id=self.tenant_id,
            stage=self.stage,
            profile_ref=self.profile_ref,
        )

    def validate(self, graph: Graph) -> ValidationReport:
        """Validate an already-built view. The disabled check applies here too."""
        if not self.enabled:
            return _report(
                Verdict.UNSUPPORTED,
                "sidecar_disabled",
                "the SHACL sidecar is opt-in and this instance is disabled; it is off the write "
                "path by construction (D4, constitution VIII)",
                target_ref=self.target_ref,
                tenant_id=self.tenant_id,
                stage=self.stage,
                profile_ref=self.profile_ref,
            )
        return validate_with_shacl(
            graph,
            self.shapes_graph,
            target_ref=self.target_ref,
            tenant_id=self.tenant_id,
            stage=self.stage,
            profile_ref=self.profile_ref,
        )
