"""Browsertrix engine adapter (T098): headless browser worker pool.

Browsertrix-crawler runs as an external CLI process (``crawler crawl``) writing
WARC files per collection; the adapter reads those WARCs and pushes each page
through the single Observation Gate. The command builder is pure (unit-tested)
and the process launcher is injectable so tests never need the browser image.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from warcio.archiveiterator import ArchiveIterator

from .._ingest import ingest_warc_records
from ..warc.collect import WarcRecord

MAX_PAYLOAD_BYTES = 16 * 1024 * 1024


def build_crawl_command(task: dict, *, collection: str) -> list[str]:
    """Pure builder for the Browsertrix ``crawler crawl`` invocation."""
    seeds = task.get("seed_urls") or ([task["uri"]] if task.get("uri") else [])
    if not seeds:
        raise ValueError("task requires 'seed_urls' or 'uri'")
    cmd = [
        "crawler",
        "crawl",
        "--collection",
        collection,
        "--workers",
        str(int(task.get("workers", 2))),
        "--timeout",
        str(int(task.get("page_timeout_s", 90))),
        *([] if task.get("screenshots", False) else ["--noScreenshots"]),
    ]
    for seed in seeds:
        cmd += ["--url", seed]
    return cmd


def collection_warcs(outdir: Path, collection: str) -> list[Path]:
    """WARC files produced by a Browsertrix collection run."""
    archive = Path(outdir) / "crawls" / "collections" / collection / "archive"
    if not archive.is_dir():
        return []
    return sorted(p for p in archive.iterdir() if p.suffix in (".gz", ".warc"))


def parse_warc_file(path: Path) -> list[WarcRecord]:
    records: list[WarcRecord] = []
    with Path(path).open("rb") as handle:
        for rec in ArchiveIterator(handle):
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


async def _subprocess_executor(cmd: list[str], outdir: Path) -> None:
    if shutil.which("crawler") is None:
        raise RuntimeError(
            "browsertrix-crawler CLI not installed; pass executor=... for a controlled run"
        )
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(outdir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"crawler exited {proc.returncode}: {(err or b'').decode(errors='replace')[-800:]}"
        )


async def run_browsertrix(
    task: dict, *, collection: str = "cognitive", executor=None
) -> list[WarcRecord]:
    """Run a Browsertrix collection and return parsed WARC records."""
    import tempfile

    seed_hint = (task.get("seed_urls") or [task.get("uri", "seed")])[0]
    outdir = Path(task.get("cwd") or tempfile.mkdtemp(prefix="browsertrix-"))
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = build_crawl_command(task, collection=collection)
    run = executor or _subprocess_executor
    await run(cmd, outdir)
    records: list[WarcRecord] = []
    for warc in collection_warcs(outdir, collection):
        records.extend(parse_warc_file(warc))
    if not records:
        raise RuntimeError(f"no WARC records produced for seed {seed_hint!r}")
    return records


async def adapt_browsertrix(task: dict, *, executor=None) -> dict:
    """Adapter callable: relay Browsertrix WARC output to the gate."""
    records = await run_browsertrix(task, executor=executor)
    observations = await ingest_warc_records(
        task, records, collector="browsertrix-adapter", source_kind="browser"
    )
    return {
        "task_id": task.get("task_id", ""),
        "adapted": len(observations),
        "observations": observations,
    }