"""Error primitives for the Scientific Intelligence Fabric (T085, FR-001/002/007).

Typed errors mirror the shared domain invariant style (``domain.ConstraintViolation``)
so callers can distinguish provenance gaps (FR-001), undeclared probability methods
(FR-002), missing hypothesis decisions (SC-003), and scope-boundary refusals
(FR-007 / ``contracts/scope-boundary.md``).
"""

from __future__ import annotations


class ScienceError(Exception):
    """Base class for scientific fabric errors."""


class ProvenanceRequiredError(ScienceError):
    """FR-001: a claim must trace to immutable observations (never empty provenance)."""

    def __init__(self, claim_id: str = "unknown") -> None:
        super().__init__(
            f"Claim {claim_id} has empty provenance; every claim must trace "
            "Claim -> EvidenceLink -> Observation -> Raw"
        )


class UnknownModelError(ScienceError):
    """FR-002: a claim's probability method must resolve to a declared model."""

    def __init__(self, model_id: str = "unknown") -> None:
        super().__init__(
            f"Probability source '{model_id}' is not a declared model; "
            "no confidence may be fabricated (FR-002)"
        )


class DecisionRequiredError(ScienceError):
    """SC-003: discarding a hypothesis requires a recorded who/when/why decision."""

    def __init__(self, hypothesis_id: str = "unknown") -> None:
        super().__init__(
            f"Hypothesis {hypothesis_id} cannot be discarded without a DecisionRecord "
            "(who/when/why); evidence links are preserved either way"
        )


class ScopeBoundaryError(ScienceError):
    """FR-007: person-level sensitive outcomes are hard-excluded before computation.

    Policy reference: contracts/scope-boundary.md. Raised before any analysis; the
    consuming layer must also emit a scope-rejection audit event.
    """

    def __init__(self, outcome_attribute: str = "unknown") -> None:
        super().__init__(
            f"Scope refusal: outcome class '{outcome_attribute}' targets a natural "
            "person's sensitive attribute (politics / illegal activity / marginalized "
            "group) and is prohibited by contracts/scope-boundary.md (FR-007)"
        )


class DeferredAnalysisError(ScienceError):
    """SC-006: structural analysis exceeding the complexity budget is deferred, never truncated."""

    def __init__(self, detail: str = "analysis deferred (budget exceeded)") -> None:
        super().__init__(detail)


class ReproductionError(ScienceError):
    """SC-007: a pinned re-run failed to reproduce recorded output within tolerance."""

    def __init__(self, run_id: str = "unknown", delta: float = 0.0) -> None:
        super().__init__(
            f"Experiment run {run_id} did not reproduce within tolerance (delta={delta})"
        )