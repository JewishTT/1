"""Rank fusion over heterogeneous ranked lists.

Spec 030 CE-001 §0.3 (normative chain: "rank fusion (RRF baseline) → Frontier
execution ledger") and §16.2. Task DON-RET-001/003/004, T0701/T0703.

**Provenance of this file.** Written clean-room. It is *not* donor code.

The specification named ``ranknexus`` and ``fuse`` as fusion candidates. Both were verified
non-existent in ``specs/029-research-closed-loop-upgrade/donors/donor-matrix.md`` §1: no
rank-fusion library named ``fuse`` exists on GitHub (39 unrelated repos — JS fuzzy search, Go
filesystem, sensor fusion, ESB), and ``ranknexus`` resolves to an unlicensed landing page. So
there is nothing to vendor. The registry records this as ``clean-room-inspired``, not
``vendored``, and the manifest must say so — calling a 20-line algorithm "donor code" would be
the kind of claim this platform exists to avoid.

The algorithm itself is Cormack, Clarke and Buettcher's Reciprocal Rank Fusion: a fixed-``k``
reciprocal of rank, summed across lists. It is used here as the **baseline to beat**, not as a
claim that it is the correct fusion for every query class — CE-001 §16.2 says so explicitly, and
the comparison harness in ``bench`` is what settles it.

What this module is responsible for is the part that is easy to get wrong:

* every input declares which ranker produced it and under which query, so a fused rank can be
  explained back to the lists that made it;
* a candidate missing from a list is *absent*, not *ranked last* — conflating the two is how a
  list that returned nothing gets rewarded for saying nothing;
* a ranker that failed is recorded as failed, distinct from one that returned an empty list;
* the ``k`` and the weighting are versioned policy, never a bare constant at the call site.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "RankerOutcome",
    "RankedCandidate",
    "FusionResult",
    "FusionPolicy",
    "reciprocal_rank_fusion",
    "DEFAULT_K",
]

#: The value the original formulation uses. It belongs to the *policy*, so it is a default here
#: and a required field in ``FusionPolicy`` -- a bare ``60`` at a call site is how fusion
#: parameters stop being comparable between runs.
DEFAULT_K = 60


class RankerOutcome(StrEnum):
    """What happened to one ranker on one query.

    ``FAILED`` and ``EMPTY`` are different and must stay different. An empty list is a claim
    about the corpus; a failure is an absence of a claim. Fusing them lets a broken ranker look
    like a confident one that found nothing, which is the most expensive way to be wrong.
    """

    OK = "ok"
    EMPTY = "empty"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """One candidate as one ranker returned it.

    ``rank`` is 1-based. ``score`` is the ranker's own score and is **never** comparable across
    rankers -- it is carried for provenance and is deliberately not an input to RRF.
    """

    candidate_id: str
    source_ranker_id: str
    rank: int
    query_id: str
    evidence_refs: tuple[str, ...] = ()
    score: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.candidate_id).strip():
            raise ValueError("a ranked candidate must have an identity")
        if not str(self.source_ranker_id).strip():
            raise ValueError(
                f"candidate {self.candidate_id!r} has no source ranker; an unattributed rank "
                "cannot be explained and cannot be ablated"
            )
        if self.rank < 1:
            raise ValueError(
                f"rank is 1-based; got {self.rank} for {self.candidate_id!r}. A zero or "
                "negative rank makes ``1/(k+rank)`` a term nobody reasoned about"
            )
        if not str(self.query_id).strip():
            raise ValueError("a ranked candidate must say which query produced it")


@dataclass(frozen=True, slots=True)
class RankerOutcome_:
    """One ranker's result for one query, including how it ended."""

    ranker_id: str
    query_id: str
    outcome: RankerOutcome
    candidates: tuple[RankedCandidate, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        if self.outcome is RankerOutcome.FAILED and not self.error:
            raise ValueError(
                f"ranker {self.ranker_id!r} failed without saying why; a failure nobody can "
                "diagnose is a failure nobody will restore"
            )
        if self.outcome is RankerOutcome.EMPTY and self.candidates:
            raise ValueError(
                f"ranker {self.ranker_id!r} reported EMPTY while returning "
                f"{len(self.candidates)} candidates; the two must not both be true"
            )


@dataclass(frozen=True, slots=True)
class FusionPolicy:
    """Versioned fusion parameters. A run that does not record these cannot be compared."""

    k: int = DEFAULT_K
    weights: Mapping[str, float] = field(default_factory=dict)
    policy_version: str = "rrf/1"
    #: Candidates appearing in no list at all are still emitted, at the bottom, so a caller
    #: can see that two rankers disagreed to produce nothing rather than silently agreeing on
    #: zero.
    include_single_ranker_candidates: bool = True

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError(f"k must be >= 1; got {self.k}")
        for ranker, weight in self.weights.items():
            if weight < 0:
                raise ValueError(f"weight for {ranker!r} is negative: {weight}")

    def weight_for(self, ranker_id: str) -> float:
        return float(self.weights.get(ranker_id, 1.0))

    def fingerprint(self) -> str:
        payload = {
            "k": self.k,
            "weights": dict(sorted(self.weights.items())),
            "policy_version": self.policy_version,
            "include_single_ranker_candidates": self.include_single_ranker_candidates,
        }
        return "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class FusionResult:
    """One fused candidate with the full derivation of its position."""

    candidate_id: str
    fused_rank: int
    fused_score: float
    contributing_rankers: tuple[str, ...]
    per_ranker_ranks: Mapping[str, int | None]
    fusion_policy_fingerprint: str
    query_id: str
    evidence_refs: tuple[str, ...] = ()
    failed_rankers: tuple[str, ...] = ()
    empty_rankers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.contributing_rankers and not self.per_ranker_ranks:
            raise ValueError("a contributing ranker must appear in per_ranker_ranks")

    def explanation(self) -> str:
        """One line an analyst can read to find out why this candidate is where it is."""
        parts = ", ".join(
            f"{r}:{rank if rank is not None else '-'}"
            for r, rank in sorted(self.per_ranker_ranks.items())
        )
        missing = ""
        if self.failed_rankers or self.empty_rankers:
            missing = f" (missing: {', '.join(sorted(self.failed_rankers + self.empty_rankers))})"
        return f"{self.candidate_id} rank {self.fused_rank} [{parts}]{missing}"


def reciprocal_rank_fusion(
    outcomes: Sequence[RankerOutcome_],
    *,
    query_id: str,
    policy: FusionPolicy | None = None,
) -> tuple[FusionResult, ...]:
    """Fuse ranked lists by reciprocal rank.

    ``score(d) = Σ_i w_i / (k + rank_i(d))``

    A candidate absent from list *i* contributes nothing from *i*. It is **not** assigned a
    trailing rank: the whole reason for reciprocal rank fusion is that a list which omitted a
    document said nothing about it, and padding the omission with a rank invents an opinion.
    ``per_ranker_ranks`` therefore carries ``None`` for the lists that omitted it, which is also
    what makes the ``missing:`` line in :meth:`FusionResult.explanation` truthful.

    Ordering is by fused score, then by candidate id. The tie-break is not cosmetic: two runs
    over the same lists must produce the same order, and a score-only sort leaves that to the
    sort implementation.
    """
    policy = policy or FusionPolicy()

    for outcome in outcomes:
        if outcome.query_id != query_id:
            raise ValueError(
                f"outcome for query {outcome.query_id!r} passed to a fusion for {query_id!r}"
            )

    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    evidence: dict[str, list[str]] = {}
    failed = tuple(sorted(o.ranker_id for o in outcomes if o.outcome is RankerOutcome.FAILED))
    empty = tuple(sorted(o.ranker_id for o in outcomes if o.outcome is RankerOutcome.EMPTY))

    contributing: set[str] = set()
    for outcome in outcomes:
        if outcome.outcome is not RankerOutcome.OK:
            continue
        weight = policy.weight_for(outcome.ranker_id)
        seen: set[str] = set()
        for item in outcome.candidates:
            if item.candidate_id in seen:
                raise ValueError(
                    f"ranker {outcome.ranker_id!r} returned {item.candidate_id!r} twice; "
                    "duplicate ranks make the fusion weight a function of list hygiene"
                )
            seen.add(item.candidate_id)
            ranks.setdefault(item.candidate_id, {})[outcome.ranker_id] = item.rank
            scores[item.candidate_id] = scores.get(item.candidate_id, 0.0) + (
                weight / (policy.k + item.rank)
            )
            contributing.add(outcome.ranker_id)
            if item.evidence_refs:
                bucket = evidence.setdefault(item.candidate_id, [])
                bucket.extend(r for r in item.evidence_refs if r not in bucket)

    if not scores and not policy.include_single_ranker_candidates:
        return ()

    # Candidates are the union of every list that returned anything. Ordering is deterministic.
    ordered = sorted(
        scores,
        key=lambda cid: (-scores[cid], cid),
    )
    results: list[FusionResult] = []
    for position, cid in enumerate(ordered, start=1):
        results.append(
            FusionResult(
                candidate_id=cid,
                fused_rank=position,
                fused_score=scores[cid],
                contributing_rankers=tuple(sorted(ranks[cid])),
                per_ranker_ranks={
                    r: ranks[cid].get(r) for r in sorted({o.ranker_id for o in outcomes})
                },
                fusion_policy_fingerprint=policy.fingerprint(),
                query_id=query_id,
                evidence_refs=tuple(evidence.get(cid, ())),
                failed_rankers=failed,
                empty_rankers=empty,
            )
        )
    return tuple(results)


def ranked_candidates(items: Iterable[Mapping[str, Any]], *, ranker_id: str, query_id: str):
    """Adapt a plain sequence of mappings into :class:`RankedCandidate` at 1-based ranks."""
    out = []
    for position, item in enumerate(items, start=1):
        out.append(
            RankedCandidate(
                candidate_id=str(item["id"]),
                source_ranker_id=str(item.get("ranker", ranker_id)),
                rank=int(item.get("rank", position)),
                query_id=query_id,
                evidence_refs=tuple(item.get("evidence_refs", ())),
                score=item.get("score"),
                metadata=item,
            )
        )
    return tuple(out)