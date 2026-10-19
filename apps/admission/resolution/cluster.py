"""Cluster membership is a decision, not a consequence of two agreements (T078, FR-084).

ADR-030-03 D5, spec FR-084::

    Transitive cluster contamination MUST be prevented: pairwise matches MUST NOT imply cluster
    membership where feature evidence is inconsistent.

The contaminated case is short and common. A and B agree. B and C agree. Every pairwise matcher
in the tree will happily return that as {A, B, C}, because ``zero.resolution.graph.
connected_components`` is a union-find over edges and union-find is transitive by construction.
But agreement with B is evidence about B, and A and C may have never been compared, or may have
been compared and found inconsistent. "Both of them are like B" is not "they are like each
other", and in identity resolution the failure mode is fusing two different people who happen to
work at the same address or share a surname.

So this module refuses the shortcut. :func:`cluster_from_decisions` builds groups from merge
*decisions* — never from scores — and a group is admitted only when, for every pair of members,
there is a merge decision in force **or** the pair's own feature evidence is checked and found
consistent. A pair that is contradicted, or never assessed, blocks the cluster and is reported
in :attr:`ClusterProposal.blocked_pairs`. The refusal is visible rather than silent because a
cluster that quietly excludes one member is indistinguishable from a cluster that never had one.

What this module does not do: it does not modify ``CollectiveResolver`` or
``CollectiveResult.cluster_count``. Those are score-propagation diagnostics from feature 013 and
an existing test pins them. ``cluster_count`` returns an integer derived from a threshold; it is
not identity, nothing commits from it, and the docstring on ``collective.py`` says so. This
module exists so that the thing which *would* be identity has to go through a decision first.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from .decision_store import DecisionKind, DecisionStore

__all__ = [
    "ClusterProposal",
    "PairAssessment",
    "PairVerdict",
    "cluster_from_decisions",
    "naive_transitive_closure",
]


class PairVerdict(StrEnum):
    """What the direct evidence between two candidates says. Never inferred from a neighbour."""

    CONSISTENT = "consistent"
    CONTRADICTED = "contradicted"
    #: Same name, same address, nothing else. Real, and routinely mistaken for an answer.
    UNASSESSED = "unassessed"


@dataclass(frozen=True, slots=True)
class PairAssessment:
    """The direct verdict on one pair, with the features that produced it."""

    left: str
    right: str
    verdict: PairVerdict
    reasons: tuple[str, ...] = ()

    @property
    def pair_key(self) -> str:
        return f"{min(self.left, self.right)}&&{max(self.left, self.right)}"

    def to_dict(self) -> dict[str, object]:
        return {
            "pair_key": self.pair_key,
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class ClusterProposal:
    """A candidate cluster and the audit trail of why it is or is not admissible."""

    members: tuple[str, ...]
    decisions: tuple[str, ...] = ()
    """Decision ids the proposal rests on. Empty for a refused proposal."""
    blocked_pairs: tuple[PairAssessment, ...] = ()
    admitted: bool = False
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "members": list(self.members),
            "admitted": self.admitted,
            "decisions": list(self.decisions),
            "blocked_pairs": [p.to_dict() for p in self.blocked_pairs],
            "reasons": list(self.reasons),
        }


def naive_transitive_closure(members: Iterable[str], edges: Iterable[tuple[str, str]]) -> set[str]:
    """What plain transitivity would return. Kept so the test can show the difference.

    This is the shape the platform refuses: it never looks at any feature, so it cannot notice
    that the two ends of a chain contradict each other.
    """
    parent = {m: m for m in members}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
    return {find(m) for m in members}


def cluster_from_decisions(
    store: DecisionStore,
    *,
    assessments: Mapping[str, PairAssessment] | None = None,
    min_members: int = 2,
) -> tuple[ClusterProposal, ...]:
    """Group merge decisions into clusters, refusing any group the direct evidence contradicts.

    ``assessments`` maps a ``pair_key`` to the verdict on that pair *directly*. A pair with no
    entry is :attr:`PairVerdict.UNASSESSED` by default, which blocks any group of three or more
    that depends on it. That default is the conservative direction: silently treating "we never
    compared them" as "they are fine" is the exact contamination FR-084 names.
    """
    assessments = assessments or {}
    merges = [d for d in store.merges_in_force()]
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for decision in merges:
        left, right = decision.pair_key.split("&&")
        union(left, right)

    groups: dict[str, set[str]] = {}
    for member in parent:
        groups.setdefault(find(member), set()).add(member)

    proposals: list[ClusterProposal] = []
    for root in sorted(groups):
        members = tuple(sorted(groups[root]))
        if len(members) < min_members:
            continue
        blocked: list[PairAssessment] = []
        decisions: list[str] = []
        for i, left in enumerate(members):
            for right in members[i + 1 :]:
                key = f"{min(left, right)}&&{max(left, right)}"
                verdict = assessments.get(key)
                if verdict is not None and verdict.verdict is PairVerdict.CONTRADICTED:
                    # Checked before the merge decision, deliberately. A merge decision says a
                    # human asserted these are one person; a contradictory national identifier
                    # says the features disagree. Averaging those into one verdict is exactly
                    # what FR-084 forbids, so the conflict is surfaced and the cluster is
                    # blocked — with the merge left in force for the reviewer to split.
                    blocked.append(verdict)
                    continue
                decision = store.current(key)
                if decision is not None and decision.kind is DecisionKind.MERGE:
                    decisions.append(decision.decision_id)
                    continue
                if verdict is None:
                    blocked.append(
                        PairAssessment(left, right, PairVerdict.UNASSESSED, ("never_compared",))
                    )
                elif verdict.verdict is PairVerdict.UNASSESSED:
                    blocked.append(verdict)
        if blocked:
            proposals.append(
                ClusterProposal(
                    members=members,
                    decisions=(),
                    blocked_pairs=tuple(blocked),
                    admitted=False,
                    reasons=("fr084_pairwise_agreement_is_not_cluster_membership",),
                )
            )
            continue
        proposals.append(
            ClusterProposal(
                members=members,
                decisions=tuple(sorted(set(decisions))),
                admitted=True,
                reasons=("every_member_pair_has_a_decision_or_consistent_evidence",),
            )
        )
    return tuple(proposals)


def contradiction_reasons(
    *,
    shared_id_number: bool = False,
    conflicting_birth_date: bool = False,
    conflicting_name: bool = False,
) -> tuple[str, ...]:
    """Features that make two candidates demonstrably different people.

    A conflicting national identifier or birth date is not weak evidence, it is positive evidence
    of difference, and averaging it away against two strong pairwise agreements is the
    contamination FR-084 exists to stop.
    """
    reasons: list[str] = []
    if shared_id_number:
        reasons.append("different_id_numbers_for_the_same_identifier")
    if conflicting_birth_date:
        reasons.append("birth_dates_disagree")
    if conflicting_name:
        reasons.append("names_disagree")
    return tuple(reasons)


def assess(left: str, right: str, *, reasons: Iterable[str]) -> PairAssessment:
    """Build an assessment from named reasons. Contradiction wins; silence is UNASSESSED."""
    reasons = tuple(reasons)
    return PairAssessment(
        left=left,
        right=right,
        verdict=PairVerdict.CONTRADICTED if reasons else PairVerdict.UNASSESSED,
        reasons=reasons,
    )