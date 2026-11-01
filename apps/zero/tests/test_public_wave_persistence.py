"""The public harvest wave persists raw pages before discovery-only stage outputs."""

from __future__ import annotations

from urllib.parse import urlsplit

from zero.enrichment.feedback import FeedbackLoop
from zero.harvest_wave import HarvestWave
from zero.harvesters.public_document import PublicDocumentHarvester
from zero.harvesters.registry import HarvesterRegistry
from zero.harvesters.transport import SecurePublicTransport
from zero.type_detector import TypeDetector
from zero.public_policy import allow_public_candidate


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
        self.root_page = b"""<html><head><title>Public Office</title></head>
        <body><a href="/official">Official profile</a>
        <a href="https://outside.example.net/exit">outside</a></body></html>"""
        self.child_page = b"""<html><head><title>Public Office Holder</title>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Person","name":"Example","jobTitle":"Public Director"}
        </script></head><body><h1>Example</h1></body></html>"""

    async def fetch(self, url: str, *, headers=None):
        if url.endswith("/robots.txt"):
            return _Response(url, b"User-agent: *\nAllow: /\n", "text/plain")
        if url.endswith("/about"):
            return _Response(url, self.root_page)
        return _Response(url, self.child_page)

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
        page_name = urlsplit(capture.url).path.strip("/").replace("/", "-")
        return SimpleNamespace(observation_id=f"OBS-RAW-{page_name}")

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
        max_depth=2,
        min_new_seeds=1,
        enable_enrichment=False,
        feedback=FeedbackLoop(kinds=frozenset({"public_page_link"})),
        candidate_allowed=allow_public_candidate,
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
    assert summaries[0].new_seeds_discovered == 1, (
        f"root wave candidates: {[(record.stage, [(item.kind, item.value) for item in record.candidates]) for record in wave.stage_records if record.seed_value == url]}; "
        f"transport failures: {transport.failures}; requests: {transport.requests_used}; "
        f"captures: {[capture.url for capture in transport.captures]}"
    )
    assert sink.order[:2] == ["raw_capture", "raw_capture"]
    assert len(sink.captures) == 2
    assert sink.captures[0][0].url.endswith("/about")
    assert sink.captures[1][0].url.endswith("/official")
    assert all(capture.parent_observation_id == "OBS-searxng-parent" for capture, *_ in sink.captures)
    assert sink.records
    root_records = [record for record, *_ in sink.records if record.seed_value == url]
    assert len(root_records) == 3
    assert all(record.as_dict()["parent_observation_id"] == "OBS-RAW-about" for record in root_records)
    assert all(record.as_dict()["discovery_observation_id"] == "OBS-searxng-parent" for record, *_ in sink.records)
    assert all(record.as_dict()["result_role"] == "DISCOVERY_ONLY" for record, *_ in sink.records)
    assert all(record.as_dict()["claim_admission_allowed"] is False for record, *_ in sink.records)
    assert all(record.as_dict()["source_id"] == "searxng_public_search" for record, *_ in sink.records)
    child_records = [record for record, *_ in sink.records if record.seed_value.endswith("/official")]
    assert len(child_records) == 3
    assert all(record.parent_observation_id == "OBS-RAW-official" for record in child_records)
    assert all(record.discovery_parent_observation_id == "OBS-RAW-about" for record in child_records)
    assert all(record.discovery_observation_id == "OBS-searxng-parent" for record in child_records)
    assert all(record.parent_capture_url.endswith("/about") for record in child_records)
    assert len(sink.captures) == 2
