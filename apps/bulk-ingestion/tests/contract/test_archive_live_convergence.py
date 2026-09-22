"""Contract: bulk archive replay and live ingestion converge (T122).

The same URL+payload arriving through the historical replay path (WARC adapter
over an archived range) and through a live acquisition run must land on the
same content-addressed raw object and the same URI -> the second path classifies
``duplicate`` (R-08), proving identity is content, not provenance (I-1).
"""

from __future__ import annotations

import io
import socket
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "acquisition"))

import pytest
from adapters.scrapy.stream import scrapy_crawl
from adapters.warc.collect import adapt_warc
from events.content_router import ContentRouter
from events.observation_gate import ObservationGate
from storage.s3 import ObjectStore
from warcio import WARCWriter
from warcio.statusandheaders import StatusAndHeaders

from historical.replay import MemoryFrontierSink

pytestmark = pytest.mark.contract

_MINIO_PORT = 9000


def _minio_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", _MINIO_PORT), timeout=3):
            return True
    except OSError:
        return False


pytestmark = [pytestmark, pytest.mark.skipif(not _minio_reachable(), reason="minio unavailable")]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Site:
    def __init__(self, files: dict[str, bytes]) -> None:
        self._dir = Path(Path.home() / "_site_tmp")
        self._dir.mkdir(exist_ok=True)
        for name, body in files.items():
            (self._dir / name).write_bytes(body)
        handler = lambda *a, **k: SimpleHTTPRequestHandler(
            *a, directory=str(self._dir), **k
        )
        self._server = ThreadingHTTPServer(("127.0.0.1", _free_port()), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.base = f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()


def _warc_bytes(url: str, body: bytes) -> bytes:
    buf = io.BytesIO()
    writer = WARCWriter(buf, gzip=False)
    writer.write_record(
        writer.create_warc_record(
            url,
            "response",
            payload=io.BytesIO(body),
            http_headers=StatusAndHeaders(
                "HTTP/1.1 200 OK",
                [("Content-Type", "text/html"), ("Content-Length", str(len(body)))],
                protocol="HTTP/1.1",
            ),
        )
    )
    return buf.getvalue()


def _tenant() -> str:
    import uuid

    return "ten-bulk-" + uuid.uuid4().hex[:6]


async def test_archive_replay_converges_with_live_ingestion() -> None:
    body = b"<html><title>converge</title><a href='about.html'>about</a></html>"
    about = b"<html><title>about</title></html>"
    site = _Site({"index.html": body, "about.html": about})
    try:
        store = ObjectStore()
        gate = ObservationGate(store, ContentRouter(), producer=None)
        tenant = _tenant()

        # Live path: scrapy exemplar fetches index.html (and follows the link).
        live = await scrapy_crawl(
            {
                "task_id": "T-BULK-LIVE-1",
                "tenant_id": tenant,
                "seed_urls": [site.base + "/index.html"],
                "observation_gate": gate,
            }
        )
        live_index = next(o for o in live["observations"] if o["uri"] == site.base + "/index.html")
        assert live_index["status"] == "created"

        # Archive path: a replay sink receives the archived WARC range candidate
        # (as Common Crawl CDX would emit it) and the WARC adapter observes it.
        warc = _warc_bytes(site.base + "/index.html", body)
        ref, _existed = await store.put_raw_dedup(warc, tenant_id=tenant)
        candidate = {"uri": f"{ref.uri}?offset=0&length={len(warc)}"}
        sink = MemoryFrontierSink()
        assert sink.enqueue(candidate) is True

        archived = await adapt_warc(
            {
                "task_id": "T-BULK-ARCH-1",
                "tenant_id": tenant,
                "warc_uri": candidate["uri"],
                "object_store": store,
                "observation_gate": gate,
            }
        )
        archive_index = archived["observations"][0]

        assert archive_index["uri"] == live_index["uri"]
        assert archive_index["status"] == "duplicate"
        assert archive_index["raw_ref"] == live_index["raw_ref"]
    finally:
        site.close()


async def test_distinct_payload_same_uri_does_not_collapse() -> None:
    body = b"<html><title>v1</title></html>"
    changed = b"<html><title>v2</title></html>"
    site = _Site({"index.html": body})
    try:
        store = ObjectStore()
        gate = ObservationGate(store, ContentRouter(), producer=None)
        tenant = _tenant()

        live = await scrapy_crawl(
            {
                "task_id": "T-BULK-LIVE-2",
                "tenant_id": tenant,
                "seed_urls": [site.base + "/index.html"],
                "observation_gate": gate,
            }
        )
        first = next(o for o in live["observations"] if o["uri"] == site.base + "/index.html")

        warc = _warc_bytes(site.base + "/index.html", changed)
        ref, _existed = await store.put_raw_dedup(warc, tenant_id=tenant)
        archived = await adapt_warc(
            {
                "task_id": "T-BULK-ARCH-2",
                "tenant_id": tenant,
                "warc_uri": f"{ref.uri}?offset=0&length={len(warc)}",
                "object_store": store,
                "observation_gate": gate,
            }
        )
        second = archived["observations"][0]

        assert second["uri"] == first["uri"]
        assert second["status"] == "created"
        assert second["raw_ref"] != first["raw_ref"]
    finally:
        site.close()