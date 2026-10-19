"""Build the WP0 owner map: who writes each canonical object (T007/T008).

The blueprint's invariant is one canonical owner per object. Finding a second writer
is the point of the exercise, so the map must be built from *write sites*, not from
whoever the documentation says owns the table.

How a writer is detected: a production module references a schema class **and**
contains a write verb near it (``.add(``, ``.merge(``, ``insert(``, ``upsert``,
``bulk_save``, ``commit(``, or a raw ``INSERT INTO``). That is a static heuristic, so
the output says "candidate writers" and lists the evidence line. A reviewer confirms;
the generator does not pretend to know intent.

What it does answer exactly: whether a table has **one** candidate writer file, several,
or none. Several is the defect. None is the other defect — an object nobody writes.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "apps"
SCHEMA = ROOT / "apps/control-plane/db/schema.py"
OUT_MD = ROOT / "specs/032-global-upgrade-execution/benchmarks/WP0-owner-map.md"
OUT_JSON = ROOT / "specs/032-global-upgrade-execution/benchmarks/WP0-owner-map.json"

WRITE_VERBS = (
    ".add(",
    ".add_all(",
    ".merge(",
    ".commit(",
    ".flush(",
    "insert(",
    "upsert",
    "bulk_save",
    "bulk_insert",
    "INSERT INTO",
)

#: The objects the blueprint makes claims about. Each maps to the schema class that
#: stores it; ``None`` means "no table yet", which is itself a finding.
CANONICAL_OBJECTS: dict[str, str | None] = {
    "raw artifact": None,
    "capture": None,
    "observation": "Observation",
    "mention": "Mention",
    "candidate": "Candidate",
    "entity": "Entity",
    "entity version": "EntityVersion",
    "investigation membership": "InvestigationEntityMembership",
    "assertion": "Assertion",
    "evidence link": "EvidenceLink",
    "admission decision": "AdmissionDecisionRow",
    "calibration profile": "CalibrationProfile",
    "projection": "Projection",
    "finding": "Finding",
    "audit log": "AuditLog",
    "acquisition task": "AcquisitionTask",
    "frontier item": "FrontierItem",
    "investigation": "Investigation",
    "source": "Source",
}


def _schema_classes() -> list[str]:
    text = SCHEMA.read_text(encoding="utf-8", errors="replace")
    return re.findall(r"^class (\w+)\(", text, re.MULTILINE)


def _production_files() -> list[Path]:
    found: list[Path] = []
    for path in APPS.rglob("*.py"):
        parts = path.parts
        if "__pycache__" in parts or "tests" in parts or path.name.startswith("test_"):
            continue
        found.append(path)
    return found


def _write_sites(path: Path, class_name: str) -> list[tuple[int, str]]:
    """Lines in ``path`` that look like a write to ``class_name``'s table."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    hits: list[tuple[int, str]] = []
    for index, line in enumerate(lines, start=1):
        if class_name not in line:
            continue
        # A write on the same line, or within the following 6 lines (a multi-line
        # ``session.add(Model(`` is the common shape).
        window = "\n".join(lines[index - 1 : index + 6])
        if any(verb in window for verb in WRITE_VERBS):
            hits.append((index, line.strip()[:160]))
    return hits


def _table_of(class_name: str) -> str | None:
    """``__tablename__`` for a schema class, read from its body."""
    text = SCHEMA.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        rf"^class {re.escape(class_name)}\(.*?^class |\Z",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return None
    table = re.search(r'__tablename__\s*=\s*"([^"]+)"', match.group(0))
    return table.group(1) if table else None


def build() -> list[dict[str, object]]:
    known = set(_schema_classes())
    files = _production_files()
    rows: list[dict[str, object]] = []
    for obj, class_name in CANONICAL_OBJECTS.items():
        if class_name is None:
            rows.append(
                {
                    "object": obj,
                    "schema_class": None,
                    "table": None,
                    "owner_app": None,
                    "writers": [],
                    "competing": False,
                    "status": "NO_TABLE_NAMED",
                    "note": "not a table: the raw bytes live in content-addressed object storage; the record that addresses them is the capture+observation pair",
                }
            )
            continue
        if class_name not in known:
            rows.append(
                {
                    "object": obj,
                    "schema_class": class_name,
                    "table": None,
                    "owner_app": "control-plane",
                    "writers": [],
                    "competing": False,
                    "status": "CLASS_ABSENT",
                    "note": f"{class_name} is not defined in db/schema.py",
                }
            )
            continue
        writers: list[dict[str, object]] = []
        for path in files:
            hits = _write_sites(path, class_name)
            if hits:
                writers.append(
                    {
                        "file": path.relative_to(ROOT).as_posix(),
                        "lines": [line for line, _ in hits],
                        "evidence": hits[0][1],
                    }
                )
        writers.sort(key=lambda w: w["file"])
        rows.append(
            {
                "object": obj,
                "schema_class": class_name,
                "table": _table_of(class_name),
                "owner_app": "control-plane",
                "writers": writers,
                "competing": len(writers) > 1,
                "status": (
                    "COMPETING_WRITERS"
                    if len(writers) > 1
                    else "SINGLE_WRITER"
                    if len(writers) == 1
                    else "NO_DIRECT_WRITER_FOUND"
                ),
                "note": "",
            }
        )
    return rows


def render(rows: list[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["status"])
        counts[key] = counts.get(key, 0) + 1

    lines = [
        "# WP0 Owner Map",
        "",
        "**Feature**: `032-global-upgrade-execution` · **Generated by**: `tools/specs/build_owner_map.py`",
        "",
        "One canonical owner per object is the blueprint's §2 invariant. This map is built from",
        "**write sites**, not from documentation, because the failure it looks for is the second",
        "writer nobody documented.",
        "",
        "A *candidate writer* is a production file that names the schema class and contains a write",
        "verb within six lines. That is a heuristic: the generator does not read intent, so a row",
        "marked `COMPETING_WRITERS` is a question for a reviewer, not a verdict. A row marked",
        "`SINGLE_WRITER` is also a question — it may be the only writer, or the others may write",
        "through a helper that does not name the class.",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    lines += [f"| `{key}` | {counts[key]} |" for key in sorted(counts)]
    lines += [f"| **total** | **{len(rows)}** |", "", "## Map", ""]
    lines += [
        "| Object | Table | Status | Writers |",
        "|---|---|---|---|",
    ]
    for row in rows:
        writers = row["writers"]  # type: ignore[assignment]
        shown = ", ".join(f"`{w['file']}`" for w in writers[:2]) or "—"  # type: ignore[index]
        if len(writers) > 2:  # type: ignore[arg-type]
            shown += f" (+{len(writers) - 2})"  # type: ignore[arg-type]
        lines.append(
            f"| {row['object']} | `{row['table'] or '—'}` | `{row['status']}` | {shown} |"
        )

    lines += ["", "## Objects with competing writers", ""]
    competing = [row for row in rows if row["status"] == "COMPETING_WRITERS"]
    if not competing:
        lines.append("None found by static analysis.")
    for row in competing:
        lines.append(f"### {row['object']} (`{row['table']}`)")
        lines.append("")
        for writer in row["writers"]:  # type: ignore[attr-defined]
            lines.append(
                f"- `{writer['file']}`:{writer['lines'][0]} — `{writer['evidence']}`"
            )
        lines.append("")

    lines += ["", "## Objects with no table or no writer", ""]
    empty = [row for row in rows if row["status"] in {"NO_TABLE_NAMED", "CLASS_ABSENT", "NO_DIRECT_WRITER_FOUND"}]
    if not empty:
        lines.append("None.")
    for row in empty:
        lines.append(f"- **{row['object']}** — `{row['status']}`. {row['note'] or 'No production writer found.'}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rows = build()
    if args.check:
        if not OUT_JSON.is_file():
            print("owner map JSON is missing")
            return 1
        if json.loads(OUT_JSON.read_text(encoding="utf-8")) != rows:
            print("owner map is out of date; rerun without --check")
            return 1
        print("owner map is up to date")
        return 0

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render(rows), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
    print(f"wrote {OUT_MD.relative_to(ROOT)}: {len(rows)} objects {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
