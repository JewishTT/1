"""Scrapy exemplar adapter (T096): external process -> CollectionAdapter stream.

The spider runs as a separate subprocess (Scrapy's own reactor); the adapter
reads the exported bytes + metadata and pushes each page through the single
Observation Gate. No other storage/event write path is touched.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ADAPTER_DIR = Path(__file__).resolve().parent
SPIDER_PATH = ADAPTER_DIR / "spider.py"


async def run_spider(seed_urls: list[str], outdir: Path, timeout: int = 300) -> list[dict]:
    """Launch the exemplar spider; return NDJSON records (path + metadata)."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    urls_file = outdir / "urls.txt"
    urls_file.write_text("\n".join(seed_urls), encoding="utf-8")
    index = outdir / "index.ndjson"
    if index.exists():
        index.unlink()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "scrapy",
        "runspider",
        str(SPIDER_PATH),
        "-a",
        f"urls_file={urls_file}",
        "-a",
        f"outdir={outdir}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(ADAPTER_DIR.parents[1]),
    )
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"scrapy exited {proc.returncode}: {(err or b'').decode(errors='replace')[-800:]}"
        )
    records: list[dict] = []
    if index.exists():
        for line in index.read_text(encoding="utf-8").splitlines():
            records.append(json.loads(line))
    return records


def _read_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


async def scrapy_crawl(task: dict) -> dict:
    """Adapter callable: run the crawler, push every page through the gate."""
    gate = task.get("observation_gate")
    if gate is None:  # Observation boundary: no gate -> refuse to store anywhere else.
        raise ValueError("task requires 'observation_gate' (Observation boundary)")
    seed_urls = task.get("seed_urls") or ([task["uri"]] if task.get("uri") else [])
    if not seed_urls:
        raise ValueError("task requires 'seed_urls' or 'uri'")
    tenant_id = task.get("tenant_id", "tenant-demo")
    with tempfile.TemporaryDirectory(prefix="scrapy-exemplar-") as td:
        records = await run_spider(seed_urls, Path(td))
        observations = []
        for rec in records:
            body = await asyncio.to_thread(_read_bytes, rec["path"])
            obs = await gate.ingest(
                body=body,
                uri=rec["url"],
                tenant_id=tenant_id,
                investigation_id=task.get("investigation_id"),
                source_id=task.get("source_id"),
                work_id=task.get("work_id"),
                region_id=task.get("region_id"),
                content_type=rec.get("content_type") or None,
                collector="scrapy-adapter",
                collector_version="2.0.0",
                source_kind="web",
            )
            observations.append(
                {
                    "uri": rec["url"],
                    "observation_id": obs["observation_id"],
                    "status": obs["status"],
                    "raw_ref": obs["raw_ref"],
                }
            )
    return {
        "task_id": task.get("task_id", ""),
        "observed": len(observations),
        "observations": observations,
    }