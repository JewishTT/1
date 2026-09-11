"""Information-gain collection planner (T104, US2; interface-contracts §4).

Ranks evidence opportunities by **expected KL divergence** across the alive
(hypothesis) population: an opportunity that separates two competing
explanations earns higher priority; discarded/resolved hypotheses never enter
the prior (dead hypotheses have ``gain_priority=None`` and pull no collection).
Read-only — no envelopes are emitted by the planner itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log

from claims.model import EvidenceDirection, EvidenceLink, Hypothesis, HypothesisStatus
from hypotheses.evidence import derive_credence
from hypotheses.model import is_alive
from store import ScienceStore

_EPS = 1e-9


@dataclass(frozen=True)
class EvidenceOpportunity:
    opportunity_id: str
    description: str
    likelihoods: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RankedOpportunity:
    opportunity_id: str
    expected_gain: float
    discriminating_pair: list[str]


def _clamp(probability: float | None) -> float:
    if probability is None:
        return 0.5
    return min(max(float(probability), 1e-6), 1.0 - 1e-6)


def _expected_kl(priors: dict[str, float], likelihoods: dict[str, float]) -> float:
    alive = list(priors)
    data_prob = sum(priors[h] * _clamp(likelihoods.get(h)) for h in alive)
    data_prob = min(max(data_prob, _EPS), 1.0 - _EPS)

    gain = 0.0
    for hypothesis_id in alive:
        p_prior = priors[hypothesis_id]
        if p_prior <= 0.0:
            continue
        p_obs = _clamp(likelihoods.get(hypothesis_id))
        for p_evidence, posterior_base in ((data_prob, p_obs), (1.0 - data_prob, 1.0 - p_obs)):
            if p_evidence <= _EPS:
                continue
            p_post = p_prior * posterior_base / p_evidence
            if p_post > 0.0:
                gain += p_evidence * p_post * log(p_post / p_prior)
    return float(gain)


def _discriminating_pair(
    priors: dict[str, float], likelihoods: dict[str, float], data_prob: float
) -> list[str]:
    alive = list(priors)
    if not alive:
        return []
    if len(alive) == 1:
        return [alive[0]]
    def _posterior(h: str) -> float:
        p_prior = priors[h]
        p_post = p_prior * _clamp(likelihoods.get(h)) / data_prob
        return min(max(p_post, 0.0), 1.0)
    separation = 0.0
    pair = [alive[0], alive[1]]
    for i, h_a in enumerate(alive):
        for h_b in alive[i + 1 :]:
            delta = abs(_posterior(h_a) - _posterior(h_b))
            if delta > separation:
                separation = delta
                pair = [h_a, h_b]
    return pair


def load_hypotheses(store: ScienceStore, project_id: str) -> list[Hypothesis]:
    """Reconstruct hypotheses from projected records (store-as-source-of-truth)."""
    hypotheses: list[Hypothesis] = []
    for record in store.all("hypotheses"):
        if record.get("project_id") != project_id:
            continue
        links = [
            EvidenceLink(
                link_id=str(item["link_id"]),
                observation_id=str(item["observation_id"]),
                raw_sha256=str(record.get("_first_event", "")),
                direction=EvidenceDirection(item["direction"]),
                weight=float(item.get("weight", 0.0)),
            )
            for item in record.get("evidence_links", [])
        ]
        hypotheses.append(
            Hypothesis(
                hypothesis_id=str(record["hypothesis_id"]),
                project_id=project_id,
                text=str(record.get("text", "")),
                status=HypothesisStatus(record.get("status", "proposed")),
                evidence_links=links,
            )
        )
    return hypotheses


def plan_collection(
    project_id: str,
    opportunities: list[EvidenceOpportunity],
    budget: int,
    *,
    hypotheses: list[Hypothesis] | None = None,
    store: ScienceStore | None = None,
) -> list[RankedOpportunity]:
    """Rank opportunities by expected KL gain across alive hypotheses only.

    The returned plan is read-only (interface-contracts §4: no envelope).
    """
    alive = [h for h in (hypotheses or []) if is_alive(h)]
    if store is not None:
        alive = [h for h in load_hypotheses(store, project_id) if is_alive(h)]
    if not alive:
        return []

    applied = derive_credence(alive)
    priors = {state: prob for state, prob in zip(applied.states, applied.probs, strict=True)}

    ranked: list[RankedOpportunity] = []
    for opp in opportunities:
        data_prob = sum(priors[h] * _clamp(opp.likelihoods.get(h)) for h in priors)
        data_prob = min(max(data_prob, _EPS), 1.0 - _EPS)
        gain = _expected_kl(priors, opp.likelihoods)
        ranked.append(
            RankedOpportunity(
                opportunity_id=opp.opportunity_id,
                expected_gain=gain,
                discriminating_pair=_discriminating_pair(priors, opp.likelihoods, data_prob),
            )
        )

    ranked.sort(key=lambda r: r.expected_gain, reverse=True)
    ranked = ranked[: max(budget, 0)]

    for hypothesis in alive:
        hypothesis.gain_priority = max(
            (r.expected_gain for r in ranked if hypothesis.hypothesis_id in r.discriminating_pair),
            default=None,
        )
    return ranked