"""Structural analysis records + DEFERRED semantics (T122, US5).

Scores are normalized to a documented range and are structural-only (counts,
density, radii) — never person verdicts. Every result carries a permutation-null
significance record or an explicit DEFERRED status with a sampling plan, so no
guarded analysis ever produces a truncated guess (SC-006).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Any


class StructureStatus(StrEnum):
    OK = "ok"
    DEFERRED = "deferred"


class StructureKind(StrEnum):
    SPECTRAL = "spectral"
    MOTIF = "motif"
    HYPERGRAPH = "hypergraph"
    TEMPORAL_NETWORK = "temporal_network"


@dataclass(frozen=True)
class NullModelResult:
    """Permutation-null result (interface-contracts §10)."""

    null_id: str
    shuffle_kind: str
    n_permutations: int
    observed_statistic: float
    null_distribution: tuple[float, ...]
    effect: float
    p_value: float
    warning: str | None = None

    @classmethod
    def build(
        cls,
        *,
        data: dict[Any, Any],
        observed: float,
        null: list[float],
    ) -> NullModelResult:
        n = len(null)
        mean = sum(null) / n if n else 0.0
        if mean > 0:
            effect = observed / mean
        else:
            effect = float("inf") if observed > 0 else 0.0
        p_value = sum(1.0 for value in null if value >= observed) / n if n else 1.0
        warning = (
            "too few permutations for reliable p-value (<100)"
            if n and n < 100
            else None
        )
        digest = sha256(
            f"null:{data.get('graph_ref', '')}:{data.get('shuffle_kind', '')}:{observed}".encode()
        ).hexdigest()[:12]
        return cls(
            null_id=f"NULL-{digest}",
            shuffle_kind=data.get("shuffle_kind", "degree_preserving_stub_swap"),
            n_permutations=n,
            observed_statistic=observed,
            null_distribution=tuple(null),
            effect=effect,
            p_value=round(p_value, 6),
            warning=warning,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "null_id": self.null_id,
            "shuffle_kind": self.shuffle_kind,
            "n_permutations": self.n_permutations,
            "observed_statistic": self.observed_statistic,
            "null_distribution": list(self.null_distribution),
            "effect": self.effect,
            "p_value": self.p_value,
            "warning": self.warning,
        }


@dataclass(frozen=True)
class StructureAnalysisResult:
    """Structural analysis result (interface-contracts §9)."""

    result_id: str
    graph_ref: str
    kind: StructureKind
    algorithm: str
    scores: dict[str, float] = field(default_factory=dict)
    significance: NullModelResult | None = None
    status: StructureStatus = StructureStatus.OK
    budget_rationale: str | None = None

    def to_ref(self) -> str:
        return f"struct:{self.result_id}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "graph_ref": self.graph_ref,
            "kind": self.kind.value if isinstance(self.kind, StructureKind) else self.kind,
            "algorithm": self.algorithm,
            "scores": self.scores,
            "significance": self.significance.as_dict() if self.significance else None,
            "status": self.status.value if isinstance(self.status, StructureStatus) else self.status,
            "budget_rationale": self.budget_rationale,
        }