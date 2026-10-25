"""Golden-path readiness: check the required capabilities against the tree.

Reads ``platform_model/golden_path.yaml`` (the hybrid manifest: specs + philosophy)
and, for every required capability, resolves each probe against the model and the
filesystem. The result is a per-capability status:

``READY``      present, production-reachable, not a stub
``PARTIAL``    present but primitive, or only partly wired
``STUB``       present but the body is a stub / NotImplementedError
``TEST_ONLY``  reached only by tests -- production never runs it
``ORPHAN``     imported by nothing -- dead or unwired
``MISSING``    a required module does not exist

This is what turns "the platform is large" into "here is exactly where the golden
path breaks".
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parent / "golden_path.yaml"

#: statuses ordered worst-first for reporting and the build plan.
STATUS_ORDER = ("MISSING", "ORPHAN", "TEST_ONLY", "STUB", "PARTIAL", "READY")


def _load_manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _file_has(path: Path, regex: str) -> bool:
    if not path.exists():
        return False
    try:
        return re.search(regex, path.read_text(encoding="utf-8", errors="replace"), re.M) is not None
    except OSError:
        return False


def build_golden_path(root: Path, model: dict) -> dict:
    manifest = _load_manifest()
    modules = {m["path"] for m in model["python"]["modules"]}
    maturity = {r["path"]: r["status"] for r in model.get("maturity", {}).get("modules", [])}
    reach = {r["path"]: r["status"] for r in model.get("reachability", {}).get("modules", [])}

    layers_out: list[dict] = []
    for layer in manifest["layers"]:
        caps_out: list[dict] = []
        for cap in layer["capabilities"]:
            primary = None
            missing: list[str] = []
            symbol_ok = True
            for probe in cap["probes"]:
                path = probe["path"]
                kind = probe["kind"]
                if kind == "module":
                    if path not in modules and not (root / path).exists():
                        missing.append(path)
                    elif primary is None:
                        primary = path
                elif kind == "symbol":
                    if not _file_has(root / path, probe["regex"]):
                        symbol_ok = False
                elif kind == "reachable":
                    if primary is None:
                        primary = path
            if missing:
                status = "MISSING"
            elif not symbol_ok:
                status = "PARTIAL"
            else:
                r = reach.get(primary) if primary else None
                mat = maturity.get(primary) if primary else None
                if r == "ORPHAN":
                    status = "ORPHAN"
                elif r == "TEST_ONLY":
                    status = "TEST_ONLY"
                elif mat in ("STUB", "NOT_IMPLEMENTED"):
                    status = "STUB"
                elif mat == "PRIMITIVE":
                    status = "PARTIAL"
                else:
                    status = "READY"
            caps_out.append({
                "id": cap["id"],
                "title": cap["title"],
                "why": cap.get("why", ""),
                "status": status,
                "primary": primary,
                "missing": missing,
                "reachability": reach.get(primary) if primary else None,
                "maturity": maturity.get(primary) if primary else None,
            })
        layers_out.append({"id": layer["id"], "title": layer["title"], "capabilities": caps_out})

    tally: dict[str, int] = {s: 0 for s in STATUS_ORDER}
    for layer in layers_out:
        for c in layer["capabilities"]:
            tally[c["status"]] += 1
    total = sum(tally.values())

    return {
        "goal": manifest.get("goal", ""),
        "layers": layers_out,
        "summary": {**tally, "total": total},
    }


def build_plan(golden: dict) -> list[dict]:
    """Ordered workstreams: every non-READY capability, worst-first within its layer."""
    plan: list[dict] = []
    for layer in golden["layers"]:
        broken = [c for c in layer["capabilities"] if c["status"] != "READY"]
        broken.sort(key=lambda c: (STATUS_ORDER.index(c["status"]), c["id"]))
        if broken:
            plan.append({
                "layer": layer["id"],
                "title": layer["title"],
                "items": broken,
            })
    return plan
