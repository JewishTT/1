"""One-off: turn a pytest verbose run into the WP0 baseline failure artifact."""

from __future__ import annotations

import json
import pathlib
import re
from collections import OrderedDict

SRC = pathlib.Path("tmp/baseline_verbose.txt")
OUT = pathlib.Path("specs/032-global-upgrade-execution/benchmarks/WP0-baseline-failures.json")

lines = SRC.read_text(encoding="utf-8", errors="replace").splitlines()

failed_ids = [
    m.group(1)
    for m in (re.match(r"^(apps/\S+::\S+) FAILED", line) for line in lines)
    if m
]

details: list[tuple[str, str, str]] = []
for index, line in enumerate(lines):
    match = re.match(r"^E   (.+)$", line)
    if not match:
        continue
    message = match.group(1).strip()
    location = ""
    error = ""
    for follow in lines[index + 1 : index + 4]:
        loc = re.match(r"^([A-Za-z]:\\[^:]+):(\d+): (.+)$", follow.strip())
        if loc:
            location = f"{loc.group(1).split(chr(92))[-1]}:{loc.group(2)}"
            error = loc.group(3).split(":")[0].strip()
            break
    details.append((message, location, error))

if len(details) != len(failed_ids):
    raise SystemExit(f"pairing mismatch: {len(details)} details vs {len(failed_ids)} ids")


INFRA_MARKERS = (
    "503 ==",
    "KeyError: 'entity'",
    "in []",
)


def classify(message: str, error: str, test_id: str) -> str:
    if "nothing is guarding that invariant" in message:
        return "gap"
    if "layer_boundaries" in test_id:
        return "gap"
    if error in {"AttributeError", "NameError"}:
        return "defect"
    if error == "IndexError":
        return "defect"
    if any(marker in message for marker in INFRA_MARKERS):
        return "infra"
    if "BLOCKED_BUDGET" in message or "offsets must be distinct" in message:
        return "defect"
    if "assert False is True" in message:
        return "defect"
    return "unclassified"


records: "OrderedDict[str, dict]" = OrderedDict()
for test_id, (message, location, error) in zip(failed_ids, details):
    file_path = test_id.split("::")[0]
    records.setdefault(file_path, {"file": file_path, "failures": []})["failures"].append(
        {
            "test": test_id,
            "error": error or "AssertionError",
            "location": location,
            "message": message[:220],
            "category": classify(message, error, test_id),
        }
    )

summary = {"infra": 0, "defect": 0, "gap": 0, "unclassified": 0}
for entry in records.values():
    for failure in entry["failures"]:
        summary[failure["category"]] += 1

artifact = {
    "schema": "wp0-baseline-failures/1",
    "command": "python -m pytest -q -p no:randomly",
    "rootdir": "C:\\Users\\tim\\Desktop\\COGNITIVE\\1",
    "exit_status": 1,
    "collected": 5622,
    "passed": 5506,
    "failed": 38,
    "skipped": 79,
    "errors": 0,
    "duration_seconds": 2846,
    "collection_command": "python -m pytest --co -q",
    "collection_errors": 0,
    "category_totals": summary,
    "files": list(records.values()),
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", OUT, summary, "files", len(records))
