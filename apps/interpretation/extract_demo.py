"""Deterministic extraction demo entrypoint (spec 007 quickstart).

Usage::

    uv run --project apps/interpretation python -m extract_demo bench/fixtures/extraction/profile.html

Reads a file (or extensions' corpus dir), runs the full deterministic stack,
prints the ExtractionResult as compact JSON (deterministic key order).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from extractors.lane import build_default_stack, extract_deterministic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="extract_demo", description="Deterministic extraction lane")
    parser.add_argument("path", nargs="*", help="artifact file(s) or directories to scan")
    parser.add_argument("--limit", type=int, default=0, help="max mentions printed per artifact (0 = all)")
    args = parser.parse_args(argv)

    targets = [Path(p) for p in args.path] or [Path("bench/fixtures/extraction/profile.html")]
    registry, extractors = build_default_stack()

    for target in targets:
        files = [target] if target.is_file() else sorted(target.rglob("*")) if target.is_dir() else []
        for file in sorted(files):
            if not file.is_file():
                continue
            raw = file.read_bytes()
            result = extract_deterministic(raw, stack=(registry, extractors))
            payload = result.to_dict()
            if args.limit and len(payload["mentions"]) > args.limit:
                payload["mentions"] = payload["mentions"][: args.limit]
            print(json.dumps({str(file): payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())