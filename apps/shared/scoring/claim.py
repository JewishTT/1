"""Claim verdict + corroboration signals (T004, FR-011, investigator pattern).

Separate typed signals (I-7): verdict, corroboration, independent chains and
triangulation are computed from independence chains — never from raw publication
count (FR-002). A claimed verdict is a structural signal for admission/feedback,
never a trusted fact (I-3).
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field


class ClaimVerdict(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class ClaimAssessment:
    claim_id: str = field(default_factory=lambda: "CL-" + uuid.uuid4().hex[:12])
    assertion_refs: list[str] = field(default_factory=list)
    verdict: ClaimVerdict = ClaimVerdict.UNCERTAIN
    corroboration: float = 0.0
    independent_chain_count: int = 0
    publication_count: int = 0
    triangulation: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "assertion_refs": list(self.assertion_refs),
            "verdict": self.verdict.value,
            "corroboration": round(self.corroboration, 3),
            "independent_chain_count": self.independent_chain_count,
            "publication_count": self.publication_count,
            "triangulation": dict(self.triangulation),
            "reasons": list(self.reasons),
        }


def corroboration_score(n_independent_chains: int, publications: int) -> float:
    """Corroboration is driven by independent chains, not raw publication count.

    A single chain with many reprints collapses to a negligible score (FR-002).
    """
    if n_independent_chains <= 0:
        return 0.0
    if n_independent_chains == 1 and publications > 1:
        return 0.1  # reprints collapse: near-zero corroboration
    return min(1.0, 0.4 + 0.2 * (n_independent_chains - 1))


def assess_claim(
    *,
    assertion_refs: list[str],
    independent_chain_count: int,
    publication_count: int,
    contradicted: bool = False,
) -> ClaimAssessment:
    """Evaluate a claim verdict from independence chains (investigator pattern)."""
    if contradicted:
        return ClaimAssessment(
            assertion_refs=list(assertion_refs),
            verdict=ClaimVerdict.CONTRADICTED,
            corroboration=0.0,
            independent_chain_count=independent_chain_count,
            publication_count=publication_count,
            triangulation={"conflict": True},
            reasons=["explicit_contradiction"],
        )

    score = corroboration_score(independent_chain_count, publication_count)
    reasons: list[str] = []
    if 0 < independent_chain_count < publication_count:
        reasons.append("reprints_collapsed")
    if independent_chain_count <= 0:
        verdict = ClaimVerdict.UNCERTAIN
        reasons.append("no_independent_chain")
    elif score >= 0.6:
        verdict = ClaimVerdict.SUPPORTED
        reasons.append("multiple_independent_chains")
    else:
        verdict = ClaimVerdict.UNCERTAIN
        reasons.append("insufficient_corroboration")

    return ClaimAssessment(
        assertion_refs=list(assertion_refs),
        verdict=verdict,
        corroboration=score,
        independent_chain_count=independent_chain_count,
        publication_count=publication_count,
        triangulation={"chains": independent_chain_count, "publications": publication_count},
        reasons=reasons,
    )