"""Strict live Common Crawl proof: CDX index lookup plus exact WARC byte-range retrieval.

A green result requires real data from both public endpoints:
  1. index.commoncrawl.org returns a CDX JSON line with URL, crawl timestamp,
     digest, filename, offset and length;
  2. data.commoncrawl.org returns HTTP 206 for that exact byte range and warcio
     yields a response record for the indexed URL with a non-empty body.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parent / "shared"))

from adapters.warc.collect import MAX_PAYLOAD_BYTES, parse_warc, range_of, split_s3_uri
from network.commoncrawl import CommonCrawlClient, crawl_badge

TARGET_URL = os.environ.get("COGNITIVE_CC_TARGET_URL", "https://example.com/")
MAX_RANGE_BYTES = 16 * 1024 * 1024
USER_AGENT = "cognitive-substrate-commoncrawl-proof/1.0 (+https://github.com/JewishTT/1)"


async def main() -> int:
    target = TARGET_URL.strip()
    if urlsplit(target).scheme not in {"http", "https"}:
        print(json.dumps({"status": "refused", "reason": "target must be an HTTP(S) URL"}))
        return 2

    client = CommonCrawlClient(timeout=90.0)
    print("=" * 72)
    print(f"COMMON CRAWL LIVE PROOF · {datetime.now(UTC).isoformat()}")
    print(f"target: {target}")
    print("=" * 72)

    try:
        crawls = await client.list_indexes()
    except Exception as exc:
        print(json.dumps({"status": "index_list_failed", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}))
        return 3
    main_indexes = [crawl for crawl in crawls if crawl.startswith("CC-MAIN-") and crawl_badge(crawl)]
    if not main_indexes:
        print(json.dumps({"status": "no_main_index_returned", "index_count": len(crawls)}))
        return 4
    ordered_indexes = sorted(
        set(main_indexes),
        key=lambda item: crawl_badge(item) or ("", 0, 0),
        reverse=True,
    )
    attempts: list[dict[str, str | int]] = []
    crawl = ""
    hits: list[dict] = []
    eligible: list[dict] = []
    transient_statuses = {408, 429, 500, 502, 503, 504}

    # The latest Common Crawl partition can be under heavy indexing load. Do
    # not let one transient 504 make the whole acquisition look unavailable:
    # retry twice, then fall back through a strictly bounded list of older
    # published index partitions.
    for candidate in ordered_indexes[:4]:
        partition_hits: list[dict] = []
        for attempt in range(1, 3):
            try:
                partition_hits = await client.discover(
                    target,
                    crawl=candidate,
                    limit="20",
                    filter="status:200",
                )
                attempts.append({"crawl": candidate, "attempt": attempt, "status": "ok"})
                break
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                attempts.append({"crawl": candidate, "attempt": attempt, "status": code})
                if code not in transient_statuses or attempt == 2:
                    break
                await asyncio.sleep(attempt * 2)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                attempts.append({
                    "crawl": candidate,
                    "attempt": attempt,
                    "status": f"{type(exc).__name__}: {str(exc)[:120]}",
                })
                if attempt == 2:
                    break
                await asyncio.sleep(attempt * 2)
            except Exception as exc:
                attempts.append({
                    "crawl": candidate,
                    "attempt": attempt,
                    "status": f"{type(exc).__name__}: {str(exc)[:120]}",
                })
                break

        if not partition_hits:
            continue
        partition_eligible = [
            hit for hit in partition_hits
            if hit.get("status") == "200"
            and str(hit.get("mime") or "").lower().startswith(("text/html", "application/xhtml"))
            and 0 < int(hit.get("length") or 0) <= MAX_RANGE_BYTES
            and hit.get("uri")
        ]
        if partition_eligible:
            crawl = candidate
            hits = partition_hits
            eligible = partition_eligible
            break

    print(f"indexes returned: {len(crawls)} · attempted partitions: {len(attempts)} · selected: {crawl or 'none'}")
    if not crawl:
        print(json.dumps({
            "status": "cdx_query_failed",
            "target": target,
            "attempts": attempts,
        }, indent=2))
        return 5
    print(f"CDX rows: {len(hits)} · eligible HTML ranges: {len(eligible)}")

    last_error = ""
    chosen = None
    parsed_records = []
    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as http:
        for hit in eligible[:8]:
            try:
                bucket, key = split_s3_uri(hit["uri"])
                if bucket != "data.commoncrawl.org":
                    raise ValueError(f"unexpected WARC bucket: {bucket}")
                offset, length = range_of(hit["uri"])
                if length is None or length <= 0 or length > MAX_RANGE_BYTES:
                    raise ValueError(f"range length outside bound: {length}")
                start, end = offset, offset + length - 1
                url = f"https://data.commoncrawl.org/{key}"
                response = await http.get(url, headers={"Range": f"bytes={start}-{end}"})
                if response.status_code != 206:
                    raise RuntimeError(f"WARC range expected HTTP 206, got {response.status_code}")
                if len(response.content) != length:
                    raise RuntimeError(f"WARC range length mismatch: expected {length}, got {len(response.content)}")
                rows = parse_warc(__import__("io").BytesIO(response.content))
                matching = [row for row in rows if row.url.rstrip("/") == str(hit.get("url", "")).rstrip("/")]
                matching = [row for row in matching if row.payload and len(row.payload) <= MAX_PAYLOAD_BYTES]
                if not matching:
                    raise RuntimeError("range contained no non-empty response record for the indexed URL")
                chosen = hit
                parsed_records = matching
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:240]}"
                continue

    if not chosen or not parsed_records:
        print(json.dumps({"status": "warc_range_failed", "last_error": last_error, "attempted": min(8, len(eligible))}))
        return 7

    record = parsed_records[0]
    digest = hashlib.sha256(record.payload).hexdigest()
    manifest = {
        "status": "PASS",
        "checked_at": datetime.now(UTC).isoformat(),
        "target_url": target,
        "crawl": crawl,
        "index_attempts": attempts,
        "index": {
            "url": chosen.get("url"),
            "timestamp": chosen.get("timestamp"),
            "status": chosen.get("status"),
            "mime": chosen.get("mime"),
            "digest": chosen.get("digest"),
            "warc_uri": chosen.get("uri"),
        },
        "warc": {
            "response_url": record.url,
            "warc_date": record.warc_date,
            "content_type": record.content_type,
            "payload_bytes": len(record.payload),
            "payload_sha256": digest,
            "warc_payload_digest": record.digest,
            "range_status": 206,
        },
    }
    out = Path(os.environ.get("COGNITIVE_PROOF_OUTPUT", "artifacts/acquisition-integration"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "commoncrawl-live.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(f"Proof artifact: {out / 'commoncrawl-live.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
