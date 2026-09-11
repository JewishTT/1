"""Pairwise resolver (T035, FR-013).

Consumes blocking pairs and produces per-type signal scoring: raw_pair_score in
[0,1] plus an explicit list of `reasons` (evidence labels). Deterministic for
identical inputs; never mutates the source candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .blocking import BlockedPair, CandidateRecord


@dataclass
class ResolvedPair:
    candidate_a: str
    candidate_b: str
    raw_pair_score: float = 0.0
    collective_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    strategies: set[str] = field(default_factory=set)


def _fold(s: str | None) -> str:
    import unicodedata

    if not s:
        return ""
    v = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in v if not unicodedata.combining(c))


def _token_sim(a: str | None, b: str | None) -> float:
    fa, fb = _fold(a), _fold(b)
    if not fa or not fb:
        return 0.0
    if fa == fb:
        return 1.0
    if SequenceMatcher(None, fa, fb).ratio() >= 0.85:
        return 0.85
    return 0.4 if set(fa.split()) & set(fb.split()) else 0.0


class PairwiseResolver:
    """Signal scoring of one candidate pair."""

    def signal_scores(self, a: CandidateRecord, b: CandidateRecord) -> dict[str, float]:
        email_same = bool(a.email and b.email and _fold(a.email) == _fold(b.email))
        dom_same = bool(a.email and b.email and _fold(a.email).rsplit("@", 1)[-1] == _fold(b.email).rsplit("@", 1)[-1])
        id_same = bool(a.id_number and b.id_number and _fold(a.id_number) == _fold(b.id_number))
        dob_same = bool(a.birth_date and b.birth_date and a.birth_date[:4] == b.birth_date[:4])
        handle_same = bool(a.handle and b.handle and _fold(a.handle) == _fold(b.handle))
        scores: dict[str, float] = {
            "name": _token_sim(a.name, b.name),
            "alias": float(any(_token_sim(al, a.name) or _token_sim(al, b.name) for al in (b.aliases + a.aliases))),
            "email": float(email_same),
            "domain": float(dom_same),
            "id": float(id_same),
            "dob": float(dob_same),
            "location": _token_sim(a.location, b.location),
            "org": _token_sim(a.organization, b.organization),
            "handle": float(handle_same),
            "co_doc": float(bool(set(a.doc_ids) & set(b.doc_ids))),
        }
        return scores

    def resolve(self, a: CandidateRecord, b: CandidateRecord, pair: BlockedPair | None = None) -> ResolvedPair:
        scores = self.signal_scores(a, b)
        reasons: list[str] = [name for name, s in scores.items() if s > 0.15]
        heuristic = max(scores.values(), default=0.0) if scores else 0.0
        if reasons:
            boost = min(1.0, heuristic + 0.12 * (len(reasons) - 1))
        else:
            boost = 0.0
        raw = round(min(1.0, boost), 3)
        return ResolvedPair(
            candidate_a=a.candidate_id,
            candidate_b=b.candidate_id,
            raw_pair_score=raw,
            reasons=sorted(reasons),
            strategies=set(pair.strategies) if pair else set(),
        )