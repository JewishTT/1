"""Architecture Evidence Graph — minimal, fact-only.

Only emits facts derivable from AST/imports/routes/schema/tests/specs.
No inference of "should be", no guessed event consumers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _evidence_id(kind: str, subject: str, obj: str, extra: str = "") -> str:
    base = f"{kind}|{subject}|{obj}|{extra}"
    import hashlib
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def collect_facts(root: Path, model: dict) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    py_modules = {m["path"]: m for m in model["python"]["modules"]}
    ts_modules = {m["path"]: m for m in model["typescript"]["modules"]}
    # MODULE_IMPORTS_MODULE from resolved edges
    for e in model["import_graph"]["edges"]:
        facts.append({
            "fact_id": _evidence_id("MODULE_IMPORTS_MODULE", e["from"], e["to"], e.get("via", "")),
            "kind": "MODULE_IMPORTS_MODULE",
            "subject": e["from"],
            "object": e["to"],
            "status": "STATIC_FACT",
            "method": "python_ast+import_resolution",
            "evidence": {"file": e["from"], "via": e.get("via")},
            "confidence": 1.0,
        })
    # ROUTE_DEFINED_IN (from api scan)
    for router in model.get("api", []):
        router_file = None
        # find first route file
        for r in router.get("routes", []):
            # routes list in semantic has files? scan_api stores router info; look up
            pass
    # better: scan routes files
    import re
    routes_base = root / "apps" / "control-plane" / "api" / "routes"
    if routes_base.exists():
        rx = re.compile(r'@(?:router|app)\.(get|post|put|delete|patch|head|options)\s*\(\s*["\']([^"\']+)["\']', re.M)
        for p in routes_base.rglob("*.py"):
            txt = p.read_text(encoding="utf-8", errors="replace")
            rel = p.relative_to(root).as_posix()
            for m in rx.finditer(txt):
                facts.append({
                    "fact_id": _evidence_id("ROUTE_DEFINED_IN", m.group(2), rel, m.group(1).upper()),
                    "kind": "ROUTE_DEFINED_IN",
                    "subject": f"{m.group(1).upper()} {m.group(2)}",
                    "object": rel,
                    "status": "STATIC_FACT",
                    "method": "regex_decorator",
                    "evidence": {"file": rel, "line": txt[:m.start()].count("\n")+1},
                    "confidence": 1.0,
                })
    # TABLE_CLASS_DEFINED
    for p in root.rglob("schema.py"):
        rel = p.relative_to(root).as_posix()
        if "apps" not in rel:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in re.finditer(r'class\s+([A-Za-z][A-Za-z0-9_]*)\s*\(.*Base.*\)', txt):
            facts.append({
                "fact_id": _evidence_id("TABLE_CLASS_DEFINED", m.group(1), rel),
                "kind": "TABLE_CLASS_DEFINED",
                "subject": m.group(1),
                "object": rel,
                "status": "STATIC_FACT",
                "method": "regex_class_base",
                "evidence": {"file": rel},
                "confidence": 1.0,
            })
    # TEST_TARGETS_MODULE
    for t in model["tests"]["by_file"]:
        if not isinstance(t, dict):
            continue
        tpath = t["path"]
        targets = t.get("targets") or []
        for tgt in targets:
            facts.append({
                "fact_id": _evidence_id("TEST_TARGETS_MODULE", tpath, tgt),
                "kind": "TEST_TARGETS_MODULE",
                "subject": tpath,
                "object": tgt,
                "status": "STATIC_FACT",
                "method": "import_and_name_scan",
                "evidence": {"file": tpath},
                "confidence": 1.0,
            })
    # SPEC_EXISTS
    specs_dir = root / "specs"
    if specs_dir.exists():
        for p in specs_dir.glob("*/spec.md"):
            rel = p.relative_to(root).as_posix()
            facts.append({
                "fact_id": _evidence_id("SPEC_EXISTS", p.parent.name, rel),
                "kind": "SPEC_EXISTS",
                "subject": p.parent.name,
                "object": rel,
                "status": "STATIC_FACT",
                "method": "filesystem",
                "evidence": {"file": rel},
                "confidence": 1.0,
            })
    # CAPABILITY_DECLARED
    for c in model.get("capabilities", []):
        facts.append({
            "fact_id": _evidence_id("CAPABILITY_DECLARED", c["id"], c.get("module", "")),
            "kind": "CAPABILITY_DECLARED",
            "subject": c["id"],
            "object": c.get("module", ""),
            "status": "INTENDED" if not c.get("exists") else "STATIC_FACT",
            "method": "wp0_capability_matrix",
            "evidence": {"source": "specs/032-global-upgrade-execution/benchmarks/WP0-capability-matrix.json"},
            "confidence": 1.0,
        })
    # CONTEXT_DEPENDENCY -- from the architecture compiler. Some of these edges are
    # hand-coded in platform_model/architecture.py, so they are INFERRED, not facts
    # read straight from the tree. Marking them honestly is the point.
    arch = model.get("architecture", {})
    for e in arch.get("context_map", {}).get("edges", []):
        facts.append({
            "fact_id": _evidence_id("CONTEXT_DEPENDENCY", e.get("from", ""), e.get("to", ""), e.get("type", "")),
            "kind": "CONTEXT_DEPENDENCY",
            "subject": e.get("from", ""),
            "object": e.get("to", ""),
            "status": "INFERRED",
            "method": f"architecture_compiler:{e.get('type', 'direct')}",
            "evidence": {"via_import": e.get("via_import"), "event": e.get("event")},
            "confidence": 0.6,
        })
    # SPEC_CITES_MODULE -- traceability link (docstring reference). INFERRED.
    for s in arch.get("spec_traceability", {}).get("specs", []):
        for m in s.get("modules", []):
            facts.append({
                "fact_id": _evidence_id("SPEC_CITES_MODULE", s["id"], m),
                "kind": "SPEC_CITES_MODULE",
                "subject": s["id"],
                "object": m,
                "status": "INFERRED",
                "method": "docstring_reference",
                "evidence": {"spec": s.get("spec_path")},
                "confidence": 0.7,
            })
    return facts


def build_evidence(root: Path, model: dict) -> dict[str, Any]:
    facts = collect_facts(root, model)
    static_facts = sum(1 for f in facts if f.get("status") == "STATIC_FACT")
    inferred = sum(1 for f in facts if f.get("status") == "INFERRED")
    intended = sum(1 for f in facts if f.get("status") == "INTENDED")
    return {
        "facts": facts,
        "stats": {
            "facts_total": len(facts),
            "static_facts": static_facts,
            "inferred": inferred,
            "intended": intended,
        },
    }
