"""The public harvest wave persists raw pages before discovery-only stage outputs."""

from __future__ import annotations

from zero.harvest_wave import HarvestWave
from zero.harvesters.public_document import PublicDocumentHarvester
from zero.harvesters.registry import HarvesterRegistry
from zero.harvesters.transport import SecurePublicTransport
from zero.type_detector import TypeDetector


class _Response:
    def __init__(self, url: str, body: bytes, content_type: str = "text/html") -> None:
        self.url = url
        self.status = 200
        self.body = body
        self.content_type = content_type
        self.pinned_ip = "93.184.216.34"
        self.redirects = ()


class _Fetcher:
    def __init__(self) -> None:
        self.page = b"""
        <html><head><title>Public Office</title>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Person","name":"Example","jobTitle":"Public Director"}
        </script></head><body><h1>Example</h1></body></html>
        """

    async def fetch(self, url: str, *, headers=None):
        if url.endswith("/robots.txt"):
            return _Response(url, b"User-agent: *\nAllow: /\n", "text/plain")
        return _Response(url, self.page)

    async def aclose(self) -> None:
        return None


class _RecordingEvidenceSink:
    def __init__(self) -> None:
        self.order: list[str] = []
        self.captures = []
        self.records = []

    async def persist_capture(self, capture, *, tenant_id: str, investigation_id: str | None):
        from types import SimpleNamespace

        self.order.append("raw_capture")
        self.captures.append((capture, tenant_id, investigation_id))
        return SimpleNamespace(observation_id="OBS-RAW-PAGE")

    async def persist(self, record, *, tenant_id: str, investigation_id: str | None):
        self.order.append("stage_observation")
        self.records.append((record, tenant_id, investigation_id))
        return record


async def test_wave_persists_capture_first_then_discovery_only_stages() -> None:
    url = "https://example.org/about"
    registry = HarvesterRegistry()
    registry.register(PublicDocumentHarvester())
    transport = SecurePublicTransport(
        fetcher_factory=lambda **_kwargs: _Fetcher(),
        minimum_host_interval_s=0,
    )
    transport.set_source_metadata(
        url,
        parent_observation_id="OBS-searxng-parent",
        discovery_source_id="searxng_public_search",
        action_ref="ACT-public-discovery",
    )
    wave = HarvestWave(
        detector=TypeDetector(),
        registry=registry,
        transport=transport,
        max_depth=1,
        min_new_seeds=0,
        enable_enrichment=False,
        seed_context={
            url: {
                "discovery_observation_id": "OBS-searxng-parent",
                "source_id": "searxng_public_search",
            }
        },
    )
    sink = _RecordingEvidenceSink()

    summaries, accepted = await wave.run_and_persist(
        [url],
        evidence_sink=sink,
        tenant_id="tenant-1",
        investigation_id="INV-1",
    )

    assert summaries and accepted
    assert sink.order[0] == "raw_capture"
    assert sink.captures[0][0].parent_observation_id == "OBS-searxng-parent"
    assert sink.records
    assert all(record.as_dict()["parent_observation_id"] == "OBS-RAW-PAGE" for record, *_ in sink.records)
    assert all(record.as_dict()["discovery_observation_id"] == "OBS-searxng-parent" for record, *_ in sink.records)
    assert all(record.as_dict()["result_role"] == "DISCOVERY_ONLY" for record, *_ in sink.records)
    assert all(record.as_dict()["claim_admission_allowed"] is False for record, *_ in sink.records)
    assert all(record.as_dict()["source_id"] == "searxng_public_search" for record, *_ in sink.records)
    assert len(sink.captures) == 1
