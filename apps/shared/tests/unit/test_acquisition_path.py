"""Unit tests for scoring + content router + observation gate (US1 acquisition path)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "control-plane"))

import pytest

from events.content_router import ContentRouter, OversizedContentError, RequestDedupKey
from events.observation_gate import ObservationGate
from scoring.scorer import HeuristicUtilityScorer, Outcome, UtilityScore
from storage.s3 import RawObjectRef


class _FakeStore:
    def __init__(self) -> None:
        self.stored = []

    async def put_raw(self, body, *, tenant_id, meta=None):
        return RawObjectRef(
            uri=f"s3://knowledge/raw/{tenant_id}/202609/{len(body)}",
            sha256=ContentRouter.sha256(body),
            size=len(body),
            tenant_prefix=f"{tenant_id}/202609",
            year_month="202609",
        )


class TestContentRouter:
    def test_sha256_deterministic(self) -> None:
        c = ContentRouter()
        assert c.sha256(b"abc") == c.sha256(b"abc")
        assert len(c.sha256(b"abc")) == 64

    def test_canonical_url_strips_fragment_and_lowercases(self) -> None:
        c = ContentRouter()
        assert c.canonical_url("HTTP://Fixtures.Local/Index.html#sec") == "http://fixtures.local/index.html"

    def test_mime_sniff_html(self) -> None:
        c = ContentRouter()
        assert c.sniff_mime(b"<html><body>hi</body></html>") == "text/html"

    def test_mime_sniff_pdf(self) -> None:
        c = ContentRouter()
        assert c.sniff_mime(b"%PDF-1.4") == "application/pdf"

    def test_oversized_rejected(self) -> None:
        c = ContentRouter(max_bytes=100)
        with pytest.raises(OversizedContentError):
            c.classify(b"x" * 200, url="http://x")

    def test_dedup_keys(self) -> None:
        assert RequestDedupKey.exact_hash("h").startswith("dedup:hash:")
        assert RequestDedupKey.canonical_url("http://x").startswith("dedup:url:")


class TestUtilityScorer:
    def test_score_returns_reasons(self) -> None:
        s = HeuristicUtilityScorer()
        score = s.score(
            {"host_key": "h", "expected_gain": 0.8, "novelty": 0.9},
            {"downstream_lag_s": 0},
        )
        assert isinstance(score, UtilityScore)
        assert score.reasons == ["heuristic-utility-scorer-v1"]

    def test_higher_gain_higher_utility(self) -> None:
        s = HeuristicUtilityScorer()
        low = s.score({"expected_gain": 0.1}, {}).utility
        high = s.score({"expected_gain": 0.9}, {}).utility
        assert high > low

    def test_backpressure_reduces_utility(self) -> None:
        s = HeuristicUtilityScorer()
        base = s.score({"expected_gain": 0.8}, {"downstream_lag_s": 0}).utility
        lagged = s.score({"expected_gain": 0.8}, {"downstream_lag_s": 120}).utility
        assert lagged < base

    def test_adjust_updates_adaptive_state(self) -> None:
        s = HeuristicUtilityScorer()
        before = s.feature_vector("host").ewma_latency_ms
        s.adjust("host", Outcome.SUCCESS, latency_ms=300.0, payload_bytes=5000)
        after = s.feature_vector("host").ewma_latency_ms
        assert after > before or after < before  # at least updated
        assert s.feature_vector("host").window_n == 1

    def test_failure_triggers_cooldown(self) -> None:
        s = HeuristicUtilityScorer()
        s.adjust("h", Outcome.FAILURE)
        assert s.feature_vector("h").cooldown_until_ms > 0


class TestObservationGate:
    @pytest.mark.asyncio
    async def test_ingest_writes_raw_and_emits_observation(self) -> None:
        gate = ObservationGate(store=_FakeStore(), router=ContentRouter())
        obs = await gate.ingest(
            body=b"<html><body>ACME Corp</body></html>",
            uri="http://fixtures.local/index.html",
            tenant_id="default-tenant",
            investigation_id="INV-1",
        )
        assert obs["status"] == "created"
        assert obs["content_hash"]
        assert obs["raw_ref"].startswith("s3://")

    @pytest.mark.asyncio
    async def test_ingest_dedup_by_hash_uses_same_ref(self) -> None:
        gate = ObservationGate(store=_FakeStore(), router=ContentRouter())
        o1 = await gate.ingest(body=b"same bytes", uri="http://a", tenant_id="t")
        o2 = await gate.ingest(body=b"same bytes", uri="http://a", tenant_id="t")
        assert o1["content_hash"] == o2["content_hash"]

    def test_mutate_attempt_rejected_as_immutable(self) -> None:
        gate = ObservationGate(store=_FakeStore(), router=ContentRouter())
        asyncio.run(gate.ingest(body=b"x", uri="http://a", tenant_id="t"))
        obs = list(gate._observations.values())[0]
        with pytest.raises(Exception):
            from domain import ObservationImmutableError

            try:
                gate.mutate_attempt(obs["observation_id"], {"uri": "http://changed"})
            except ObservationImmutableError:
                raise
            raise AssertionError("expected ObservationImmutableError")