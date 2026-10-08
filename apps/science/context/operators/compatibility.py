"""Compatibility assessment across the eight declared dimensions (spec 025 §9).

ADR-0031 states the reason this module exists: "pairwise compatibility of sections
is not local-global compatibility on overlaps; the cocycle condition on triple
overlaps is a separate requirement." So compatibility is computed per dimension,
per §9.2 semantics, and never collapsed into a single boolean.

The four-valued per-dimension verdict is what keeps §0.2 intact at this layer:

    SUPPORTED | CONTRADICTED | UNKNOWN | NOT_APPLICABLE

``UNKNOWN`` is the load-bearing one. A semantic mapping that was never attempted
is not a mapping that failed, and a structural comparison that was skipped for
budget is not a structural match. An assessment that reported ``NOT_APPLICABLE``
for everything undetermined would declare unrelated cells compatible -- which is
how a merged candidate section ends up asserting a structure nobody checked.

The aggregation to an overall verdict is deliberately *not* a weighted score.
Spec §14.1's prohibition on collapsing distinct quantities applies here: a
numeric compatibility verdict and a provenance verdict are not commensurable, so
the roll-up is by precedence over blocking dimensions only.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from context.locality import ContextCell, ObstructionKind, _digest


class DimensionVerdict(enum.StrEnum):
    """§9.2 per-dimension verdicts."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class CompatibilityVerdict(enum.StrEnum):
    """§9.1 overall verdict."""

    COMPATIBLE = "compatible"
    PARTIAL = "partial"
    INCOMPATIBLE = "incompatible"
    UNRESOLVED = "unresolved"


class Dimension(enum.StrEnum):
    """The eight dimensions of §9.1, in declaration order."""

    IDENTITY = "identity"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    NUMERIC = "numeric"
    PROVENANCE = "provenance"
    CAUSAL = "causal"


#: Precedence used for roll-up. A single CONTRADICTED dimension outranks any
#: number of UNKNOWN ones, because "we found a conflict" and "we did not look"
#: are not the same statement and only one of them justifies a refusal.
_SEVERITY: dict[DimensionVerdict, int] = {
    DimensionVerdict.CONTRADICTED: 3,
    DimensionVerdict.UNKNOWN: 2,
    DimensionVerdict.NOT_APPLICABLE: 1,
    DimensionVerdict.SUPPORTED: 0,
}

DIMENSIONS: tuple[Dimension, ...] = tuple(Dimension)


@dataclass(frozen=True, slots=True)
class DimensionResult:
    """One dimension's verdict, with the evidence that produced it."""

    dimension: Dimension
    verdict: DimensionVerdict
    detail: str = ""
    evidence_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "verdict": self.verdict.value,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class CompatibilityAssessment:
    """§9.1, transcribed. One assessment per cell overlap."""

    overlap_id: str
    dimensions: Mapping[Dimension, DimensionResult]
    method_fingerprint: str = ""
    assessment_id: str = ""
    operator: str = "compatibility.operator.v1"

    def __post_init__(self) -> None:
        if not self.assessment_id:
            object.__setattr__(self, "assessment_id", f"CMP-{_digest(self._material())}")

    def _material(self) -> dict[str, Any]:
        return {
            "overlap_id": self.overlap_id,
            "dimensions": {
                dimension.value: result.verdict.value
                for dimension, result in sorted(self.dimensions.items(), key=lambda item: item[0].value)
            },
        }

    def verdict_of(self, dimension: Dimension) -> DimensionVerdict:
        result = self.dimensions.get(dimension)
        return result.verdict if result is not None else DimensionVerdict.UNKNOWN

    @property
    def blocking_dimensions(self) -> tuple[Dimension, ...]:
        """Dimensions that refute compatibility. Not merely unverified ones."""
        return tuple(
            sorted(
                (
                    dimension
                    for dimension, result in self.dimensions.items()
                    if result.verdict is DimensionVerdict.CONTRADICTED
                ),
                key=lambda item: item.value,
            )
        )

    @property
    def missing_evidence(self) -> tuple[Dimension, ...]:
        """Dimensions nobody determined. Distinct from refuted ones."""
        return tuple(
            sorted(
                (
                    dimension
                    for dimension, result in self.dimensions.items()
                    if result.verdict is DimensionVerdict.UNKNOWN
                ),
                key=lambda item: item.value,
            )
        )

    @property
    def unapplicable_dimensions(self) -> tuple[Dimension, ...]:
        return tuple(
            sorted(
                (
                    dimension
                    for dimension, result in self.dimensions.items()
                    if result.verdict is DimensionVerdict.NOT_APPLICABLE
                ),
                key=lambda item: item.value,
            )
        )

    @property
    def verdict(self) -> CompatibilityVerdict:
        """Roll up by precedence. No weighted score: §14.1 forbids it."""
        if not self.dimensions:
            return CompatibilityVerdict.UNRESOLVED
        if any(
            result.verdict is DimensionVerdict.CONTRADICTED
            for result in self.dimensions.values()
        ):
            return CompatibilityVerdict.INCOMPATIBLE
        if any(
            result.verdict is DimensionVerdict.UNKNOWN for result in self.dimensions.values()
        ):
            return CompatibilityVerdict.UNRESOLVED
        if any(
            result.verdict is DimensionVerdict.NOT_APPLICABLE
            for result in self.dimensions.values()
        ):
            return CompatibilityVerdict.PARTIAL
        return CompatibilityVerdict.COMPATIBLE

    @property
    def is_pairwise_compatible(self) -> bool:
        """True only when nothing was refuted and nothing was left undetermined."""
        return self.verdict in (
            CompatibilityVerdict.COMPATIBLE,
            CompatibilityVerdict.PARTIAL,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "overlap_id": self.overlap_id,
            "operator": self.operator,
            "method_fingerprint": self.method_fingerprint,
            "verdict": self.verdict.value,
            "dimensions": {
                dimension.value: result.as_dict()
                for dimension, result in sorted(
                    self.dimensions.items(), key=lambda item: item[0].value
                )
            },
            "blocking_dimensions": [item.value for item in self.blocking_dimensions],
            "missing_evidence": [item.value for item in self.missing_evidence],
        }


# -- per-dimension evaluators -------------------------------------------------


def assess_identity(left: ContextCell, right: ContextCell) -> DimensionResult:
    """§9.2: use durable resolution outputs where available.

    Undetermined identity is ``UNKNOWN``, never ``INCOMPATIBLE``: two mentions may
    resolve to one entity later, and declaring them different entities at this
    point would fork a subject that should be merged.
    """
    shared = set(left.entity_refs) & set(right.entity_refs)
    if shared:
        return DimensionResult(
            Dimension.IDENTITY,
            DimensionVerdict.SUPPORTED,
            detail=f"shared entity refs: {sorted(shared)}",
            evidence_refs=tuple(sorted(shared)),
        )
    if not left.entity_refs or not right.entity_refs:
        return DimensionResult(
            Dimension.IDENTITY,
            DimensionVerdict.UNKNOWN,
            detail="one side carries no entity refs, so identity cannot be compared",
        )
    return DimensionResult(
        Dimension.IDENTITY,
        DimensionVerdict.UNKNOWN,
        detail="no shared entity refs and no resolution output to decide",
    )


def assess_temporal(left: ContextCell, right: ContextCell) -> DimensionResult:
    """§9.2: evaluate explicit time relations from the interval algebra."""
    left_slice = left.temporal_slice
    right_slice = right.temporal_slice
    if not left_slice or not right_slice:
        return DimensionResult(
            Dimension.TEMPORAL,
            DimensionVerdict.UNKNOWN,
            detail="a temporal slice is missing on one side",
        )
    if left_slice == right_slice:
        return DimensionResult(
            Dimension.TEMPORAL, DimensionVerdict.SUPPORTED, detail="identical slices"
        )
    latest_left = max(left_slice)
    earliest_right = min(right_slice)
    if latest_left < earliest_right:
        return DimensionResult(
            Dimension.TEMPORAL,
            DimensionVerdict.SUPPORTED,
            detail="slices are disjoint in time and therefore comparable",
        )
    return DimensionResult(
        Dimension.TEMPORAL,
        DimensionVerdict.SUPPORTED,
        detail="slices overlap",
    )


def assess_semantic(left: ContextCell, right: ContextCell) -> DimensionResult:
    """§9.2: evaluate mappings under an explicit semantic regime, preserving UNKNOWN."""
    if not left.semantic_regime_ref or not right.semantic_regime_ref:
        return DimensionResult(
            Dimension.SEMANTIC,
            DimensionVerdict.UNKNOWN,
            detail="no semantic regime declared on one side",
        )
    if left.semantic_regime_ref == right.semantic_regime_ref:
        return DimensionResult(
            Dimension.SEMANTIC,
            DimensionVerdict.SUPPORTED,
            detail=f"same regime {left.semantic_regime_ref}",
        )
    return DimensionResult(
        Dimension.SEMANTIC,
        DimensionVerdict.UNKNOWN,
        detail=(
            f"regimes differ ({left.semantic_regime_ref} vs "
            f"{right.semantic_regime_ref}); no cross-regime mapping established"
        ),
    )


def assess_structural(left: ContextCell, right: ContextCell) -> DimensionResult:
    """§9.2: compare graph/hypergraph patterns under declared tolerance.

    This is one of two dimensions that can *refute*. A cell may declare explicit
    relation assertions via ``completeness["relation_assertions"]`` as
    ``(subject, predicate, object)`` triples; if two cells assert different
    objects for the same subject/predicate, the structure is contradicted rather
    than merely undetermined. Without that path the four-valued verdict had no way
    to ever produce ``CONTRADICTED``, and ``INCOMPATIBLE`` would be unreachable.
    """
    if not left.relation_refs or not right.relation_refs:
        return DimensionResult(
            Dimension.STRUCTURAL,
            DimensionVerdict.NOT_APPLICABLE,
            detail="no relations declared, so no pattern to compare",
        )

    # Contradiction first. A shared relation ref is weak evidence, and letting it
    # short-circuit would let two cells that assert incompatible objects for the
    # same subject/predicate report as structurally supported.
    left_claims = _claim_index(left, "relation_assertions")
    right_claims = _claim_index(right, "relation_assertions")
    contradiction = _first_contradiction(left_claims, right_claims)
    if contradiction is not None:
        subject, predicate, left_object, right_object = contradiction
        return DimensionResult(
            Dimension.STRUCTURAL,
            DimensionVerdict.CONTRADICTED,
            detail=(
                f"({subject},{predicate}) asserted with object {left_object!r} "
                f"on one side and {right_object!r} on the other"
            ),
            evidence_refs=(str(subject), str(predicate)),
        )

    shared = set(left.relation_refs) & set(right.relation_refs)
    if shared:
        return DimensionResult(
            Dimension.STRUCTURAL,
            DimensionVerdict.SUPPORTED,
            detail=f"shared relations: {sorted(shared)}",
            evidence_refs=tuple(sorted(shared)),
        )
    return DimensionResult(
        Dimension.STRUCTURAL,
        DimensionVerdict.UNKNOWN,
        detail="disjoint relation sets and no declared assertion to refute with",
    )


def _claim_index(cell: ContextCell, key: str) -> dict[tuple[str, str], set[str]]:
    """Index ``(subject, predicate) -> {object}`` from a declared claim bag."""
    index: dict[tuple[str, str], set[str]] = {}
    raw = cell.completeness.get(key) or ()
    for item in raw:
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            continue
        subject, predicate, obj = (str(part) for part in item)
        index.setdefault((subject, predicate), set()).add(obj)
    return index


def _first_contradiction(
    left: dict[tuple[str, str], set[str]],
    right: dict[tuple[str, str], set[str]],
) -> tuple[str, str, str, str] | None:
    """The first stable-order key where the two claim bags disagree."""
    for subject, predicate in sorted(set(left) & set(right)):
        left_objects = left[(subject, predicate)]
        right_objects = right[(subject, predicate)]
        if left_objects != right_objects and (left_objects - right_objects):
            return (
                subject,
                predicate,
                min(left_objects - right_objects),
                min(right_objects),
            )
    return None


def assess_numeric(left: ContextCell, right: ContextCell) -> DimensionResult:
    """§9.2: declared units, precision, intervals and tolerance.

    The second dimension that can refute. Cells may declare
    ``completeness["numeric_values"]`` as ``{measure: value}`` plus an optional
    ``completeness["numeric_tolerance"]``; a disagreement larger than the
    declared tolerance is a contradiction, not an unknown.
    """
    left_values = left.completeness.get("numeric_values")
    right_values = right.completeness.get("numeric_values")
    if not isinstance(left_values, Mapping) or not isinstance(right_values, Mapping):
        return DimensionResult(
            Dimension.NUMERIC,
            DimensionVerdict.UNKNOWN,
            detail="no declared numeric values on one side",
        )
    if not left_values or not right_values:
        return DimensionResult(
            Dimension.NUMERIC,
            DimensionVerdict.UNKNOWN,
            detail="one side declared an empty numeric bag",
        )
    tolerance = float(
        left.completeness.get("numeric_tolerance")
        or right.completeness.get("numeric_tolerance")
        or 0.0
    )
    shared_measures = set(left_values) & set(right_values)
    if not shared_measures:
        return DimensionResult(
            Dimension.NUMERIC,
            DimensionVerdict.UNKNOWN,
            detail="no shared measure to compare",
        )
    for measure in sorted(shared_measures):
        try:
            delta = abs(float(left_values[measure]) - float(right_values[measure]))
        except (TypeError, ValueError):
            continue
        if delta > tolerance:
            return DimensionResult(
                Dimension.NUMERIC,
                DimensionVerdict.CONTRADICTED,
                detail=(
                    f"measure {measure} differs by {delta} beyond tolerance {tolerance}"
                ),
                evidence_refs=(str(measure),),
            )
    return DimensionResult(
        Dimension.NUMERIC,
        DimensionVerdict.SUPPORTED,
        detail=f"{len(shared_measures)} shared measure(s) agree within tolerance {tolerance}",
        evidence_refs=tuple(sorted(str(measure) for measure in shared_measures)),
    )


def assess_provenance(left: ContextCell, right: ContextCell) -> DimensionResult:
    """§9.2 and Constitution II: both sides must be traceable to a source lineage."""
    if not left.method_fingerprint or not right.method_fingerprint:
        return DimensionResult(
            Dimension.PROVENANCE,
            DimensionVerdict.UNKNOWN,
            detail="a cell carries no method fingerprint, so its lineage is unproven",
        )
    if not left.produced_by or not right.produced_by:
        return DimensionResult(
            Dimension.PROVENANCE,
            DimensionVerdict.UNKNOWN,
            detail="a cell names no producing operator",
        )
    return DimensionResult(
        Dimension.PROVENANCE,
        DimensionVerdict.SUPPORTED,
        detail="both cells declare a producer and a method fingerprint",
    )


def assess_spatial(left: ContextCell, right: ContextCell) -> DimensionResult:
    """§9.2 / §8.3: geospatial tile, when applicable."""
    left_tile = left.scope.qualifier if left.scope.kind.value == "geospatial" else ""
    right_tile = right.scope.qualifier if right.scope.kind.value == "geospatial" else ""
    if not left_tile or not right_tile:
        return DimensionResult(
            Dimension.SPATIAL,
            DimensionVerdict.NOT_APPLICABLE,
            detail="no geospatial tile declared on one side",
        )
    if left_tile == right_tile:
        return DimensionResult(
            Dimension.SPATIAL, DimensionVerdict.SUPPORTED, detail=f"same tile {left_tile}"
        )
    return DimensionResult(
        Dimension.SPATIAL,
        DimensionVerdict.UNKNOWN,
        detail=f"different tiles {left_tile} vs {right_tile}; no adjacency relation",
    )


def assess_causal(left: ContextCell, right: ContextCell) -> DimensionResult:
    """§27 separation: identification, estimation and refutation stay separate."""
    left_stages = set(left.completeness.get("causal_stages") or ())
    right_stages = set(right.completeness.get("causal_stages") or ())
    if not left_stages or not right_stages:
        return DimensionResult(
            Dimension.CAUSAL,
            DimensionVerdict.NOT_APPLICABLE,
            detail="no causal stages declared, so no causal claim is being compared",
        )
    if "identify" not in left_stages or "identify" not in right_stages:
        return DimensionResult(
            Dimension.CAUSAL,
            DimensionVerdict.UNKNOWN,
            detail="identification stage missing on one side",
        )
    if left_stages == right_stages:
        return DimensionResult(
            Dimension.CAUSAL,
            DimensionVerdict.SUPPORTED,
            detail=f"same declared stages: {sorted(left_stages)}",
        )
    return DimensionResult(
        Dimension.CAUSAL,
        DimensionVerdict.UNKNOWN,
        detail=f"stage sets differ: {sorted(left_stages)} vs {sorted(right_stages)}",
    )


#: §9.1 declares the dimensions in a fixed order; the assessment fills all of them.
ASSESSORS = {
    Dimension.IDENTITY: assess_identity,
    Dimension.TEMPORAL: assess_temporal,
    Dimension.SPATIAL: assess_spatial,
    Dimension.SEMANTIC: assess_semantic,
    Dimension.STRUCTURAL: assess_structural,
    Dimension.NUMERIC: assess_numeric,
    Dimension.PROVENANCE: assess_provenance,
    Dimension.CAUSAL: assess_causal,
}


def assess_pair(
    left: ContextCell,
    right: ContextCell,
    *,
    overlap_id: str,
    method_fingerprint: str = "",
    overrides: Mapping[Dimension, DimensionResult] | None = None,
) -> CompatibilityAssessment:
    """Assess one cell pair across all eight dimensions.

    ``overrides`` exists so a caller can inject a dimension result that cannot be
    derived from the cell headers alone -- a numeric comparison performed against
    real measurements, for instance. It is additive: unspecified dimensions are
    still assessed, and an unspecified dimension is never silently defaulted to
    SUPPORTED.
    """
    dimensions: dict[Dimension, DimensionResult] = {
        dimension: ASSESSORS[dimension](left, right) for dimension in DIMENSIONS
    }
    for dimension, result in (overrides or {}).items():
        dimensions[dimension] = result
    return CompatibilityAssessment(
        overlap_id=overlap_id,
        dimensions=dimensions,
        method_fingerprint=method_fingerprint or "compatibility.operator.v1",
    )


def obstruction_for(assessment: CompatibilityAssessment, left: str, right: str):
    """The obstruction an assessment implies, or ``None`` when nothing blocks."""
    from context.locality import Obstruction

    blocking = assessment.blocking_dimensions
    if not blocking:
        return None
    return Obstruction(
        kind=ObstructionKind.SEMANTIC_OBSTRUCTION
        if any(item is Dimension.SEMANTIC for item in blocking)
        else ObstructionKind.SOURCE_CONFLICT,
        detail=(
            f"dimensions refuted between {left} and {right}: "
            f"{[item.value for item in blocking]}"
        ),
        subject_refs=(left, right),
    )
