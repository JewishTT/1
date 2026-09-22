"""Zero-layer (Collection Fabric) control-surface API tests.

Exercise ``/api/v1/fabric`` endpoints hermetic: every handler either runs pure
fabric logic (badges, reobservation, modifier, frontier, pools, partition,
throttle) or uses the injected/canned cross-app modules (search, backfill
replay, region backpressure) with no live network or storage.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_ROOT = Path(__file__).resolve().parents[3]
for _rel in ("interpretation", "bulk-ingestion"):
    sys.path.insert(0, str(_ROOT / _rel))

import pytest
from fastapi.testclient import TestClient

from api import routes as api_routes
from api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.unit
class TestFabricEndpoints:
    def test_badge_catalog_and_aliases(self, client: TestClient) -> None:
        resp = client.get("/api/v1/fabric/badges")
        assert resp.status_code == 200
        body = resp.json()
        assert "http" in body["catalog"]
        assert "content-addressed" in body["catalog"]
        assert set(body["engines"]) >= {"http", "browser", "bulk"}
        assert "js-render" in body["aliases"].get("browser", [])

    def test_engines_list_and_get(self, client: TestClient) -> None:
        resp = client.get("/api/v1/fabric/engines")
        assert resp.status_code == 200
        engines = resp.json()["engines"]
        names = {e["engine"] for e in engines}
        assert names >= {"http", "browser", "archival", "bulk"}
        http = next(e for e in engines if e["engine"] == "http")
        assert "etag" in http["badges"]
        assert http["aliases"] != []

        got = client.get("/api/v1/fabric/engines/http")
        assert got.status_code == 200
        assert "etag" in got.json()["badges"]
        assert client.get("/api/v1/fabric/engines/nope").status_code == 404

    def test_engine_select_returns_engine_or_gap(self, client: TestClient) -> None:
        ok = client.post(
            "/api/v1/fabric/engines/select",
            json={"required_badges": ["javascript", "dom"]},
        )
        assert ok.status_code == 200
        assert ok.json()["engine"] == "browser"

        gap = client.post(
            "/api/v1/fabric/engines/select",
            json={"required_capabilities": ["teleport"]},
        )
        assert gap.status_code == 200
        body = gap.json()
        assert body["matched"] is False
        assert "teleport" in body["gap"]["missing"]

    def test_engine_match_and_badge_resolution(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/fabric/engines/match", json={"badges": ["http", "headers"]}
        )
        assert resp.status_code == 200
        names = {m["engine"] for m in resp.json()["matches"]}
        assert "http" in names

        badge = client.post("/api/v1/fabric/tool/badge", json={"token": "js-render"})
        assert badge.status_code == 200
        assert badge.json()["badge"] == "browser"
        assert client.post("/api/v1/fabric/tool/badge", json={"token": "nope"}).status_code == 404

    def test_reobservation_and_etag(self, client: TestClient) -> None:
        changed = client.post(
            "/api/v1/fabric/tool/reobserve",
            json={
                "previous": {"uri": "https://a/x", "digest": "sha1:aaa"},
                "observed": {"uri": "https://a/x", "digest": "sha1:bbb"},
            },
        )
        assert changed.json()["outcome"] == "changed"
        assert changed.json()["refetch_required"] is True

        unchanged = client.post(
            "/api/v1/fabric/tool/reobserve",
            json={"previous": {"etag": 'W/"abc"'}, "observed": {"etag": '"abc"'}},
        )
        assert unchanged.json()["outcome"] == "unchanged"
        assert unchanged.json()["etag_match"] is True

        fresh = client.post(
            "/api/v1/fabric/tool/reobserve",
            json={"observed": {"uri": "https://a/y", "digest": "sha1:ccc"}},
        )
        assert fresh.json()["outcome"] == "created"

        dup = client.post(
            "/api/v1/fabric/tool/reobserve",
            json={"observed": {"uri": "https://a/z", "already_seen": True}},
        )
        assert dup.json()["outcome"] == "duplicate"

        etag = client.post(
            "/api/v1/fabric/tool/etag", json={"left": 'W/"x1"', "right": '"x1"'}
        )
        assert etag.json()["equal"] is True

    def test_modifier_apis(self, client: TestClient) -> None:
        matched = client.post(
            "/api/v1/fabric/modifier/match",
            json={"observed": {"email": "A@X.com"}, "known": {"email": "a@x.com"}},
        )
        assert matched.json()["matched"]["email"] == "a@x.com"

        dedup = client.post(
            "/api/v1/fabric/modifier/dedupe-links",
            json={
                "links": [
                    {"entity": "E1", "identifiers": {"email": "a@x.com"}},
                    {"entity": "E2", "identifiers": {"email": "a@x.com"}},
                    {"entity": "E3", "identifiers": {"phone": "555"}},
                ]
            },
        )
        assert dedup.status_code == 200
        assert any(len(g) == 2 for g in dedup.json()["groups"])
        assert any(len(g) == 1 for g in dedup.json()["groups"])

        urgency = client.post(
            "/api/v1/fabric/modifier/urgency",
            json={
                "entity": "E1",
                "links": [
                    {"entity": "E1", "identifiers": {"email": "a@x.com"}},
                    {"entity": "E2", "identifiers": {"email": "b@x.com"}},
                ],
            },
        )
        assert urgency.json()["urgency"] == "HIGH"
        assert urgency.json()["disposition"] == "CONFLICT"

    def test_cross_semantic_search(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/fabric/search",
            json={
                "query": "wayback cdx",
                "docs": {
                    "d1": "wayback cdx replay of historical warc surfaces",
                    "d2": "nothing in common here",
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["badge"] == "bulk"
        assert body["hits"] and body["hits"][0]["doc_id"] == "d1"

        badge = client.get("/api/v1/fabric/search/badge", params={"q": "parquet read"})
        assert badge.json()["badge"] == "parquet"

    def test_frontier_cycle(self, client: TestClient) -> None:
        uri = "https://fabric-frontier.test/item"
        enq = client.post(
            "/api/v1/fabric/frontier/enqueue",
            json={"items": [{"uri": uri, "priority": 1.0, "partition": "eu-west"}]},
        )
        assert enq.status_code == 200
        dup = client.post(
            "/api/v1/fabric/frontier/enqueue",
            json={"items": [{"uri": uri, "priority": 0.5}]},
        )
        assert dup.json()["duplicates"] == [uri]

        status = client.get("/api/v1/fabric/frontier/status").json()
        assert status["ready"] >= 1

        popped = client.post("/api/v1/fabric/frontier/pop")
        assert popped.status_code == 200
        item = popped.json()
        assert item["uri"] == uri
        assert item["state"] == "LEASED"
        assert item["partition"] == "eu-west"

        done = client.post(f"/api/v1/fabric/frontier/{item['frontier_id']}/complete")
        assert done.status_code == 200
        assert done.json()["state"] == "DONE"
        assert client.get("/api/v1/fabric/frontier/status").json()["by_state"]["DONE"] >= 1

    def test_worker_pools(self, client: TestClient) -> None:
        pools = client.get("/api/v1/fabric/pools").json()["pools"]
        kinds = {p["kind"] for p in pools}
        assert kinds == {"http", "browser", "document", "ocr", "vision", "tda"}
        fail = client.post("/api/v1/fabric/pools/browser/fail")
        assert fail.status_code == 200
        assert fail.json()["kind"] == "browser"
        after = client.get("/api/v1/fabric/pools").json()["pools"]
        browser = next(p for p in after if p["kind"] == "browser")
        assert browser["failures"] >= 1

    def test_partition_resolution(self, client: TestClient) -> None:
        global_part = client.post(
            "/api/v1/fabric/partitions/resolve",
            json={"uri": "https://news.example.com/story"},
        ).json()
        assert global_part["host"] == "news.example.com"
        assert global_part["partition"] == "global"

        regional = client.post(
            "/api/v1/fabric/partitions/resolve",
            json={"uri": "https://news.wire.ru/story", "region_map": {".ru": "ru"}},
        ).json()
        assert regional["partition"] == "ru"
        assert regional["sample_id"].startswith("obs.ru.")

    def test_region_backpressure_verdicts(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        # Load the real RegionBackpressure rules by file (no `dispatcher`/`adapters`
        # import) so this control-plane suite never makes `adapters` importable.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "dispatcher_regional", str(_ROOT / "acquisition" / "dispatcher" / "regional.py")
        )
        region_module = importlib.util.module_from_spec(spec)
        sys.modules["dispatcher_regional"] = region_module
        spec.loader.exec_module(region_module)  # type: ignore[union-attr]
        original = api_routes.fabric._lazy
        monkeypatch.setattr(
            api_routes.fabric,
            "_lazy",
            lambda name: (region_module, None) if name == "dispatcher.regional" else original(name),
        )

        go = client.post(
            "/api/v1/fabric/backpressure/verdict",
            json={"region": "eu-1", "ready_depth": 1, "in_flight": 0, "capacity": 4},
        )
        assert go.json()["verdict"] == "go"

        throttle = client.post(
            "/api/v1/fabric/backpressure/verdict",
            json={"region": "eu-2", "ready_depth": 5, "in_flight": 0, "capacity": 4},
        )
        assert throttle.json()["verdict"] == "throttle"

        halt = client.post(
            "/api/v1/fabric/backpressure/verdict",
            json={
                "region": "us-1",
                "ready_depth": 1,
                "in_flight": 0,
                "capacity": 4,
                "oldest_age_s": 999,
            },
        )
        assert halt.json()["verdict"] == "halt"
        assert client.get("/api/v1/fabric/frontier/status").status_code == 200

    def test_backpressure_501_when_acquisition_absent(self, client: TestClient) -> None:
        import sys

        if str(_ROOT / "acquisition") in sys.path:
            pytest.skip("acquisition source dir present on sys.path")
        resp = client.post(
            "/api/v1/fabric/backpressure/verdict",
            json={"region": "eu-3", "ready_depth": 1, "in_flight": 0, "capacity": 4},
        )
        assert resp.status_code == 501

    def test_throttle_rate(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/fabric/throttle/rate",
            json={"queue_depth": 10_000, "max_rate_per_s": 10.0, "downstream_lag_s": 120.0},
        )
        assert resp.json()["effective_rate_per_s"] == 0.0
        assert resp.json()["lag_scale"] == 0.0

    def test_bulk_backfill_plan_and_cdx(self, client: TestClient) -> None:
        plan = client.post(
            "/api/v1/fabric/bulk/plan",
            json={
                "cc_prefixes": ["s3://commoncrawl/sample/*"],
                "domains": ["example.com"],
            },
        )
        assert plan.status_code == 200
        assert plan.json()["sources"] == 2
        assert plan.json()["cdx_urls"][0].startswith("https://web.archive.org/cdx")

        cdx = client.get(
            "/api/v1/fabric/bulk/cdx",
            params={"domain": "example.com", "from_ts": "20230101"},
        )
        assert cdx.status_code == 200
        assert "from=20230101" in cdx.json()["url"]

    def test_bulk_replay_hermetic(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/fabric/bulk/replay",
            json={
                "plan": {"cc_prefixes": ["s3://commoncrawl/sample/*"]},
                "cc_hits": {
                    "s3://commoncrawl/sample/*": [
                        {
                            "url": "http://a.example/x",
                            "timestamp": "20230101000000",
                            "offset": "0",
                        },
                        {
                            "url": "http://b.example/x",
                            "timestamp": "20230101000000",
                            "offset": "1",
                        },
                    ]
                },
            },
        )
        assert resp.status_code == 200
        stats = resp.json()["stats"]
        assert stats["discovered"] == 2
        assert stats["enqueued"] == 2
        assert len(resp.json()["enqueued_uris"]) == 2