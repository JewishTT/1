"""Offline dataset build (spec 007, T005): produce canonical, content-addressed
dictionary datasets from raw input files.

Canonical form: JSONL with ``{"term": ..., "payload": {...}}`` entries sorted by
term (then payload), compact separators, trailing newline — the same inputs always
yield the same sha256 (FR-8). A sidecar ``*.meta.json`` records kind, version,
license, entries, sha256.

Usage:
    uv run python -m datasets.build --kind geonames --version 2026.08 \
        --license "CC-BY-4.0" --in cities_ru_en.tsv --out .datasets/

Accepted input: JSONL with term/payload keys, or TSV where column 1 is the term
and the remaining tab-separated columns are payload values (joined as a list).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

KINDS = ("geonames", "sanctions", "first_names", "surnames", "companies")


def _read_input(path: Path) -> list[dict]:
    entries: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("{"):
            obj = json.loads(line)
            if "term" not in obj:
                raise ValueError(f"JSONL entry without 'term': {line[:80]}")
            entries.append(obj)
        else:
            parts = line.split("\t")
            entries.append({"term": parts[0].strip(), "payload": {"values": [p.strip() for p in parts[1:]]}})
    return entries


def _read_jsonl_bytes(data: bytes) -> list[dict]:
    """Parse canonical JSONL bytes (one term/payload object per line)."""
    entries: list[dict] = []
    for raw in data.decode("utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        if "term" not in obj:
            raise ValueError(f"JSONL entry without 'term': {line[:80]}")
        entries.append(obj)
    return entries


def canonicalize(entries: list[dict]) -> str:
    """Term-sorted canonical JSONL (deterministic bytes)."""
    dedup: dict[str, dict] = {}
    for entry in entries:
        term = str(entry["term"]).strip()
        if not term:
            continue
        payload = entry.get("payload", {})
        key = term + "\x00" + json.dumps(payload, sort_keys=True, ensure_ascii=False)
        dedup[key] = {"term": term, "payload": payload}
    lines = [
        json.dumps(dedup[k], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        for k in sorted(dedup)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def build(
    *,
    kind: str,
    version: str,
    license_note: str,
    input_path: Path | None = None,
    input_bytes: bytes | None = None,
    out_dir: Path,
) -> tuple[Path, str, int]:
    if kind not in KINDS:
        raise ValueError(f"unknown dataset kind: {kind} (expected one of {KINDS})")
    if input_path is None and input_bytes is None:
        raise ValueError("provide either input_path or input_bytes")
    entries = _read_input(input_path) if input_path is not None else _read_jsonl_bytes(input_bytes or b"")
    canonical = canonicalize(entries)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    out_dir.mkdir(parents=True, exist_ok=True)
    data_path = out_dir / f"{kind}_{version}.jsonl"
    meta_path = out_dir / f"{kind}_{version}.meta.json"
    data_path.write_bytes(canonical.encode("utf-8"))
    meta = {
        "kind": kind,
        "version": version,
        "sha256": digest,
        "license": license_note,
        "entries": len(entries),
    }
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return data_path, digest, len(entries)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a canonical dictionary dataset")
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--version", required=True)
    parser.add_argument("--license", required=True, dest="license_note")
    parser.add_argument("--in", dest="input_path", required=True, type=Path)
    parser.add_argument("--out", dest="out_dir", required=True, type=Path)
    args = parser.parse_args()
    data_path, digest, count = build(
        kind=args.kind,
        version=args.version,
        license_note=args.license_note,
        input_path=args.input_path,
        out_dir=args.out_dir,
    )
    print(f"built {data_path}")
    print(f"sha256={digest} entries={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
