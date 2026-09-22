"""Integration: Wave 3 adapters push bytes through the single real gate (T096/T092/T093/T094).

Every adapter run lands in content-addressed MinIO via ObservationGate; statuses
follow the R-08 lifecycle; identity/dedup is proven by a second identical run.
"""

from __future__ import annotations

import importlib
import io
import json
import socket
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

import httpx
import pytest
from adapters.commoncrawl.index import discover
from adapters.scrapy.stream import scrapy_crawl
from adapters.warc.collect import adapt_warc
from events.content_router import ContentRouter
from events.observation_gate import ObservationGate
from storage.s3 import ObjectStore
from warcio import WARCWriter
from warcio.statusandheaders import StatusAndHeaders

worker_dataset = importlib.import_module("worker-dataset")

pytestmark = pytest.mark.integration

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
        (self._dir / "index.html").write_bytes(files["index.html"])
        (self._dir / "about.html").write_bytes(files["about.html"])
        handler = lambda *a, **k: SimpleHTTPRequestHandler(  # noqa: E731
            *a, directory=str(self._dir), **k
        )
        self._server = ThreadingHTTPServer(("127.0.0.1", _free_port()), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.base = f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()


def _warc_bytes(
    url: str = "https://collect.example/page", body: bytes = b"<html>warc fixture</html>"
) -> bytes:
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


def _gate() -> ObservationGate:
    return ObservationGate(ObjectStore(), ContentRouter(), producer=None)


def _tenant() -> str:
    import uuid

    return "ten-ad-" + uuid.uuid4().hex[:6]


async def test_scrapy_exemplar_collects_pages_through_gate() -> None:
    site = _Site(
        {
            "index.html": b"<html><title>home</title>"
              b"<body><a href='about.html'>about</a></body></html>",
            "about.html": b"<html><title>about us</title></html>",
        }
    )
    try:
        gate = _gate()
        result = await scrapy_crawl(
            {
                "task_id": "T-SCR-1",
                "tenant_id": _tenant(),
                "seed_urls": [site.base + "/index.html"],
                "observation_gate": gate,
            }
        )
        assert result["observed"] >= 2
        assert all(o["status"] == "created" for o in result["observations"])
        assert all("/raw/ten-ad-" in o["raw_ref"] for o in result["observations"])
    finally:
        site.close()


async def test_scrapy_exemplar_second_run_dedups_by_content() -> None:
    site = _Site(
        {
            "index.html": b"<html><title>stable</title><a href='about.html'>about</a></html>",
            "about.html": b"<html><title>a</title></html>",
        }
    )
    try:
        gate = _gate()
        tenant = _tenant()
        base_task = {
            "task_id": "T-SCR-2",
            "tenant_id": tenant,
            "seed_urls": [site.base + "/index.html"],
            "observation_gate": gate,
        }
        first = await scrapy_crawl(dict(base_task))
        second = await scrapy_crawl(dict(base_task))
        assert first["observed"] >= 2
        assert [o["status"] for o in second["observations"]] == ["duplicate", "duplicate"]
        first_refs = {o["raw_ref"] for o in first["observations"]}
        second_refs = {o["raw_ref"] for o in second["observations"]}
        assert first_refs == second_refs
    finally:
        site.close()


async def test_warc_adapter_range_reads_s3_and_observes_payload() -> None:
    store = ObjectStore()
    data = _warc_bytes()
    tenant = _tenant()
    ref, _existed = await store.put_raw_dedup(data, tenant_id=tenant)
    uri = f"{ref.uri}?offset=0&length={len(data)}"
    result = await adapt_warc(
        {
            "task_id": "T-WAR-1",
            "tenant_id": tenant,
            "warc_uri": uri,
            "object_store": store,
            "observation_gate": _gate(),
        }
    )
    assert result["adapted"] == 1
    obs = result["observations"][0]
    assert obs["status"] == "created"
    assert obs["uri"] == "https://collect.example/page"


async def test_dataset_worker_parquet_artifact_lands_in_gate() -> None:
    import tempfile

    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({"url": ["a", "b"], "size": [1, 2]})
    with tempfile.TemporaryDirectory() as td:
        path = str(Path(td) / "fixture.parquet")
        pq.write_table(table, path)
        store = ObjectStore()
        gate = ObservationGate(store, ContentRouter())
        result = await worker_dataset.acquire(
            {
                "task_id": "T-DS-1",
                "tenant_id": _tenant(),
                "dataset_url": path,
                "observation_gate": gate,
            }
        )
        assert result["observed"] == 1
        obs = result["observations"][0]
        assert obs["status"] == "created"
        assert obs["meta"]["schema"] == ["url:string", "size:int64"]
        key = obs["raw_ref"].split("s3://", 1)[1].split("/", 1)[1]
        stored = await store.read_range(bucket=store.raw_bucket, key=key)
        assert stored == Path(path).read_bytes()


async def test_commoncrawl_discover_normalizes_candidates_from_stub() -> None:
    lines = [
        {
            "url": "https://news.example/a",
            "timestamp": "20231012000000",
            "status": "200",
            "mime": "text/html",
            "digest": "abc",
            "filename": "crawl-data/CC-MAIN-1/segments/0/warc/000.warc.gz",
            "offset": "123",
            "length": "456",
        },
        {
            "url": "https://news.example/b",
            "timestamp": "20231012000001",
            "status": "200",
            "mime": "text/html",
            "digest": "def",
            "filename": "crawl-data/CC-MAIN-1/segments/0/warc/000.warc.gz",
            "offset": "457",
            "length": "789",
        },
    ]
    payload = "\n".join(json.dumps(ln) for ln in lines).encode()

    class _Handler(SimpleHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", _free_port()), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async def fetch(url: str) -> str:
            resp = await httpx.AsyncClient().get(url)
            return resp.text

        result = await discover(
            {"task_id": "T-CC-1", "url": "https://news.example/a", "index_url": f"http://127.0.0.1:{server.server_address[1]}/idx"},
            http_get=fetch,
        )
        assert result["candidate_count"] == 2
        assert result["adapted_fits"] is True
        assert all("?offset=" in c["uri"] for c in result["candidates"])
    finally:
        server.shutdown()