"""Harvest wave orchestrator (spec/010 §0.9 stabilization, FR-005/FR-011/FR-012).

Runs the full per-wave cycle for a batch of raw seeds:

    detect → harvest → gate → enrich → feedback (new seeds) → next wave

until stabilization (the new-seed yield falls below ``min_new_seeds``) or the
``max_depth`` (default 3) is reached. Order is fully deterministic: seeds and
modules are processed in sorted order, resolution clusters collapse duplicate
candidates, and feedback dedups on normalized ``(type, value)`` keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enrichment.feedback import FeedbackLoop
from .enrichment.modules import run_enrichers
from .harvesters.contracts import ObservationCandidate
from .harvesters.registry import HarvesterContext, HarvesterRegistry
from .harvesters.transport import OfflineTransport, Transport
from .observation_gate import ZeroLayerGate
from .resolution.graph import cluster_candidates
from .type_detector import SeedInput, TypeDetector

DEFAULT_MAX_DEPTH = 3
DEFAULT_MIN_NEW_SEEDS = 1


@dataclass
class WaveSummary:
    """Deterministic report of one harvest wave (emitted as cycle metrics)."""

    wave_index: int
    seeds_in: int
    contacts_out: int
    new_seeds_discovered: int
    confidence_dist: tuple[tuple[str, int], ...]
    stabilized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "wave_index": self.wave_index,
            "seeds_in": self.seeds_in,
            "contacts_out": self.contacts_out,
            "new_seeds_discovered": self.new_seeds_discovered,
            "confidence_dist": dict(self.confidence_dist),
            "stabilized": self.stabilized,
        }


class HarvestWave:
    """Wave orchestrator for a single batch of raw seeds."""

    def __init__(
        self,
        *,
        detector: TypeDetector | None = None,
        registry: HarvesterRegistry | None = None,
        gate: ZeroLayerGate | None = None,
        feedback: FeedbackLoop | None = None,
        transport: Transport | None = None,
        dns_exists=None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        min_new_seeds: int = DEFAULT_MIN_NEW_SEEDS,
    ) -> None:
        self._detector = detector or TypeDetector()
        self._registry = registry if registry is not None else HarvesterRegistry()
        self._gate = gate or ZeroLayerGate()
        self._feedback = feedback or FeedbackLoop(detector=self._detector)
        self._transport = transport or OfflineTransport()
        self._dns_exists = dns_exists
        self._max_depth = max_depth
        self._min_new_seeds = min_new_seeds
        self._seen_keys: set[str] = set()
        self._observations = []

    # -- main entry --------------------------------------------------------------

    def run(self, raw_seeds: list[str]) -> list[WaveSummary]:
        """Run waves until stabilization; returns per-wave summaries in order."""
        current: list[SeedInput] = []
        for raw in raw_seeds:
            seed = self._detector.detect(raw)
            current.append(seed)
            self._seen_keys.add(_seed_key(seed))

        summaries: list[WaveSummary] = []
        for wave_index in range(self._max_depth):
            self._gate.emit_started(wave_index=wave_index, seed_count=len(current))
            summary, wave_candidates = self._run_wave(wave_index, current)
            summaries.append(summary)

            new_seeds = self._feedback.new_seeds(wave_candidates, seen=self._seen_keys)
            summaries[-1].new_seeds_discovered = len(new_seeds)
            if len(new_seeds) < self._min_new_seeds:
                summaries[-1].stabilized = True
                break
            current = [self._detector.detect(seed.derived_value) for seed in new_seeds]
            for seed in current:
                self._seen_keys.add(_seed_key(seed))
        return summaries

    # -- per-wave plumbing ---------------------------------------------------------

    def _run_wave(
        self, wave_index: int, seeds: list[SeedInput]
    ) -> tuple[WaveSummary, list[ObservationCandidate]]:
        wave_candidates: list[ObservationCandidate] = []
        for seed in sorted(seeds, key=lambda s: s.raw_value):
            harvested = self._harvest_and_enrich(seed)
            clustering = cluster_candidates(harvested)
            wave_candidates.extend(clustering)
            derived = [c.value for c in clustering if c.confidence >= 0.5]
            self._observations.append(
                self._gate.emit(seed=seed, candidates=clustering, derived_seeds=derived)
            )
        dist = _confidence_dist_from(wave_candidates)
        summary = WaveSummary(
            wave_index=wave_index,
            seeds_in=len(seeds),
            contacts_out=len(wave_candidates),
            new_seeds_discovered=0,
            confidence_dist=dist,
        )
        return summary, wave_candidates

    def _harvest_and_enrich(self, seed: SeedInput) -> list[ObservationCandidate]:
        ctx = HarvesterContext(
            seed=seed,
            transport=self._transport,
            dns_exists=self._dns_exists,
            dns_records=None,
        )
        flat: list[ObservationCandidate] = []
        for result in self._registry.run(seed, ctx):
            flat.extend(result.candidates)
        flat.extend(run_enrichers(seed, {"dns_records": ctx.dns_records}))
        return flat


def _seed_key(seed: SeedInput) -> str:
    return f"{seed.detected_type.value}:{seed.raw_value.lower()}"


def _confidence_dist_from(candidates: list[ObservationCandidate]) -> tuple[tuple[str, int], ...]:
    from .observation_gate import confidence_distribution

    return confidence_distribution(candidates)