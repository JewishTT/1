"""StormCrawler engine adapter (T099): distributed streaming crawl engine.

StormCrawler is a distributed topology (Storm bolts) that streams fetched
content to a search backend. Cognitive integrates at the *job contract* level:
the adapter emits a topology job spec (seeds, render type, crawl id, fetch
interval) and consumes the engine's fetch manifest (url + local content path +
content type) into the single Observation Gate. No Solr/Storm dependency is
required for the contract; the manifest is the engine boundary.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .._ingest import fetch_record, ingest_warc_records


def build_job_spec(
    task: dict,
    *,
    crawl_id: str = "cognitive-crawl",
    rendertype: str = "html",
    fetchers: int = 2,
    fetch_interval_s: int = 60,
) -> dict:
    """Pure builder for a StormCrawler topology job spec (JSON-serializable)."""
    seeds = task.get("seed_urls") or ([task["uri"]] if task.get("uri") else [])
    if not seeds:
        raise ValueError("task requires 'seed_urls' or 'uri'")
    return {
        "crawl_id": crawl_id,
        "seeds": list(seeds),
        "evaluate": float(task.get("evaluate", 0.8)),
        "fetch_interval_s": int(fetch_interval_s),
        "fetchers": int(fetchers),
        "rendertype": rendertype,
        "sink": "manifest://cognitive",
        "url_filters": list(task.get("url_filters", [])),
    }


def parse_fetch_manifest(text: str) -> list[dict]:
    """Parse the engine fetch manifest (NDJSON rows: url, path, content_type)."""
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if not rec.get("url") or not rec.get("path"):
            continue
        rows.append(
            {
                "url": rec["url"],
                "path": rec["path"],
                "content_type": rec.get("content_type"),
            }
        )
    return rows


async def _read(path: str) -> bytes:
    return await asyncio.to_thread(Path(path).read_bytes)


async def collect_fetches(task: dict, manifest_path: str) -> list:
    """Read manifest rows and load each fetched payload as a record."""
    text = await asyncio.to_thread(Path(manifest_path).read_text, "utf-8")
    records = []
    for row in parse_fetch_manifest(text):
        payload = await _read(row["path"])
        records.append(fetch_record(row["url"], row["content_type"], payload))
    return records


async def adapt_stormcrawler(task: dict) -> dict:
    """Adapter callable: emit the job spec and ingest the fetch manifest."""
    manifest_path = task.get("manifest_path")
    if not manifest_path:
        raise ValueError("task requires 'manifest_path' (StormCrawler engine boundary)")
    spec = build_job_spec(
        task,
        crawl_id=task.get("crawl_id", "cognitive-crawl"),
        rendertype=task.get("rendertype", "html"),
        fetchers=int(task.get("fetchers", 2)),
        fetch_interval_s=int(task.get("fetch_interval_s", 60)),
    )
    records = await collect_fetches(task, manifest_path)
    observations = await ingest_warc_records(
        task, records, collector="stormcrawler-adapter", source_kind="web"
    )
    return {
        "task_id": task.get("task_id", ""),
        "job_spec": spec,
        "adapted": len(observations),
        "observations": observations,
    }