"""Nutch engine adapter (T100): bulk crawl backend.

Apache Nutch runs as an external bulk crawler (``bin/nutch crawl``) producing
segment directories. The adapter owns the CLI contract (args builder) and the
segment import contract: each parsed segment file carries ``URL:`` metadata plus
the document body; every document converges on the single Observation Gate.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .._ingest import fetch_record, ingest_warc_records


def build_crawl_args(
    task: dict,
    *,
    seeds_dir: str,
    crawl_dir: str,
    depth: int = 3,
    threads: int = 10,
) -> list[str]:
    """Pure builder for the Nutch ``bin/nutch crawl`` invocation."""
    if not seeds_dir:
        raise ValueError("task requires 'seeds_dir' for nutch")
    return [
        "bin/nutch",
        "crawl",
        seeds_dir,
        "-dir",
        crawl_dir,
        "-depth",
        str(int(depth)),
        "-threads",
        str(int(threads)),
    ]


def parse_segment_file(text: str) -> tuple[str, bytes] | None:
    """Parse a Nutch parse_text document (``URL: ...`` header + body)."""
    url = ""
    body_lines: list[str] = []
    in_body = False
    for line in text.splitlines():
        if not in_body and line.startswith("URL:"):
            url = line[len("URL:") :].strip()
            continue
        if not in_body and line.startswith("#"):
            continue
        in_body = True
        body_lines.append(line)
    if not url:
        return None
    return url, "\n".join(body_lines).encode("utf-8")


def segment_documents(crawl_dir: str) -> list[Path]:
    """Parsed segment documents under ``<crawl_dir>/segments/*/parse_text``."""
    segments = Path(crawl_dir) / "segments"
    if not segments.is_dir():
        return []
    docs: list[Path] = []
    for seg in sorted(segments.iterdir()):
        parse_text = seg / "parse_text"
        if parse_text.is_dir():
            docs.extend(sorted(p for p in parse_text.iterdir() if p.is_file()))
    return docs


async def collect_segments(task: dict, crawl_dir: str) -> list:
    """Load parsed segment documents as engine records."""
    records = []
    for doc in segment_documents(crawl_dir):
        text = await asyncio.to_thread(doc.read_text, "utf-8")
        parsed = parse_segment_file(text)
        if parsed is None:
            continue
        url, payload = parsed
        records.append(fetch_record(url, task.get("content_type", "text/html"), payload))
    return records


async def adapt_nutch(task: dict, *, executor=None) -> dict:
    """Adapter callable: import Nutch segments through the gate (bulk backend)."""
    crawl_dir = task.get("crawl_dir")
    if not crawl_dir:
        raise ValueError("task requires 'crawl_dir' (Nutch bulk engine boundary)")
    args = build_crawl_args(task, seeds_dir=task.get("seeds_dir", ""), crawl_dir=crawl_dir)
    records = await collect_segments(task, crawl_dir)
    observations = await ingest_warc_records(
        task, records, collector="nutch-adapter", source_kind="web"
    )
    return {
        "task_id": task.get("task_id", ""),
        "crawl_args": args,
        "adapted": len(observations),
        "observations": observations,
    }