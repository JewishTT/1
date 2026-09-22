"""Integration: Wave 5 engine adapters push bytes through the real gate (T096/T098/T099/T100).

Engine boundaries are simulated the same way Wave 3 simulated Common Crawl: a
stub Heritrix HTTP API / fake executors / fixture manifests. Every run lands in
content-addressed MinIO; statuses follow the R-08 lifecycle; dedup is proven on
a second identical run.
"""

from __future__ import annotations

import socket
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

import pytest
from adapters.browsertrix.collect import adapt_browsertrix
from adapters.heritrix.collect import HeritrixClient, adapt_heritrix
from adapters.nutch.collect import adapt_nutch
from adapters.stormcrawler.collect import adapt_stormcrawler
from events.content_router import ContentRouter
from events.observation_gate import ObservationGate
from storage.s3 import ObjectStore
from warcio import WARCWriter
from warcio.statusandheaders import StatusAndHeaders

pytestmark = pytest.mark.integration

_MINI_PORT = 9000


def _minio_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", _MINI_PORT), timeout=3):
            return True
    except OSError:
        return False


pytestmark = [pytestmark, pytest.mark.skipif(not _minio_reachable(), reason="minio unavailable")]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _gate() -> ObservationGate:
    return ObservationGate(ObjectStore(), ContentRouter(), producer=None)


def _tenant() -> str:
    return "ten-eng-" + uuid.uuid4().hex[:6]


def _warc_bytes(url: str, body: bytes) -> bytes:
    buf = BytesIO()
    writer = WARCWriter(buf, gzip=False)
    writer.write_record(
        writer.create_warc_record(
            url,
            "response",
            payload=BytesIO(body),
            http_headers=StatusAndHeaders(
                "HTTP/1.1 200 OK",
                [("Content-Type", "text/html"), ("Content-Length", str(len(body)))],
                protocol="HTTP/1.1",
            ),
        )
    )
    return buf.getvalue()


async def test_heritrix_adapter_streams_stub_job_warcs_through_gate() -> None:
    warc = _warc_bytes("https://heritrix.example/page", b"<html>heritrix</html>")
    state = {"engine_launches": 0}

    class _HeritrixHandler(BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:  # noqa: ANN002
            pass

        def do_POST(self) -> None:  # noqa: N802
            state["engine_launches"] += 1
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def do_GET(self) -> None:  # noqa: N802
            path_url = self.path
            if path_url.endswith(".state"):
                body = b"FINISHED"
            elif path_url.endswith(".findex"):
                body = b"job/crawl/warcs/000.warc"
            elif path_url.endswith(".warc"):
                body = warc
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", _free_port()), _HeritrixHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = HeritrixClient(f"http://127.0.0.1:{server.server_address[1]}", poll_s=0.05)
        tenant = _tenant()
        result = await adapt_heritrix(
            {
                "task_id": "T-HER-1",
                "tenant_id": tenant,
                "observation_gate": _gate(),
            },
            client=client,
        )
        assert state["engine_launches"] == 1
        assert result["adapted"] == 1
        obs = result["observations"][0]
        assert obs["status"] == "created"
        assert obs["uri"] == "https://heritrix.example/page"
        assert "/raw/ten-eng-" in obs["raw_ref"]
    finally:
        server.shutdown()


async def test_browsertrix_adapter_collection_warcs_land_in_gate() -> None:
    warc = _warc_bytes("https://browsertrix.example/page", b"<html>browsertrix</html>")

    async def fake_executor(cmd: list[str], outdir: Path) -> None:
        archive = Path(outdir) / "crawls" / "collections" / "cognitive" / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        (archive / "000.warc").write_bytes(warc)

    with tempfile.TemporaryDirectory() as td:
        tenant = _tenant()
        result = await adapt_browsertrix(
            {
                "task_id": "T-BX-1",
                "tenant_id": tenant,
                "seed_urls": ["https://browsertrix.example/page"],
                "cwd": td,
                "observation_gate": _gate(),
            },
            executor=fake_executor,
        )
        assert result["adapted"] == 1
        assert result["observations"][0]["status"] == "created"
        assert result["observations"][0]["uri"] == "https://browsertrix.example/page"


async def test_stormcrawler_manifest_and_fetches_land_in_gate() -> None:
    with tempfile.TemporaryDirectory() as td:
        body = b"<html>stormcrawler</html>"
        doc = Path(td) / "fetch-1.html"
        doc.write_bytes(body)
        manifest = Path(td) / "manifest.ndjson"
        doc_path = str(doc).replace("\\", "/")
        manifest.write_text(
            f'{{"url": "https://stormcrawler.example/a", "path": "{doc_path}", '
            '"content_type": "text/html"}',
            encoding="utf-8",
        )
        tenant = _tenant()
        result = await adapt_stormcrawler(
            {
                "task_id": "T-SC-1",
                "tenant_id": tenant,
                "seed_urls": ["https://stormcrawler.example/"],
                "manifest_path": str(manifest),
                "observation_gate": _gate(),
            }
        )
        assert result["job_spec"]["crawl_id"] == "cognitive-crawl"
        assert result["adapted"] == 1
        assert result["observations"][0]["status"] == "created"
        assert result["observations"][0]["uri"] == "https://stormcrawler.example/a"


async def test_nutch_segments_import_lands_in_gate() -> None:
    with tempfile.TemporaryDirectory() as td:
        crawl = Path(td) / "crawl"
        doc = crawl / "segments" / "20231012000000" / "parse_text" / "0000"
        doc.parent.mkdir(parents=True)
        doc.write_text("URL: https://nutch.example/page\n<html>nutch</html>", encoding="utf-8")

        tenant = _tenant()
        result = await adapt_nutch(
            {
                "task_id": "T-NUT-1",
                "tenant_id": tenant,
                "crawl_dir": str(crawl),
                "seeds_dir": "/unused-in-adapt",
                "observation_gate": _gate(),
            }
        )
        assert result["adapted"] == 1
        obs = result["observations"][0]
        assert obs["status"] == "created"
        assert obs["uri"] == "https://nutch.example/page"


async def test_heritrix_second_run_dedups_by_content() -> None:
    warc = _warc_bytes("https://heritrix.example/stable", b"<html>stable</html>")

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:  # noqa: ANN002
            pass

        def do_POST(self) -> None:  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self) -> None:  # noqa: N802
            if self.path.endswith(".state"):
                body = b"FINISHED"
            elif self.path.endswith(".findex"):
                body = b"job/crawl/warcs/000.warc"
            else:
                body = warc
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", _free_port()), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = HeritrixClient(f"http://127.0.0.1:{server.server_address[1]}", poll_s=0.05)
        tenant = _tenant()
        base = {
            "task_id": "T-HER-2",
            "tenant_id": tenant,
            "observation_gate": _gate(),
        }
        first = await adapt_heritrix(dict(base), client=client)
        second = await adapt_heritrix(dict(base), client=client)
        assert [o["status"] for o in second["observations"]] == ["duplicate"]
        assert {o["raw_ref"] for o in first["observations"]} == {
            o["raw_ref"] for o in second["observations"]
        }
    finally:
        server.shutdown()