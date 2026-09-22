"""Narrative → market operators (T090, econ wiring from votran).

Adapted from votranhabysscoremicro (Apache-2.0): deterministic ports of the
NarrativeEngine (narrative → asset impact), EntropyBoundForecastDecay (forecast
accuracy → entropy → decay) and EchoChamberEffect (cosine belief graph →
belief update + bubble risk). RNG noise is replaced by deterministic
pseudo-noise so results are reproducible.

   Source repo : donors/votranhabysscoremicro/VoTranhAbyssCoreMicro.py
   License     : Apache-2.0
   What changed: networkx/scipy/numpy → stdlib; random.choice/gauss → deterministic
                 selection/noise; dataclass value objects; the political-planet
                 simulator context is dropped (operators only).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Narrative:
    """A generated narrative and its asset-class impact vector."""
    title: str
    impact: dict[str, float]
    strength: float

    def as_dict(self) -> dict[str, Any]:
        return {"title": self.title, "impact": dict(self.impact), "strength": self.strength}


class NarrativeEngine:
    """Deterministic narrative generator (votran NarrativeEngine semantics)."""

    def __init__(self, narrative_strength: float = 0.5) -> None:
        self.narrative_strength = narrative_strength
        self.narrative_history: deque[Narrative] = deque(maxlen=50)
        self.contrarian_count = 0

    def generate_narrative(self, context: dict[str, float]) -> Narrative:
        volatility = context.get("volume_volatility", context.get("Stock_Volatility", 0.0))
        sentiment = context.get("market_sentiment", 0.0)
        fear = context.get("fear_index", 0.0)

        # Donor picks randomly among three templates; deterministic substitute:
        # first template whose gate fires, else the bonds/stocks default.
        def gold_title() -> str:
            return "Gold Is Dead" if sentiment < 0.0 else "Gold Revival Imminent"

        def crypto_title() -> str:
            return "Crypto Surge Ahead" if volatility > 0.5 else "Crypto Stability Returns"

        def bonds_title() -> str:
            return "Bonds Are Safe Haven" if fear > 0.5 else "Stocks To Soar"

        candidates: list[tuple[bool, str]] = [
            (sentiment < 0.0 or sentiment > 0.0, gold_title()),
            (volatility > 0.5, crypto_title()),
        ]
        title = next((title for gate, title in candidates if gate), bonds_title())
        impact: dict[str, float] = {
            "gold": -0.2 if "Gold Is Dead" in title else 0.2,
            "crypto": 0.3 if "Crypto" in title else 0.0,
            "stocks": 0.2 if "Stocks" in title else 0.0,
            "bonds": 0.2 if "Bonds" in title else 0.0,
        }
        narrative = Narrative(
            title=title,
            impact=impact,
            strength=self.narrative_strength * (1.0 + volatility),
        )
        self.narrative_history.append(narrative)
        return narrative

    def trigger_contrarian(self, agent_id: str) -> None:
        del agent_id
        self.contrarian_count += 1

    def metrics(self) -> dict[str, Any]:
        return {
            "narrative_strength": self.narrative_strength,
            "narrative_count": len(self.narrative_history),
            "contrarian_count": self.contrarian_count,
        }


class EntropyBoundForecastDecay:
    """Deterministic entropy-bound forecast decay (votran semantics)."""

    def __init__(self, *, entropy_threshold: float = 0.95, decay_rate: float = 0.03) -> None:
        self.entropy_threshold = entropy_threshold
        self.decay_rate = decay_rate
        self.history: deque[float] = deque(maxlen=7)
        self.entropy_level = 0.0
        self.user_count = 0

    @staticmethod
    def _pseudo_noise(step: int, decay_rate: float) -> float:
        # deterministic ≈ gauss(0, decay_rate), bounded to ±decay_rate
        phase = step * 1.618033988749895
        return decay_rate * math.sin(phase) * math.cos(phase / 2.0)

    def update_forecast(self, predicted_value: float, actual_value: float) -> float:
        accuracy = 1.0 - abs(predicted_value - actual_value) / (abs(actual_value) + 1e-6)
        self.history.append(accuracy)
        self.user_count += 1
        if len(self.history) < 7:
            return predicted_value
        avg_accuracy = sum(self.history) / len(self.history)
        if avg_accuracy > self.entropy_threshold:
            self.entropy_level = min(1.0, self.entropy_level + 0.1 * self.user_count / 1000.0)
            noise = self._pseudo_noise(self.user_count, self.decay_rate)
            return predicted_value * (1.0 - self.entropy_level * noise)
        return predicted_value

    def metrics(self) -> dict[str, float]:
        return {
            "entropy_level": self.entropy_level,
            "user_count": self.user_count,
            "avg_accuracy": sum(self.history) / len(self.history) if self.history else 0.0,
        }


@dataclass
class BeliefHolder:
    """An agent with a five-dimensional belief vector (votran fields)."""
    id: str
    trust_government: float = 0.5
    fear_index: float = 0.0
    risk_appetite: float = 0.5
    faith_in_shaman: float = 0.0
    belief_in_narrative: float = 0.0

    def vector(self) -> list[float]:
        return [
            self.trust_government,
            self.fear_index,
            self.risk_appetite,
            self.faith_in_shaman,
            self.belief_in_narrative,
        ]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    if denominator == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / denominator


class EchoChamberEffect:
    """Cosine belief graph: belief updating + bubble-risk score (votran semantics)."""

    def __init__(self, similarity_threshold: float = 0.85) -> None:
        self.similarity_threshold = similarity_threshold
        self.graph: dict[str, list[tuple[str, float]]] = {}
        self.vectors: dict[str, list[float]] = {}
        self.bubble_risk = 0.0

    def build_belief_graph(self, agents: list[BeliefHolder]) -> None:
        self.vectors = {agent.id: agent.vector() for agent in agents}
        self.graph = {agent.id: [] for agent in agents}
        for left in agents:
            for right in agents:
                if left.id >= right.id:
                    continue
                similarity = _cosine_similarity(left.vector(), right.vector())
                if similarity > self.similarity_threshold:
                    self.graph[left.id].append((right.id, similarity))
                    self.graph[right.id].append((left.id, similarity))

    def update_beliefs(self, agents: list[BeliefHolder], context: dict[str, float]) -> None:
        del context
        for agent in agents:
            neighbors = self.graph.get(agent.id, [])
            if not neighbors:
                continue
            weighted = _weighted_average(neighbors, self.vectors)
            values = agent.vector()
            blended = [max(0.0, min(1.0, 0.7 * value + 0.3 * component)) for value, component in zip(values, weighted)]
            agent.trust_government = blended[0]
            agent.fear_index = blended[1]
            agent.risk_appetite = blended[2]
            agent.faith_in_shaman = blended[3]
            agent.belief_in_narrative = blended[4]
        self._refresh_vectors(agents)
        self._update_bubble_risk()

    def _refresh_vectors(self, agents: list[BeliefHolder]) -> None:
        for agent in agents:
            self.vectors[agent.id] = agent.vector()

    def _update_bubble_risk(self) -> None:
        if not self.vectors:
            self.bubble_risk = 0.0
            return
        dimensions = len(next(iter(self.vectors.values())))
        std_sums = 0.0
        for dim in range(dimensions):
            values = [vector[dim] for vector in self.vectors.values()]
            mean = sum(values) / len(values)
            std_sums += math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        risk = std_sums / dimensions
        if risk < 0.2:
            risk = min(1.0, risk + 0.3)
        self.bubble_risk = risk

    def graph_density(self) -> float:
        nodes = len(self.graph)
        if nodes < 2:
            return 0.0
        edges = sum(len(neighbors) for neighbors in self.graph.values())
        return edges / (nodes * (nodes - 1))

    def metrics(self) -> dict[str, float]:
        return {"bubble_risk": self.bubble_risk, "graph_density": self.graph_density()}


def _weighted_average(neighbors: list[tuple[str, float]], vectors: dict[str, list[float]]) -> list[float]:
    weight_sum = sum(weight for _, weight in neighbors) or 1.0
    dims = len(vectors[neighbors[0][0]])
    averaged = [0.0] * dims
    for node_id, weight in neighbors:
        vector = vectors[node_id]
        for dim in range(dims):
            averaged[dim] += (weight / weight_sum) * vector[dim]
    return averaged