from __future__ import annotations
import os
import csv
import json
import re
from pathlib import Path
from typing import List, Dict, Tuple

# Simple, self-contained exporter with optional split-by-entity CSVs
# - export() returns (csv_path, json_path)
# - When split_by_entity=True, also writes additional CSVs:
#   urls.csv, emails.csv, phones.csv, images.csv, pdfs.csv (plus misc.csv if needed)

EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
PHONE_RE = re.compile(r"(?:(?:\+?\d{1,3})?[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}")


def ensure_dir(p: str | os.PathLike[str]) -> Path:
    path = Path(p)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _infer_kind(r: Dict) -> str:
    url = (r.get("url") or "").lower()
    src = (r.get("source") or "").lower()
    media = (r.get("media_type") or "").lower()
    # email / phone in any string field
    for v in r.values():
        if isinstance(v, str) and EMAIL_RE.search(v or ""):
            return "emails"
        if isinstance(v, str) and PHONE_RE.search(v or ""):
            return "phones"
    # media
    if media == "image" or src == "image":
        return "images"
    if media == "pdf" or src == "pdf" or url.endswith(".pdf"):
        return "pdfs"
    # default url bucket
    if url:
        return "urls"
    return "misc"


def export(
    results: List[Dict],
    outdir: str | os.PathLike[str],
    filename_tpl: str,
    name: str,
    formats: Tuple[str, ...] = ("csv", "json"),
    split_by_entity: bool = False,
) -> Tuple[str, str]:
    """
    Write unified CSV/JSON and optional split CSVs by entity type.

    Args:
        results: list of dict rows
        outdir: output directory path
        filename_tpl: template ending with .ext; base will be used for files
        name: not used directly here but kept for compatibility
        formats: tuple containing any of {"csv","json"}
        split_by_entity: when True, also write *_urls.csv, *_emails.csv, ...
    Returns:
        (csv_path, json_path) absolute paths (if format not requested, still returns computed paths)
    """
    ensure_dir(outdir)
    base = filename_tpl.rsplit(".", 1)[0]
    fname_csv = base + ".csv"
    fname_json = base + ".json"

    # unified CSV
    if "csv" in formats:
        keys = sorted({k for r in results for k in r.keys()}) or ["url", "title", "domain", "source"]
        with open(Path(outdir) / fname_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in results:
                w.writerow({k: r.get(k, "") for k in keys})

    # unified JSON
    if "json" in formats:
        with open(Path(outdir) / fname_json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    # split CSVs
    if split_by_entity:
        buckets: Dict[str, List[Dict]] = {"urls": [], "emails": [], "phones": [], "images": [], "pdfs": [], "misc": []}
        for r in results:
            kind = _infer_kind(r)
            buckets.setdefault(kind, []).append(r)
        for bname, rows in buckets.items():
            if not rows:
                continue
            keys = sorted({k for r in rows for k in r.keys()}) or ["url", "title", "domain", "source"]
            with open(Path(outdir) / (base + f"_{bname}.csv"), "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                for r in rows:
                    w.writerow({k: r.get(k, "") for k in keys})

    return (str(Path(outdir) / fname_csv), str(Path(outdir) / fname_json))

