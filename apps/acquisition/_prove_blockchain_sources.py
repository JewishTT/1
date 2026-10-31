"""Live proof for the BTC / ETH / TRON read-only source vertical slice.

This deliberately traverses SourceConnector (not a standalone requests snippet),
then parses the captured raw bytes with the source's own declarative parse contract.
A pass means the endpoint returned usable records through the acquisition source path.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "acquisition"))
sys.path.insert(0, str(ROOT / "apps" / "interpretation"))
sys.path.insert(0, str(ROOT / "apps" / "shared"))

from parsers.families import parse_source
from sources.catalogue import load_catalogue
from sources.connector import SourceConnector, tasks_for

QUERIES = {
    "blockstream_btc_address_transactions": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "blockstream_btc_tx_detail": "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b",
    "blockscout_eth_address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "blockscout_eth_transactions": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "trongrid_account": "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
    "trongrid_account_transactions": "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
}


async def main() -> int:
    definitions, rejected = load_catalogue()
    if rejected:
        print(json.dumps({"catalogue_rejections": rejected}, indent=2))
        return 2
    by_name = {definition.name: definition for definition in definitions}
    missing = sorted(set(QUERIES) - set(by_name))
    if missing:
        print(json.dumps({"missing_definitions": missing}, indent=2))
        return 2

    connector = SourceConnector()
    results: list[dict] = []
    try:
        for name, query in QUERIES.items():
            definition = by_name[name]
            try:
                task = tasks_for(definition, query)
                captured = False
                async for capture, event in connector.collect(task):
                    captured = True
                    parsed = parse_source(
                        definition,
                        capture.body or b"",
                        status_code=capture.status,
                    )
                    result = {
                        "source": name,
                        "status_code": capture.status,
                        "parse_status": parsed.status,
                        "records": parsed.record_count,
                        "unresolved_required_fields": list(parsed.unresolved),
                        "content_digest": capture.content_digest,
                        "byte_length": capture.byte_length,
                        "event_id": event.get("event_id") if isinstance(event, dict) else None,
                    }
                    results.append(result)
                    print(json.dumps(result, sort_keys=True))
                    break  # one real page per endpoint is the proof boundary
                if not captured:
                    results.append({"source": name, "error": "no_capture"})
            except Exception as exc:  # the proof records provider-specific failure detail
                results.append({
                    "source": name,
                    "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                })
    finally:
        await connector.aclose()

    failed = [
        result for result in results
        if result.get("status_code") != 200
        or result.get("parse_status") != "ok"
        or not result.get("records")
        or result.get("unresolved_required_fields")
    ]
    print("=" * 72)
    print(json.dumps({
        "checked": len(results),
        "passed": len(results) - len(failed),
        "failed": failed,
    }, indent=2, sort_keys=True))
    return 0 if len(results) == len(QUERIES) and not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
