"""Semantic operators: relation operators bound to the existing RelationSchema.

Feature 017, FR-006. This module does **not** declare a second schema for
relations. It binds an executable *operator* to the existing
:class:`domain.relation_schema.RelationSchema` (feature 016) and attaches policy
and strategy that make the schema enforceable in the pipeline: evidence
requirements, extraction strategies, admission policy, validation policy and
projection policy. The world is closed for operations but open for content: an
operator's contract is fixed, but an unknown relation type can still be admitted
and represented as an operator definition if necessary (FR-013).

Default domain-range policy is ``warn`` (D1) because a rejection would mean
validation produces deletion instead of findings, which would violate FR-012.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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


class ExtractionStrategy(StrEnum):
    """How a candidate relation is extracted from mentions/surface."""

    DEPENDENCY_PATTERN = "dependency_pattern"
    LEXICAL_PATTERN = "lexical_pattern"
    PROFILE_CONTEXT = "profile_context"
    DISTANT_SUPERVISION = "distant_supervision"
    RULE = "rule"
    WEAK_SUPERVISION = "weak_supervision"


class DomainRangePolicy(StrEnum):
    """What to do when a role's type is not within hints.

    ``WARN`` means the assertion is still materialised and a finding is raised;
    ``DENY`` would prevent materialisation, which violates FR-012.
    """

    WARN = "warn"
    DENY = "deny"
    IGNORE = "ignore"


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
    applies the global defaults (``domain_range_policy = WARN``), so new relation
    types that appear with no profile or ontology still get a usable, closed
    operator contract (FR-013).
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
