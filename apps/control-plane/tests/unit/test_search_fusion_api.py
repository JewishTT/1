"""The fusion strategy is reachable over HTTP, not only in-process (T004, D6).

`QueryPlanner` gained a rank-fusion strategy, but a strategy a caller cannot name
is not a feature -- it is a code path reachable only from a unit test. These
tests go through the real router with the real tenant dependency, because the
things that break at this boundary are not the ones that break inside the
planner:

* the query parameter has to survive FastAPI's validation,
* an unrecognised strategy has to be a 422 and not a 500. Reporting a caller's
  typo as a server fault inverts blame and, worse, a 500 here would land in the
  degraded-backend machinery, so the caller is told a backend broke when nothing
  did.
* `score-weighted` must remain the default, or this silently reorders every
  existing caller's results.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import search as search_routes
from services.query_planner import RANK_FUSION, SCORE_WEIGHTED, BackendHit, QueryPlanner

HEADERS = {"X-Tenant-ID": "t-1"}


class StubBackend:
    def __init__(self, hits: list[BackendHit]) -> None:
        self.hits = list(hits)

    async def search(self, text, filters, limit: int = 20) -> list[BackendHit]:
        return list(self.hits[:limit])


@pytest.fixture
def planner(monkeypatch):
    """Two backends that disagree about order, so fusion has something to fuse."""

    def _build(tenant_id: str):
        return QueryPlanner(
            {
                "search": StubBackend(
                    [
                        BackendHit(doc_id="a", score=0.9, observation_id="OBS-1"),
                        BackendHit(doc_id="b", score=0.1),
                    ]
                ),
                "graph": StubBackend(
                    [
                        BackendHit(doc_id="b", score=0.4),
                        BackendHit(doc_id="a", score=0.2),
                    ]
                ),
            },
            {"OBS-1": {"observation_id": "OBS-1", "uri": "http://f.local/a", "content_hash": "sha256:aa"}},
        )

    monkeypatch.setattr(search_routes, "build_query_planner", _build)
    return TestClient(app)


class TestStrategyIsReachable:
    def test_get_accepts_rank_fusion(self, planner):
        r = planner.get("/api/v1/search", params={"q": "x", "fusion": RANK_FUSION}, headers=HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["results"], "rank fusion returned nothing to rank"
        assert body["results"][0]["fusion"] == RANK_FUSION

    def test_get_still_defaults_to_score_weighted(self, planner):
        r = planner.get("/api/v1/search", params={"q": "x"}, headers=HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["results"][0]["fusion"] == SCORE_WEIGHTED

    def test_post_accepts_rank_fusion(self, planner):
        r = planner.post(
            "/api/v1/search",
            json={"query": "x", "fusion": RANK_FUSION},
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
        assert r.json()["results"][0]["fusion"] == RANK_FUSION

    def test_rank_fusion_carries_its_attribution_to_the_client(self, planner):
        r = planner.get("/api/v1/search", params={"q": "x", "fusion": RANK_FUSION}, headers=HEADERS)
        top = r.json()["results"][0]
        assert top["fusion_policy_fingerprint"].startswith("sha256:")
        assert set(top["per_ranker_ranks"]) == {"search", "graph"}
        # Absence is recorded as null, never padded to a trailing rank.
        assert None in top["per_ranker_ranks"].values() or top["fused_rank"] == 1


class TestTyposAreTheCallersFault:
    def test_an_unknown_strategy_is_422_not_500(self, planner):
        r = planner.get("/api/v1/search", params={"q": "x", "fusion": "vibes"}, headers=HEADERS)
        assert r.status_code == 422, r.text
        # And specifically not an outage: nothing failed, so nothing may claim to.
        assert "degraded_backends" not in r.json()