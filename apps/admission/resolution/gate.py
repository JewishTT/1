"""The admission gate for identity: the only path from a proposal to a MERGE (T081, FR-081).

Load-bearing invariant, stated once and enforced in code below:

    **A similarity probability, centrality, graph adjacency, topological feature or model output
    never commits a merge on its own. A score is evidence, not a decision.**

That was violated in the 029 audit: the merge bar was ``match_score >= 0.8`` against a profile
whose own ``version`` field read ``"UNCALIBRATED-v1"``, out of a ``MediaProfile`` that starts
empty so every unregistered entity type fell back to exactly those defaults. A number nobody
fitted was able to fuse two people, and after the fusion the mistake was indistinguishable from
a fact. ``engine/admission.py`` closed that specific hole for the admission lane (WP-E T070).
This module closes it for the resolution lane, where the defect is still live:
``CorrelationService.decide`` will happily ACCEPT on a review string with nothing checking the
matcher's self-declared calibration, and nothing anywhere refused on centrality or adjacency.

Four guards, each returning a machine-readable code rather than raising a bare ``ValueError``,
because a refusal nobody can grep for is a refusal nobody notices:

``fr081_derived_signal_only``
    Every item of evidence is derived from the matcher or the graph — no observation, no span.
    High score, perfect corroboration by its own count, still nothing to commit with.

``fr081_score_alone_cannot_commit``
    ``authority=MATCHER``. FR-081 says no model output may *by itself* authorise a merge, so this
    path is refused unconditionally. It is not low-scoring that disqualifies it; being the author.

``t081_uncalibrated_matcher_cannot_commit``
    ``authority=POLICY`` with a matcher profile that declares itself uncalibrated. Refused at
    every score, because the check is on the *declaration*, not the magnitude. A policy may
    commit a merge using a calibrated matcher; it may not commit one using a number nobody
    fitted, however confident the number sounds.

``fr083_review_required``
    An ambiguous pair, or one whose matcher is uncalibrated, needs a named human reviewer. "The
    analyst agreed" is an actor; "the score was high" is not.

There is no fifth guard that could be weakened into the first. ``commit_merge`` is the only
writer of ``DecisionKind.MERGE`` in this package, and it takes no score.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .decision_store import (
    ClaimBinding,
    DecisionKind,
    DecisionStore,
    IdentityHypothesis,
    MatcherProfile,
    ResolutionDecision,
    UnknownDecision,
    corroboration_from_counts,
    new_decision,
)
from .span import EvidenceSpanRef, Grounding, grounding_of, ungrounded

__all__ = [
    "EvidenceItem",
    "EvidenceKind",
    "GateOutcome",
    "IdentityResolutionGate",
    "MergeAuthority",
    "MergeRefused",
    "Refusal",
]


class MergeRefused(RuntimeError):
    """The gate declined to commit a merge. Carries the code, so the refusal is queryable."""

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(f"{refusal.code}: {refusal.detail}")
        self.refusal = refusal


@dataclass(frozen=True, slots=True)
class Refusal:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


class MergeAuthority(StrEnum):
    """Who is authoring the merge. Not how confident they are."""

    HUMAN_REVIEW = "human_review"
    POLICY = "policy"
    MATCHER = "matcher"


class EvidenceKind(StrEnum):
    """What kind of thing an evidence item is.

    The split is the point: :attr:`OBSERVATION` is a thing in the world that can be checked,
    and the rest are inferences from it. FR-081 names the inferences exactly — probability,
    centrality, adjacency, topology, model output — so they are enumerated here rather than
    left to a caller's naming discipline.
    """

    OBSERVATION = "observation"
    SPAN = "span"
    SIMILARITY_PROBABILITY = "similarity_probability"
    MATCH_WEIGHT = "match_weight"
    CENTRALITY = "centrality"
    GRAPH_ADJACENCY = "graph_adjacency"
    TOPOLOGY = "topology"
    MODEL_OUTPUT = "model_output"


#: FR-081's enumerated list, exactly. Nothing in this set may authorise a merge by itself.
DERIVED_EVIDENCE = frozenset(
    {
        EvidenceKind.SIMILARITY_PROBABILITY,
        EvidenceKind.MATCH_WEIGHT,
        EvidenceKind.CENTRALITY,
        EvidenceKind.GRAPH_ADJACENCY,
        EvidenceKind.TOPOLOGY,
        EvidenceKind.MODEL_OUTPUT,
    }
)

#: Evidence that grounds a proposal in something checkable.
GROUNDING_EVIDENCE = frozenset({EvidenceKind.OBSERVATION, EvidenceKind.SPAN})


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    kind: EvidenceKind
    ref: str = ""

    @property
    def is_grounding(self) -> bool:
        return self.kind in GROUNDING_EVIDENCE


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """What the gate did. A refusal is an outcome, not an exception with no record."""

    decision: ResolutionDecision | None
    refusals: tuple[Refusal, ...] = ()
    hypotheses: tuple[IdentityHypothesis, ...] = ()

    @property
    def committed(self) -> bool:
        return self.decision is not None

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(r.code for r in self.refusals)

    def to_dict(self) -> dict[str, object]:
        return {
            "committed": self.committed,
            "decision_id": self.decision.decision_id if self.decision else None,
            "kind": self.decision.kind.value if self.decision else None,
            "refusals": [r.to_dict() for r in self.refusals],
            "grounding": grounding_of(self.decision.span_refs).value
            if self.decision
            else Grounding.UNGROUNDED.value,
        }


class IdentityResolutionGate:
    """The single writer of ``DecisionKind.MERGE`` for the resolution lane."""

    def __init__(self, store: DecisionStore | None = None) -> None:
        # `store or DecisionStore()` is wrong here: DecisionStore defines __len__, so an empty
        # store is falsy and the injected store would be silently discarded for a fresh one.
        self._store = store if store is not None else DecisionStore()

    @property
    def store(self) -> DecisionStore:
        return self._store

    # -- proposal -------------------------------------------------------------

    def propose(
        self,
        pair_key: str,
        statement: str,
        *,
        raised_by: str,
        score: float | None = None,
        score_semantics: str = "",
        evidence: Sequence[EvidenceItem] = (),
        span_refs: Sequence[EvidenceSpanRef] = (),
    ) -> IdentityHypothesis:
        """Record a competing reading of a pair.

        Always lands as a hypothesis, never as a decision, regardless of ``score``. This is the
        method every matcher output goes through, and its return type has no decision field in
        it — there is no value of ``score`` that turns a proposal into a merge.
        """
        hypothesis = IdentityHypothesis(
            hypothesis_id=f"HYP-{abs(hash((pair_key, statement, raised_by))) % (16**12):012x}",
            pair_key=pair_key,
            statement=statement,
            raised_by=raised_by,
            score=score,
            score_semantics=score_semantics,
            evidence_refs=tuple(e.ref for e in evidence),
            span_refs=tuple(span_refs),
        )
        return self._store.record_hypothesis(hypothesis)

    # -- commitment -----------------------------------------------------------

    def commit_merge(
        self,
        pair_key: str,
        *,
        authority: MergeAuthority,
        decided_by: str,
        hypothesis_id: str | None = None,
        matcher: MatcherProfile | None = None,
        reviewer_id: str | None = None,
        evidence: Sequence[EvidenceItem] = (),
        span_refs: Sequence[EvidenceSpanRef] = (),
        corroboration: tuple[str, int, dict[str, int | str]] | None = None,
        documents: int = 0,
        hosts: int = 0,
        lineage_roots: int | None = None,
        rationale: str = "",
        ambiguous: bool = False,
    ) -> GateOutcome:
        """Commit a merge, or refuse with reasons. Takes no score argument, by design.

        ``corroboration`` overrides the counts; otherwise they are built by
        :func:`resolution.decision_store.corroboration_from_counts`, which names the measure.
        """
        refusals = self._refusals(
            authority=authority,
            decided_by=decided_by,
            reviewer_id=reviewer_id,
            matcher=matcher,
            evidence=evidence,
            span_refs=span_refs,
            ambiguous=ambiguous,
            hypothesis_id=hypothesis_id,
        )
        if refusals:
            return GateOutcome(decision=None, refusals=refusals)

        counts = corroboration or corroboration_from_counts(
            documents=documents, hosts=hosts, lineage_roots=lineage_roots
        )
        decision = new_decision(
            pair_key=pair_key,
            kind=DecisionKind.MERGE,
            decided_by=decided_by,
            hypothesis_id=hypothesis_id,
            matcher=matcher,
            corroboration=counts,
            rationale=rationale,
            evidence_refs=tuple(e.ref for e in evidence),
            span_refs=span_refs,
        )
        return GateOutcome(decision=self._store.append(decision), refusals=())

    def split(
        self,
        pair_key: str,
        *,
        decided_by: str,
        supersedes: str | None = None,
        hypothesis_id: str | None = None,
        reviewer_id: str | None = None,
        rationale: str = "",
        documents: int = 0,
        hosts: int = 0,
        lineage_roots: int | None = None,
    ) -> GateOutcome:
        """Split a pair by appending a SPLIT that supersedes the merge.

        Nothing is deleted (FR-082). The merge stays readable with its evidence, its author and
        its timestamp, which is what makes the split auditable rather than a silent correction.
        """
        target = supersedes or self._current_merge(pair_key)
        if target is None:
            raise UnknownDecision(
                f"cannot split {pair_key!r}: there is no merge in force to supersede. A split "
                "with nothing to contradict is not a reversal, it is a no-op with a name on it"
            )
        decision = new_decision(
            pair_key=pair_key,
            kind=DecisionKind.SPLIT,
            decided_by=decided_by,
            supersedes=target.decision_id,
            hypothesis_id=hypothesis_id,
            corroboration=corroboration_from_counts(
                documents=documents, hosts=hosts, lineage_roots=lineage_roots
            ),
            rationale=rationale,
            evidence_refs=(f"reviewer:{reviewer_id}",) if reviewer_id else (),
        )
        return GateOutcome(decision=self._store.append(decision), refusals=())

    def bind_claim(self, claim_id: str, pair_key: str, *, decided_by: str | None = None) -> ClaimBinding:
        """Bind a claim to whatever interpretation is in force for its pair *right now*.

        The binding is written once and never re-pointed. Later re-interpretation produces a new
        decision; the claim keeps pointing at the one it was written under (ADR-030-03 D3).
        """
        current = self._store.current(pair_key)
        interpretation = current.decision_id if current and current.kind is DecisionKind.MERGE else None
        return self._store.bind_claim(claim_id, interpretation, note=decided_by or "")

    # -- guards ---------------------------------------------------------------

    def _refusals(
        self,
        *,
        authority: MergeAuthority,
        decided_by: str,
        reviewer_id: str | None,
        matcher: MatcherProfile | None,
        evidence: Sequence[EvidenceItem],
        span_refs: Sequence[EvidenceSpanRef],
        ambiguous: bool,
        hypothesis_id: str | None,
    ) -> tuple[Refusal, ...]:
        refusals: list[Refusal] = []

        if not decided_by:
            refusals.append(
                Refusal("fr082_unattributed_decision", "decided_by is required on every decision")
            )

        if authority is MergeAuthority.MATCHER:
            # Unconditional. Not "high scores are refused" — being the author is disqualifying.
            refusals.append(
                Refusal(
                    "fr081_score_alone_cannot_commit",
                    f"authority={authority.value}: a matcher may propose; it may not authorise "
                    "a merge at any score (FR-081)",
                )
            )

        grounding_evidence = [e for e in evidence if e.is_grounding]
        if not grounding_evidence and grounding_of(span_refs) is not Grounding.GROUNDED:
            kinds = sorted({e.kind.value for e in evidence}) or ["none"]
            refusals.append(
                Refusal(
                    "fr081_derived_signal_only",
                    "every item of evidence is derived from the matcher or the graph "
                    f"({', '.join(kinds)}); a merge needs an observation or a span",
                )
            )

        if matcher is not None and matcher.declares_uncalibrated:
            if authority is not MergeAuthority.HUMAN_REVIEW:
                refusals.append(
                    Refusal(
                        "t081_uncalibrated_matcher_cannot_commit",
                        f"matcher {matcher.name!r} version {matcher.version!r} declares itself "
                        "uncalibrated; the check is on the declaration, not the score",
                    )
                )
            if not reviewer_id:
                refusals.append(
                    Refusal(
                        "fr083_review_required",
                        "a match proposed by an uncalibrated matcher needs a named human "
                        "reviewer before it can be committed",
                    )
                )

        if hypothesis_id is not None:
            known = {h.hypothesis_id for h in self._store.hypotheses()}
            if hypothesis_id not in known:
                refusals.append(
                    Refusal("fr080_unknown_hypothesis", f"hypothesis {hypothesis_id!r} was never proposed")
                )

        if ambiguous and not reviewer_id:
            refusals.append(
                Refusal(
                    "fr083_review_required",
                    "the pair is labelled ambiguous; FR-083 requires human review where "
                    "ambiguity requires it",
                )
            )

        return tuple(refusals)

    # -- internals ------------------------------------------------------------

    def _current_merge(self, pair_key: str) -> ResolutionDecision | None:
        current = self._store.current(pair_key)
        if current is not None and current.kind is DecisionKind.MERGE:
            return current
        return None


def ungrounded_span(observation_ref: str, uri: str, reason: str) -> EvidenceSpanRef:
    """An explicitly un-grounded span for proposals whose source cannot be located (contract 02 R4)."""
    from .span import SourceLocator

    return ungrounded(observation_ref, reason, SourceLocator(uri=uri))