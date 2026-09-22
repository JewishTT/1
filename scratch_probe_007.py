# -*- coding: utf-8 -*-
"""Authoritative probe: real dictionaries.data + lane mention/evidence surface."""
from __future__ import annotations

import hashlib, json, sys
from pathlib import Path

ROOT = Path(r"C:\Users\tim\Desktop\COGNITIVE\1")
sys.path.insert(0, str(ROOT / "apps" / "interpretation"))

import dictionaries.data as dd  # noqa: E402

print("PUBLIC:", [n for n in dir(dd) if not n.startswith("_")])
print("VERSIONS:", json.dumps(getattr(dd, "VERSIONS", None), ensure_ascii=False, sort_keys=True))
meta_name = "automaton"
if hasattr(dd, meta_name):
    meta, auto = dd.automaton("first_names")
    print("AUTO_FIRST meta:", {k: (v[:24] if isinstance(v, str) and len(v) > 24 else v) for k, v in vars(meta).items()})
    print("AUTO_FIRST type:", type(auto).__name__)

root = getattr(dd, "dataset_root", None) or getattr(dd, "data_root", None)
if root:
    print("DATA_ROOT:", root())

from extractors.lane import extract_deterministic  # noqa: E402

FIX = ROOT / "bench" / "fixtures" / "extraction"


def dump(name: str) -> None:
    blob = (FIX / name).read_bytes()
    r = extract_deterministic(blob)
    print("=" * 20, name, "=" * 20)
    print("ct=", getattr(r, "content_type", None), "sha?=", getattr(r, "artifact_sha", None)[:8] if getattr(r, "artifact_sha", None) else None, "quar=", getattr(r, "quarantined", None), "reason=", getattr(r, "reason", None))
    for m in r.mentions:
        n = m.normalized
        canon = n.canonical if n else None
        print(
            f'  {m.kind:8s} ex={m.extractor:12s} {m.value!r} -> {canon!r} '
            f'ev={json.dumps(m.evidence, ensure_ascii=False)[:160]}'
        )


for f in ["bio_ru.txt", "bio_en.txt", "cp1251_page.html", "profile.html", "corrupt.bin", "contact.html", "sample.pdf", "sample_exif.jpg", "sample.docx"]:
    try:
        dump(f)
    except Exception as e:
        print(f"[{f}] ERR {type(e).__name__}: {e}")
