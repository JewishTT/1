"""Semantic operators: relation operators bound to the existing RelationSchema.

Feature 017, FR-006. This module does **not** declare a second schema for
relations. It binds an executable *operator* to the existing
:class:`domain.relation_schema.RelationSchema` (feature 016) and attaches policy
and strategy that make the schema enforceable in the pipeline: evidence
requirements, extraction strategies, admission policy, validation policy and
projection policy. The world is closed for operations but open for content: an
operator's contract is fixed, but an unknown relation type can still be admitted
and represented as an operator definition if necessary (FR-013).

Default domain-range policy is ``warn`` (D1), which admits the claim and raises
a finding. No policy here deletes, filters or deprojects a claim, and no policy
here asserts anything about whether a relation exists: every member of
:class:`DomainRangePolicy` is a statement about **this operator's own
materialised view** and about nothing else (FR-012).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.relation_candidate import ExtractionStrategy
from domain.relation_schema import RelationArityMode, RelationSchema, TemporalSemantics

__all__ = [
    "AdmissionPolicy",
    "DomainRangePolicy",
    "ExtractionStrategy",
    "ProjectionPolicy",
    "RelationOperator",
    "ValidationPolicy",
    "default_operator_for_schema",
]


class DomainRangePolicy(StrEnum):
    """What this operator does when a role's type falls outside its declared hints.

    Every member is a statement about **one operator's own materialised view**. None of them is a
    statement about whether the relation exists, whether the claim is true, or whether anything
    should be deleted. The names are chosen so that reading one in isolation cannot be mistaken for
    a global veto:

    * ``WARN`` - the default (D1). A finding is raised and the claim is admitted into this
      operator's view. Nothing is withheld and nothing is removed (FR-012, SC-8).
    * ``EXCLUDE_FROM_VIEW`` - this operator declines to admit the claim into **its own**
      materialised view. The claim, its evidence and the findings that motivated the decision are
      untouched, still queryable and still resolvable (FR-012, SC-4), and another operator with a
      different policy may admit the very same claim into its own view.
    * ``IGNORE`` - the check is not run. Nothing is judged, so nothing can be withheld.

    The legacy input spelling ``"deny"`` is accepted by :meth:`_missing_` and canonicalised to
    ``EXCLUDE_FROM_VIEW`` on construction, so existing stored configuration keeps loading. It is
    deliberately **not** a member: a member named ``DENY`` reads as a global refusal, which is the
    exact misreading this enum exists to rule out. Ask :attr:`excludes_from_view` rather than
    comparing members, so a future member cannot silently acquire veto semantics.
    """

    WARN = "warn"
    EXCLUDE_FROM_VIEW = "exclude_from_view"
    IGNORE = "ignore"

    @classmethod
    def _missing_(cls, value: object) -> DomainRangePolicy | None:
        """Resolve the retired ``"deny"`` spelling to the scoped member, refusing everything else.

        Returns ``None`` for an unrecognised value so ``DomainRangePolicy`` still raises
        ``ValueError``: an unrecognised policy must not become a silent admission or a silent veto.
        """
        if isinstance(value, str) and value.strip().casefold().replace("-", "_") == "deny":
            return cls.EXCLUDE_FROM_VIEW
        return None

    @property
    def excludes_from_view(self) -> bool:
        """Whether this policy withholds a claim from *this operator's* view. Never a deletion.

        The only supported way to ask the question. Comparing against
        ``EXCLUDE_FROM_VIEW`` at a call site is how a second, future member ends up being treated
        as a veto it was never scoped to be.
        """
        return self is DomainRangePolicy.EXCLUDE_FROM_VIEW


class AdmissionPolicy(StrEnum):
    """When an operator admits a claim."""

    STRICT = "strict"
    LENIENT = "lenient"
    EVIDENCE_ONLY = "evidence_only"


class ValidationPolicy(StrEnum):
    """How aggressively to validate a claim produced by this operator."""

    NORMAL = "normal"
    CONSERVATIVE = "conservative"
    PERMISSIVE = "permissive"


class ProjectionPolicy(StrEnum):
    """Whether projections should include claims that produced warnings."""

    INCLUDE_WARNINGS = "include_warnings"
    EXCLUDE_WARNINGS = "exclude_warnings"


@dataclass(frozen=True)
class RelationOperator:
    """Executable relation operator bound to an existing :class:`RelationSchema`.

    No fields duplicate the schema's core shape unnecessarily: this object only
    adds the *behaviour* (how to extract, admit, validate, project). The schema
    remains the single declaration of semantics (FR-006).

    ``ExtractionStrategy`` is deliberately defined in :mod:`domain.relation_candidate`
    and imported here rather than declared locally. Which strategies an operator
    admits is a question about extraction, and the extraction layer has to be able
    to record the strategy it used without importing this module -- importing
    ``semantic`` from ``domain`` would invert the dependency and drag the whole
    semantic layer into the foundation.

    **``domain_range_policy`` is scoped to this operator's own materialised view.**
    It decides whether *this* operator's projection of *this* relation type carries a
    claim, and it is the only field here that can withhold one. It is not a global veto, it
    is not a judgement that the relation does not exist, and it is never a deletion: a claim
    excluded by ``EXCLUDE_FROM_VIEW`` keeps its object, its evidence and its findings, stays
    queryable and resolvable (FR-012, SC-4), and a second operator holding the same claim
    under a different policy reaches a different - equally correct - decision about its own
    view. The default is :attr:`DomainRangePolicy.WARN`, which admits and records a finding,
    so a default-constructed operator cannot withhold anything (D1). The admission decision
    itself is a :class:`semantic.validation.MaterialisationDecision`, which states that scope
    explicitly rather than returning a bare boolean.
    """

    relation_type: str
    schema_version: str = "1"

    arity_mode: RelationArityMode = RelationArityMode.DIRECTED
    directed: bool = True
    symmetric: bool = False
    temporal: TemporalSemantics = TemporalSemantics.OPTIONAL_INTERVAL

    inverse_relation_type: str = ""
    transitivity: str = ""
    extraction_rule_ids: tuple[str, ...] = ()

    roles: tuple[str, ...] = ()
    subject_kinds: tuple[str, ...] = ()
    object_kinds: tuple[str, ...] = ()

    evidence_requirements: tuple[str, ...] = ("mention_pair", "relation_pattern")
    extraction_strategies: tuple[ExtractionStrategy, ...] = (
        ExtractionStrategy.LEXICAL_PATTERN,
        ExtractionStrategy.PROFILE_CONTEXT,
    )

    domain_range_policy: DomainRangePolicy = DomainRangePolicy.WARN
    admission_policy: AdmissionPolicy = AdmissionPolicy.EVIDENCE_ONLY
    validation_policy: ValidationPolicy = ValidationPolicy.NORMAL
    projection_policy: ProjectionPolicy = ProjectionPolicy.INCLUDE_WARNINGS

    def __post_init__(self) -> None:
        object.__setattr__(self, "arity_mode", RelationArityMode(self.arity_mode))
        object.__setattr__(self, "temporal", TemporalSemantics(self.temporal))
        object.__setattr__(self, "domain_range_policy", DomainRangePolicy(self.domain_range_policy))
        object.__setattr__(self, "admission_policy", AdmissionPolicy(self.admission_policy))
        object.__setattr__(self, "validation_policy", ValidationPolicy(self.validation_policy))
        object.__setattr__(self, "projection_policy", ProjectionPolicy(self.projection_policy))
        object.__setattr__(
            self,
            "extraction_strategies",
            tuple(sorted(set(ExtractionStrategy(s) for s in self.extraction_strategies))),
        )
        object.__setattr__(
            self,
            "evidence_requirements",
            tuple(sorted(set(str(r) for r in self.evidence_requirements))),
        )
        object.__setattr__(
            self,
            "extraction_rule_ids",
            tuple(sorted({str(r) for r in self.extraction_rule_ids})),
        )
        object.__setattr__(
            self,
            "roles",
            tuple(str(r) for r in sorted({str(r) for r in self.roles}, key=str)),
        )
        object.__setattr__(
            self,
            "subject_kinds",
            tuple(sorted({str(k) for k in self.subject_kinds})),
        )
        object.__setattr__(
            self,
            "object_kinds",
            tuple(sorted({str(k) for k in self.object_kinds})),
        )

    @property
    def key(self) -> tuple[str, str]:
        return (self.relation_type, self.schema_version)


def default_operator_for_schema(schema: RelationSchema) -> RelationOperator:
    """Derive a conservative, production-safe operator from an existing schema.

    This is not opinionated about content: it mirrors the schema's shape and
    applies the global defaults (``domain_range_policy = WARN``, which admits
    and records a finding rather than withholding), so new relation types that
    appear with no profile or ontology still get a usable, closed operator
    contract that cannot exclude anything (FR-013, D1).
    """
    return RelationOperator(
        relation_type=schema.relation_type,
        schema_version=schema.schema_version,
        arity_mode=schema.arity_mode,
        directed=schema.arity_mode is RelationArityMode.DIRECTED,
        # 016 does not model symmetry as a field, so it is derived from arity: an
        # undirected relation has no direction to violate, a directed one does.
        symmetric=schema.arity_mode is RelationArityMode.UNDIRECTED,
        temporal=schema.temporal_semantics,
        inverse_relation_type="",
        transitivity="",
        extraction_rule_ids=tuple(schema.admissible_evidence_patterns),
        roles=tuple(schema.allowed_role_classes),
        subject_kinds=tuple(schema.sorted_subject_classes),
        object_kinds=tuple(schema.sorted_object_classes),
        evidence_requirements=tuple(schema.admissible_evidence_patterns)
        or ("mention_pair", "relation_pattern"),
        extraction_strategies=(
            ExtractionStrategy.DEPENDENCY_PATTERN,
            ExtractionStrategy.LEXICAL_PATTERN,
        ),
        domain_range_policy=DomainRangePolicy.WARN,
    )
