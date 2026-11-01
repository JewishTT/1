"""Harvest wave orchestrator (spec/010 §0.9 stabilization, FR-005/FR-011/FR-012).

The wave is deterministic and bounded. Source modules and candidates are ordered
before aggregation; each per-seed wave preserves three separately addressable
outputs (HARVEST, ENRICHMENT, RESOLUTION) so downstream consumers can replay the
specific stage without mistaking a derived candidate for an external fact.

A default registry is populated from the checked-in module table. An explicitly
injected registry is never widened implicitly, which keeps tests and deployments
able to constrain the execution surface.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
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
STAGE_NAMES = frozenset({"HARVEST", "ENRICHMENT", "RESOLUTION"})


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


@dataclass(frozen=True)
class WaveStageRecord:
    """One immutable stage output; candidates remain provisional until admission."""

    wave_index: int
    seed_id: str
    seed_type: str
    seed_value: str
    stage: str
    candidates: tuple[ObservationCandidate, ...]
    module_names: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    pending_worker_commands: int = 0
    derived_seeds: tuple[str, ...] = ()
    parent_observation_id: str = ""
    source_id: str = ""

    def __post_init__(self) -> None:
        if self.wave_index < 0:
            raise ValueError("wave_index cannot be negative")
        if self.stage not in STAGE_NAMES:
            raise ValueError(f"unsupported zero-layer stage: {self.stage!r}")

    def as_dict(self) -> dict[str, Any]:
        """Stable body written to the canonical Capture/Observation path."""
        return {
            "schema": "zero-layer-stage/v1",
            "wave_index": self.wave_index,
            "seed_id": self.seed_id,
            "seed_type": self.seed_type,
            "seed_value": self.seed_value,
            "stage": self.stage,
            "module_names": list(self.module_names),
            "notes": list(self.notes),
            "pending_worker_commands": self.pending_worker_commands,
            "candidate_count": len(self.candidates),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "derived_seeds": list(self.derived_seeds),
            "parent_observation_id": self.parent_observation_id,
            "source_id": self.source_id,
            "result_role": "DISCOVERY_ONLY",
            "claim_admission_allowed": False,
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
        enable_enrichment: bool = True,
        seed_context: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        if not 1 <= int(max_depth) <= 5:
            raise ValueError("max_depth must be between 1 and 5")
        if int(min_new_seeds) < 0:
            raise ValueError("min_new_seeds cannot be negative")
        self._detector = detector or TypeDetector()
        if registry is None:
            registry = HarvesterRegistry()
            registry.register_all()
        self._registry = registry
        self._gate = gate or ZeroLayerGate()
        self._feedback = feedback or FeedbackLoop(detector=self._detector)
        self._transport = transport or OfflineTransport()
        self._dns_exists = dns_exists
        self._max_depth = int(max_depth)
        self._min_new_seeds = int(min_new_seeds)
        self._enable_enrichment = bool(enable_enrichment)
        self._seed_context = {
            str(key): dict(value) for key, value in (seed_context or {}).items()
        }
        self._seen_keys: set[str] = set()
        self._observations = []
        self._stage_records: list[WaveStageRecord] = []

    @property
    def stage_records(self) -> tuple[WaveStageRecord, ...]:
        """The last run's HARVEST/ENRICHMENT/RESOLUTION records in stable order."""
        return tuple(self._stage_records)

    # -- main entry --------------------------------------------------------------

    def run(self, raw_seeds: list[str]) -> list[WaveSummary]:
        """Run waves until stabilization; returns per-wave summaries in order.

        A HarvestWave instance is reusable. Every invocation starts a new run-local
        dedup set and record list, so a second call cannot inherit the first run's
        feedback state or accidentally persist stale stage records.
        """
        self._seen_keys.clear()
        self._observations.clear()
        self._stage_records.clear()

        current: list[SeedInput] = []
        for raw in raw_seeds:
            seed = self._detector.detect(raw)
            current.append(seed)
            self._seen_keys.add(_seed_key(seed))
        if not current:
            return []

        summaries: list[WaveSummary] = []
        for wave_index in range(self._max_depth):
            self._gate.emit_started(wave_index=wave_index, seed_count=len(current))
            summary, wave_candidates = self._run_wave(wave_index, current)
            summaries.append(summary)

            new_seeds = self._feedback.new_seeds(wave_candidates, seen=self._seen_keys)
            summary.new_seeds_discovered = len(new_seeds)
            if len(new_seeds) < self._min_new_seeds:
                summary.stabilized = True
            self._gate.emit_cycle(
                wave_index=wave_index,
                seeds_in=summary.seeds_in,
                contacts_out=summary.contacts_out,
                new_seeds_discovered=summary.new_seeds_discovered,
                confidence_dist=summary.confidence_dist,
            )
            if summary.stabilized:
                break
            current = [self._detector.detect(seed.derived_value) for seed in new_seeds]
            for seed in current:
                self._seen_keys.add(_seed_key(seed))
        return summaries

    async def run_and_persist(
        self,
        raw_seeds: list[str],
        *,
        evidence_sink: Any,
        tenant_id: str,
        investigation_id: str | None = None,
    ) -> tuple[list[WaveSummary], list[Any]]:
        """Run and persist every stage through an injected canonical evidence sink.

        The adapter is deliberately injected: zero-layer owns deterministic extraction,
        while the composition root supplies the platform's raw-first ArtifactSink.
        Every returned observation is DISCOVERY_ONLY and is barred from claim admission.
        """
        if evidence_sink is None:
            raise ValueError("evidence_sink is required for persisted zero-layer runs")
        if not tenant_id or not str(tenant_id).strip():
            raise ValueError("tenant_id is required for persisted zero-layer runs")
        summaries = await asyncio.to_thread(self.run, raw_seeds)
        accepted: list[Any] = []
        captures = getattr(self._transport, "captures", ())
        captures = captures() if callable(captures) else captures
        persist_capture = getattr(evidence_sink, "persist_capture", None)
        if captures and not callable(persist_capture):
            raise TypeError("evidence_sink must implement persist_capture for raw network captures")
        for capture in captures or ():
            accepted.append(await persist_capture(
                capture,
                tenant_id=tenant_id,
                investigation_id=investigation_id,
            ))
        for record in self._stage_records:
            accepted.append(await evidence_sink.persist(
                record,
                tenant_id=tenant_id,
                investigation_id=investigation_id,
            ))
        return summaries, accepted

    # -- per-wave plumbing ---------------------------------------------------------

    def _run_wave(
        self, wave_index: int, seeds: list[SeedInput]
    ) -> tuple[WaveSummary, list[ObservationCandidate]]:
        wave_candidates: list[ObservationCandidate] = []
        for seed in sorted(seeds, key=lambda s: s.raw_value):
            ctx = HarvesterContext(
                seed=seed,
                transport=self._transport,
                dns_exists=self._dns_exists,
                dns_records=None,
            )
            module_results = self._registry.run(seed, ctx)
            harvested = [
                candidate
                for result in module_results
                for candidate in result.candidates
            ]
            enriched = (
                run_enrichers(seed, {"dns_records": ctx.dns_records})
                if self._enable_enrichment
                else []
            )
            combined = harvested + enriched
            clustering = cluster_candidates(combined)
            clustering = sorted(clustering, key=lambda c: (c.kind, c.value, c.source_module))
            derived = sorted(c.value for c in clustering if c.confidence >= 0.5)

            module_names = tuple(result.module for result in module_results)
            module_notes = tuple(
                f"{result.module}: {note}"
                for result in module_results
                for note in result.notes
            )
            pending_commands = sum(len(result.commands) for result in module_results)
            seed_context = self._seed_context.get(seed.raw_value, {})
            common = {
                "wave_index": wave_index,
                "seed_id": seed.seed_id,
                "seed_type": seed.detected_type.value,
                "seed_value": seed.raw_value,
                "parent_observation_id": str(seed_context.get("parent_observation_id") or ""),
                "source_id": str(seed_context.get("source_id") or ""),
            }
            self._stage_records.extend(
                (
                    WaveStageRecord(
                        **common,
                        stage="HARVEST",
                        candidates=tuple(sorted(harvested, key=lambda c: (c.kind, c.value, c.source_module))),
                        module_names=module_names,
                        notes=module_notes,
                        pending_worker_commands=pending_commands,
                    ),
                    WaveStageRecord(
                        **common,
                        stage="ENRICHMENT",
                        candidates=tuple(sorted(enriched, key=lambda c: (c.kind, c.value, c.source_module))),
                        module_names=("deterministic-enrichers",),
                    ),
                    WaveStageRecord(
                        **common,
                        stage="RESOLUTION",
                        candidates=tuple(clustering),
                        derived_seeds=tuple(derived),
                    ),
                )
            )
            wave_candidates.extend(clustering)
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


def _seed_key(seed: SeedInput) -> str:
    return f"{seed.detected_type.value}:{seed.raw_value.lower()}"


def _confidence_dist_from(candidates: list[ObservationCandidate]) -> tuple[tuple[str, int], ...]:
    from .observation_gate import confidence_distribution

    return confidence_distribution(candidates)
