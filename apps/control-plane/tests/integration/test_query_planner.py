"""Integration test: hybrid query fusion returns evidence-linked results (T048).

Indexes a fixture corpus into the hermetic search backends, runs hybrid queries
with temporal/source/investigation filters, and asserts that fused results
resolve their evidence chain to immutable observations (I-1).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from services.query_planner import (
    BackendHit,
    MemoryBackend,
    QueryFilters,
    QueryPlanner,
)

OBSERVATIONS = {
    "OBS-1001": {"observation_id": "OBS-1001", "uri": "http://fixtures.local/report.html", "content_hash": "sha256:aa"},
    "OBS-1002": {"observation_id": "OBS-1002", "uri": "http://fixtures.local/ledger.html", "content_hash": "sha256:bb"},
    "OBS-1003": {"observation_id": "OBS-1003", "uri": "http://fixtures.local/weather.html", "content_hash": "sha256:cc"},
}

DOCS = [
    BackendHit(doc_id="OBS-1001", kind="observation", score=0.9, observation_id="OBS-1001", source_id="src-a",
               payload={"text": "Yard account transfers detected", "investigation_id": "INV-1"}),
    BackendHit(doc_id="ENT-2001", kind="entity", score=0.7, observation_id="OBS-1001", source_id="src-a",
               payload={"text": "suspicious account Yard", "investigation_id": "INV-1"}),
    BackendHit(doc_id="DOC-3001", kind="document", score=0.4, observation_id="OBS-1002", source_id="src-a",
               payload={"text": "ledger reconciliation for Yard", "investigation_id": "INV-1"}),
    BackendHit(doc_id="DOC-3002", kind="document", score=0.3, observation_id="OBS-1003", source_id="src-b",
               payload={"text": "daily weather bulletin", "investigation_id": "INV-1"}),
]


@pytest.fixture
def planner() -> QueryPlanner:
    return QueryPlanner(
        backends={
            "opensearch": MemoryBackend("opensearch", DOCS),
            "graph": MemoryBackend("graph", [DOCS[1]]),
            "clickhouse": MemoryBackend("clickhouse", [DOCS[0], DOCS[2]]),
        },
        observations=OBSERVATIONS,
    )


@pytest.mark.integration
class TestHybridFusion:
    async def test_fuses_backends_into_single_surface(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Yard")
        results = await planner.execute(plan)
        doc_ids = {r.doc_id for r in results}
        assert "OBS-1001" in doc_ids
        assert "ENT-2001" in doc_ids
        # Every result must carry an evidence chain.
        assert all(r.evidence for r in results)

    async def test_evidence_resolves_to_immutable_observations(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Yard")
        results = await planner.execute(plan)
        for result in results:
            for link in result.evidence:
                obs = link["observation"]
                assert obs["immutable"] is True  # I-1
                assert obs["uri"] in {o["uri"] for o in OBSERVATIONS.values()}

    async def test_source_filter_restricts_corpus(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Yard", filters=QueryFilters(source_ids=frozenset({"src-b"})))
        results = await planner.execute(plan)
        assert results == []  # src-b corpus is the weather bulletin, no "Yard"

    async def test_investigation_filter(self, planner: QueryPlanner) -> None:
        plan = planner.plan(
            "Yard",
            filters=QueryFilters(investigation_id="INV-1"),
        )
        results = await planner.execute(plan)
        assert results  # corpus is scoped to INV-1, so matches survive

    async def test_fused_score_is_bounded_and_ranked(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Yard")
        results = await planner.execute(plan)
        scores = [r.score for r in results]
        assert all(0.0 <= s <= 1.0 for s in scores)
        assert scores == sorted(scores, reverse=True)