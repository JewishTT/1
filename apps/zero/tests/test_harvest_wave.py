"""Unit tests for wave orchestration + observation gate (spec/010 FR-012, FR-009)."""

from __future__ import annotations

import pytest

from zero.harvest_wave import HarvestWave, WaveSummary
from zero.harvesters.registry import HarvesterRegistry
from zero.harvesters.transport import DictTransport
from zero.observation_gate import ZeroLayerGate, confidence_distribution
from zero.type_detector import TypeDetector


class _RecordingProducer:
    """Captures (topic, key) for emission assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def produce(self, topic: str, envelope, key: str = "") -> None:
        self.calls.append((topic, key))


class _MemoryStore:
    def __init__(self) -> None:
        self.items: list[tuple[bytes, str]] = []

    def put_raw_dedup(self, body: bytes, *, tenant_id: str, meta: dict | None = None) -> None:
        self.items.append((body, tenant_id))


class TestHarvestWaveStabilization:
    def _html(self) -> str:
        return (
            "<html><body>"
            "<p>contact alice@corp.co or +12025550199</p>"
            '<a href="https://github.com/octocat">g</a>'
            '<a href="https://blog.example.org">b</a>'
            "</body></html>"
        )

    def _wave(self, max_depth: int = 3, min_new_seeds: int = 1) -> HarvestWave:
        registry = HarvesterRegistry()
        registry.register_all()
        transport = DictTransport(bodies={"https://corp.co/team": self._html()})
        return HarvestWave(
            detector=TypeDetector(),
            registry=registry,
            transport=transport,
            max_depth=max_depth,
            min_new_seeds=min_new_seeds,
        )

    def test_stabilizes_before_max_depth(self) -> None:
        wave = self._wave(max_depth=3, min_new_seeds=1)
        summaries = wave.run(["https://corp.co/team"])
        assert summaries, "at least one wave ran"
        assert summaries[-1].stabilized is True
        assert all(isinstance(s, WaveSummary) for s in summaries)

    def test_first_wave_discovers_contacts(self) -> None:
        wave = self._wave()
        summaries = wave.run(["https://corp.co/team"])
        first = summaries[0]
        assert first.seeds_in == 1
        assert first.contacts_out >= 3  # email + phone + linked domain

    def test_max_depth_one_stops(self) -> None:
        wave = self._wave(max_depth=1)
        summaries = wave.run(["https://corp.co/team"])
        assert len(summaries) == 1
        # with depth 1 we never look at feedback, so no stabilization flag is set
        assert summaries[0].stabilized is False

    def test_min_new_seeds_high_stabilizes_early(self) -> None:
        wave = self._wave(max_depth=3, min_new_seeds=100)
        summaries = wave.run(["https://corp.co/team"])
        assert len(summaries) == 1
        assert summaries[0].stabilized is True

    def test_deterministic_across_runs(self) -> None:
        first = [s.as_dict() for s in self._wave().run(["https://corp.co/team"])]
        second = [s.as_dict() for s in self._wave().run(["https://corp.co/team"])]
        assert first == second

    def test_multiple_seeds_parallel_sorted(self) -> None:
        wave = self._wave(max_depth=1)
        summaries = wave.run(["https://corp.co/team", "alice@corp.co", "bob clue"])
        assert summaries[0].seeds_in == 3

    def test_confidence_distribution_in_summary(self) -> None:
        wave = self._wave()
        summary = wave.run(["https://corp.co/team"])[0]
        dist = dict(summary.confidence_dist)
        assert sum(dist.values()) == summary.contacts_out


class TestObservationGate:
    def test_emit_produces_immutable_observation(self) -> None:
        producer = _RecordingProducer()
        store = _MemoryStore()
        gate = ZeroLayerGate(producer=producer, store=store)
        seed = TypeDetector().detect("acme.com")

        from zero.harvesters.contracts import ObservationCandidate
        from zero.harvesters.domain import role_addresses

        candidates = [
            ObservationCandidate(email, "email", 0.45, "email_permutation", "role")
            for email, _ in role_addresses("acme.com")
        ]
        obs = gate.emit(seed=seed, candidates=candidates, derived_seeds=[])
        assert obs.observation_id.startswith("ZERO-OBS-")
        assert obs.seed_id == seed.seed_id
        assert obs.confidence_dist[2][1] == 0  # nobody above 0.9

        topics = [t for t, _ in producer.calls]
        # emit() publishes seed_detected + observation; both go to the "zero_layer" topic
        assert topics.count("zero_layer") == 2

    def test_emitted_observation_is_content_addressed(self) -> None:
        gate = ZeroLayerGate()
        seed = TypeDetector().detect("alice@example.com")
        obs_a = gate.emit(seed=seed, candidates=[], derived_seeds=[])
        obs_b = gate.emit(seed=seed, candidates=[], derived_seeds=[])
        assert obs_a.content_digest == obs_b.content_digest
        assert obs_a.observation_id != obs_b.observation_id  # new immutable record

    def test_immutability_enforcement(self) -> None:
        gate = ZeroLayerGate()
        obs = gate.emit(seed=TypeDetector().detect("bob@x.co"), candidates=[], derived_seeds=[])
        with pytest.raises(ValueError):
            ZeroLayerGate.assert_immutable(obs, {"seed_value", "content_digest"})
        # unrelated field is fine
        ZeroLayerGate.assert_immutable(obs, {"candidate", "metadata"})

    def test_emit_cycle_metrics(self) -> None:
        producer = _RecordingProducer()
        gate = ZeroLayerGate(producer=producer)
        gate.emit_cycle(
            seeds_in=2,
            contacts_out=10,
            new_seeds_discovered=3,
            confidence_dist=(("0.5-0.7", 6), ("0.7-0.9", 4), ("0.9-1.0", 0)),
        )
        assert any(t == "zero_layer" for t, _ in producer.calls)


class TestConfidenceDistribution:
    def test_bins(self) -> None:
        from zero.harvesters.contracts import ObservationCandidate

        candidates = [
            ObservationCandidate("a", "email", 0.55, "m", "x"),
            ObservationCandidate("b", "email", 0.75, "m", "x"),
            ObservationCandidate("c", "email", 0.95, "m", "x"),
            ObservationCandidate("d", "email", 0.30, "m", "x"),
        ]
        dist = dict(confidence_distribution(candidates))
        assert dist == {"0.5-0.7": 1, "0.7-0.9": 1, "0.9-1.0": 1}


class TestFullPipelineIntegration:
    def test_single_seed_to_observation(self) -> None:
        registry = HarvesterRegistry()
        registry.register_all()
        producer = _RecordingProducer()
        gate = ZeroLayerGate(producer=producer, store=_MemoryStore())
        wave = HarvestWave(
            detector=TypeDetector(),
            registry=registry,
            gate=gate,
            transport=DictTransport(
                bodies={
                    "https://acme.com/contact": (
                        "<html><body>mailto:sales@acme.com</body></html>"
                    )
                }
            ),
            max_depth=2,
        )
        summaries = wave.run(["https://acme.com/contact"])
        assert summaries[0].contacts_out >= 1
        observations = gate.observations()
        assert observations
        assert all(o.content_digest for o in observations)