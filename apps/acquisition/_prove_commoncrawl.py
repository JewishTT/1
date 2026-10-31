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

    client = CommonCrawlClient(timeout=45.0)
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
    crawl = max(main_indexes, key=lambda item: crawl_badge(item) or ("", 0, 0))
    print(f"indexes returned: {len(crawls)} · selected: {crawl}")

    try:
        hits = await client.discover(
            target,
            crawl=crawl,
            limit="20",
            filter="status:200",
        )
    except Exception as exc:
        print(json.dumps({"status": "cdx_query_failed", "crawl": crawl, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}))
        return 5
    eligible = [
        hit for hit in hits
        if hit.get("status") == "200"
        and str(hit.get("mime") or "").lower().startswith(("text/html", "application/xhtml"))
        and 0 < int(hit.get("length") or 0) <= MAX_RANGE_BYTES
        and hit.get("uri")
    ]
    print(f"CDX rows: {len(hits)} · eligible HTML ranges: {len(eligible)}")
    if not eligible:
        print(json.dumps({"status": "no_eligible_cdx_record", "crawl": crawl, "target": target}))
        return 6

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
