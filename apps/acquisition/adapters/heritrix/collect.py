"""Heritrix engine adapter (T096): archival WARC-first collection.

Relays a Heritrix crawler job (REST API: ``_action=launch``, ``.state``,
``.findex``) and streams emitted WARCs through the single Observation Gate.
The external engine never writes to Cognitive storage — the HTTP client is
injectable so tests run against a stub job without Java/Heritrix installed.
"""

from __future__ import annotations

import asyncio
import io

import httpx
from warcio.archiveiterator import ArchiveIterator

from .._ingest import ingest_warc_records
from ..warc.collect import WarcRecord

DEFAULT_POLL_S: float = 2.0
MAX_WAIT_S: float = 120.0
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024

TERMINAL_STATES = frozenset({"FINISHED", "ABORTED", "STOPPED"})


class HeritrixClient:
    """Minimal Heritrix engine REST client (job launch/state/WARC listing)."""

    def __init__(self, base_url: str, *, token: str = "", poll_s: float = DEFAULT_POLL_S) -> None:
        self.base = base_url.rstrip("/")
        self.token = token
        self.poll_s = poll_s

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def launch(self, job: str) -> None:
        async with httpx.AsyncClient(timeout=30, headers=self._headers()) as client:
            resp = await client.post(
                f"{self.base}/engine",
                params={"_action": "launch", "job": job},
            )
            resp.raise_for_status()

    async def state(self, job: str) -> str:
        async with httpx.AsyncClient(timeout=30, headers=self._headers()) as client:
            resp = await client.get(f"{self.base}/job/{job}.state")
            resp.raise_for_status()
            return resp.text.strip()

    async def warcs(self, job: str) -> list[str]:
        async with httpx.AsyncClient(timeout=30, headers=self._headers()) as client:
            resp = await client.get(f"{self.base}/job/{job}.findex")
            resp.raise_for_status()
        return [ln.strip() for ln in resp.text.splitlines() if ln.strip()]

    async def fetch_warc(self, warc_path: str) -> bytes:
        async with httpx.AsyncClient(timeout=120, headers=self._headers()) as client:
            resp = await client.get(f"{self.base}/job/{warc_path.lstrip('/')}")
            resp.raise_for_status()
            return resp.content


def parse_warc_bytes(data: bytes) -> list[WarcRecord]:
    """Parse ``response`` records out of a WARC payload buffer."""
    records: list[WarcRecord] = []
    for rec in ArchiveIterator(io.BytesIO(data)):
        if rec.rec_type != "response":
            continue
        url = rec.rec_headers.get_header("WARC-Target-URI") or ""
        if not url.startswith(("http://", "https://")):
            continue
        payload = rec.content_stream().read(MAX_PAYLOAD_BYTES + 1)
        content_type = None
        if rec.http_headers is not None:
            content_type = rec.http_headers.get_header("Content-Type")
        records.append(
            WarcRecord(
                url=url,
                warc_date=rec.rec_headers.get_header("WARC-Date"),
                content_type=(content_type or "").split(";")[0].strip() or None,
                payload=payload,
                digest=rec.rec_headers.get_header("WARC-Payload-Digest"),
            )
        )
    return records


async def run_heritrix_crawl(task: dict, *, job: str = "crawl", client=None) -> list[WarcRecord]:
    """Drive a Heritrix job to completion and return parsed WARC records."""
    if client is None:
        client = HeritrixClient(task.get("base_url", "http://localhost:8443"))
    await client.launch(job)
    deadline = asyncio.get_event_loop().time() + float(task.get("max_wait_s", MAX_WAIT_S))
    while True:
        state = await client.state(job)
        if state in TERMINAL_STATES:
            break
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(f"heritrix job {job!r} did not finish in time (state={state!r})")
        await asyncio.sleep(client.poll_s)
    records: list[WarcRecord] = []
    for warc_path in await client.warcs(job):
        data = await client.fetch_warc(warc_path)
        records.extend(parse_warc_bytes(data))
    return records


async def adapt_heritrix(task: dict, *, client=None) -> dict:
    """Adapter callable: relay Heritrix WARC output to the gate."""
    samples = await run_heritrix_crawl(task, client=client)
    observations = await ingest_warc_records(
        task, samples, collector="heritrix-adapter", source_kind="webarchive"
    )
    return {
        "task_id": task.get("task_id", ""),
        "adapted": len(observations),
        "observations": observations,
    }