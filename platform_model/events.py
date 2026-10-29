"""Event coverage: for every catalogued event type, is it produced and consumed?

The catalog (``apps/shared/events/topics.py``) declares ~100 event types. A type
that appears only in the catalog is an event nobody emits or reads. This analyzer
makes one pass over the tree and counts, per type, the files that mention the
literal and the files that mention it on a line that also says publish/emit/produce.

It is a textual count, not a call-graph proof; it is labelled as such.
"""

from __future__ import annotations

import re
from pathlib import Path

_PRODUCER = re.compile(r"publish|emit|produce|send", re.I)


def _catalog_types(root: Path) -> dict[str, str]:
    txt = (root / "apps" / "shared" / "events" / "topics.py").read_text(encoding="utf-8", errors="replace")
    return {m.group(1): m.group(2) for m in re.finditer(r'"([a-z][a-z0-9_.]+)"\s*:\s*"([a-z0-9_.-]+)"', txt)}


def build_event_coverage(root: Path, model: dict) -> dict:
    catalog = _catalog_types(root)
    # one alternation, longest-first so ``a.b.c`` wins over ``a.b``
    pattern = re.compile("|".join(re.escape(t) for t in sorted(catalog, key=len, reverse=True)))
    hits: dict[str, int] = {t: 0 for t in catalog}
    producers: dict[str, int] = {t: 0 for t in catalog}
    for m in model["python"]["modules"]:
        rel = m["path"]
        if rel.endswith("events/topics.py"):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seen = {mm.group(0) for mm in pattern.finditer(text)}
        for t in seen:
            hits[t] += 1
        if seen:
            for line in text.splitlines():
                if not _PRODUCER.search(line):
                    continue
                for t in seen:
                    if t in line:
                        producers[t] += 1
    unreferenced = sorted(t for t in catalog if not hits[t])
    produced = sorted(t for t in catalog if producers[t])
    return {
        "total": len(catalog),
        "lanes": len(set(catalog.values())),
        "produced": len(produced),
        "unreferenced": unreferenced,
        "by_type": {t: {"lane": catalog[t], "files": hits[t], "producer_files": producers[t]} for t in sorted(catalog)},
    }
