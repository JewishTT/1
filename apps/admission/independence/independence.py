"""Source Independence Engine (T087, FR-015).

Builds a citation/derivation graph over observations: edges `cites`, `copies`,
`references`, `rewrites`. From the graph it computes independent evidence
chains (sets of observations whose evidence is not transitively derived from a
single origin) and an independence score per EvidenceLink, which feeds evidence
fusion. `publication_count` (T037) stays separate from `independent_support`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from scoring.claim import ClaimAssessment, assess_claim

from engine.assertions import EvidenceLink


class DerivationEdge(str, Enum):
    CITES = "cites"
    COPIES = "copies"
    REFERENCES = "references"
    REWRITES = "rewrites"


@dataclass
class DerivationEdgeEntry:
    source_doc: str
    target_doc: str
    kind: DerivationEdge
    weight: float = 1.0

    def __hash__(self) -> int:
        return hash((self.source_doc, self.target_doc, self.kind))


class SourceIndependenceEngine:
    """Computes independent evidence chains from the derivation graph."""

    def __init__(self) -> None:
        # observation_id -> list of (derived_from_observation, kind, weight)
        self._derives_from: defaultdict[str, list[tuple[str, DerivationEdge, float]]] = defaultdict(list)
        self._outgoing: defaultdict[str, list[tuple[str, DerivationEdge, float]]] = defaultdict(list)

    def add_edge(self, derived_doc: str, origin_doc: str, kind: DerivationEdge, weight: float = 1.0) -> None:
        self._derives_from[derived_doc].append((origin_doc, kind, weight))
        self._outgoing[origin_doc].append((derived_doc, kind, weight))

    def root_dependencies(self, doc: str) -> frozenset[str]:
        """Set of origin documents a doc ultimately derives from (transitively)."""
        roots: set[str] = set()
        seen: set[str] = set()
        stack = [doc]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            deps = self._derives_from.get(cur)
            if not deps:
                roots.add(cur)
                continue
            for (origin, _, _) in deps:
                stack.append(origin)
        return frozenset(roots)

    def independence_score_for(self, evidence: EvidenceLink) -> float:
        """0=fully derived from a single origin; 1=observations are fully independent."""
        roots: set[str] = set()
        for ref in evidence.evidence_refs:
            roots |= self.root_dependencies(ref.document_id)
        n = len(roots)
        if n <= 1:
            return 0.0
        return min(1.0, 0.4 + 0.12 * n)

    def independent_chains(self, evidence: EvidenceLink) -> list[tuple[str, str]]:
        """Pairs of (root_dependency, evidence_ref.document_id) grouped per root."""
        by_root: dict[str, list[str]] = defaultdict(list)
        for ref in evidence.evidence_refs:
            for root in self.root_dependencies(ref.document_id):
                by_root[root].append(ref.document_id)
        chains = [(root, ",".join(sorted(docs))) for root, docs in by_root.items()]
        return sorted(chains)

    def independent_source_count(self, evidence: EvidenceLink) -> int:
        """Distinct independent evidence chains (FR-002): never == raw publication count."""
        return len(self.independent_chains(evidence))

    def dataset_boundary(self, evidence: EvidenceLink) -> dict[str, int]:
        """FTM dataset-as-provenance-boundary view (FR-002)."""
        publications = len({r.document_id for r in evidence.evidence_refs})
        return {
            "publication_count": publications,
            "independent_source_count": self.independent_source_count(evidence),
        }

    def fuse(self, evidence: EvidenceLink) -> EvidenceLink:
        evidence.independent_support = self.independence_score_for(evidence)
        evidence.independent_evidence_chains = self.independent_chains(evidence)
        evidence.independent_source_count = self.independent_source_count(evidence)
        return evidence

    def assess_claim(
        self,
        evidence: EvidenceLink,
        *,
        contradicted: bool = False,
        assertion_refs: list[str] | None = None,
    ) -> ClaimAssessment:
        """investigator-style claim verdict from independence chains (FR-011).

        Verdict/corroboration derive from independent chains, never raw
        publication count (FR-002). A single chain with many reprints collapses
        to a negligible corroboration score.
        """
        return assess_claim(
            assertion_refs=assertion_refs or [],
            independent_chain_count=self.independent_source_count(evidence),
            publication_count=evidence.publication_count,
            contradicted=contradicted,
        )