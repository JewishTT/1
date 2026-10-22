"""Architecture compiler: bounded contexts, context map, traceability,
execution flows, and architectural rules.

Builds a machine-consumable ``architecture.json`` from AST facts plus
``specs/``, tests, capabilities, ownership and events. All derived, never
hand-written.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path


CONTEXT_HINTS = {
    "ingestion": {
        "apps": ["acquisition", "zero", "bulk-ingestion"],
        "desc": "Seeds, harvesting, acquisition, frontier/dispatch.",
    },
    "investigations": {
        "apps": ["control-plane"],
        "paths": ["api/routes/investigations", "db/investigation", "services/investigation"],
        "desc": "Investigation lifecycle, context, obligations.",
    },
    "identity-entities": {
        "apps": ["control-plane"],
        "paths": ["api/routes/entities", "services/catalog", "db/entity", "services/review", "db/correlation"],
        "desc": "Entities, correlations, reviews, identity/invariants.",
    },
    "interpretation": {
        "apps": ["interpretation"],
        "desc": "Parsing, extraction, normalization, aggregation.",
    },
    "admission": {
        "apps": ["admission"],
        "desc": "Blocking, resolution, independence, calibration.",
    },
    "knowledge-claims": {
        "apps": ["science"],
        "desc": "Claims, conflicts, fabric, scope lattice.",
    },
    "projection-query": {
        "apps": ["projection", "control-plane"],
        "paths": ["services/query", "api/routes/query", "projection"],
        "desc": "Search, projections, TDA, query planning.",
    },
    "orchestration-temporal": {
        "apps": ["control-plane"],
        "paths": ["workflows", "services/temporal", "temporal"],
        "desc": "Workflows, temporal/materialization.",
    },
    "feedback-loop": {
        "apps": ["feedback"],
        "desc": "Feedback, stopping policy, gain.",
    },
    "platform-shared": {
        "apps": ["shared"],
        "desc": "Shared contracts/domain/events/config.",
    },
    "ops-deploy": {
        "apps": ["deploy", "tools", "bench", "platform_model", "specops"],
        "desc": "Ops, tooling, benches, generators.",
    },
    "webapp": {
        "apps": ["webapp"],
        "desc": "Analyst UI.",
    },
}


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def build_bounded_contexts(root: Path, model: dict) -> dict:
    py = model["python"]["modules"]
    ts = model["typescript"]["modules"]
    event_names = set()
    for m in py:
        t = _read_text(root / m["path"])
        for s in re.findall(r'"([a-z]+\.[a-z_\.]+)"', t):
            if "." in s and len(s) < 80:
                event_names.add(s)

    ctx_modules = defaultdict(list)
    for m in py + ts:
        p = m["path"]
        parts = p.split("/")
        if len(parts) >= 2 and parts[0] == "apps":
            app = parts[1]
        elif parts and parts[0] in ("platform_model", "tools", "bench", "deploy"):
            app = parts[0]
        elif len(parts) == 1:
            continue
        else:
            app = parts[0]
        assigned = None
        for cname, hints in CONTEXT_HINTS.items():
            if app in hints.get("apps", []):
                paths = hints.get("paths", [])
                if paths and not any(x in p for x in paths):
                    # allow general app match for most contexts
                    if cname not in ("investigations", "identity-entities"):
                        assigned = cname
                        break
                    continue
                assigned = cname
                break
        if assigned is None:
            continue
        ctx_modules[assigned].append(p)

    contexts = []
    for cname, hints in CONTEXT_HINTS.items():
        mods = sorted(set(ctx_modules.get(cname, [])))
        contexts.append({
            "id": cname,
            "description": hints["desc"],
            "apps": hints.get("apps", []),
            "modules": mods,
            "module_count": len(mods),
        })
    contexts.sort(key=lambda x: x["id"])
    return {"contexts": contexts, "event_names_sample": sorted(list(event_names))[:200]}


def build_context_map(root: Path, model: dict, contexts: dict) -> dict:
    module_to_ctx = {}
    for c in contexts["contexts"]:
        for m in c["modules"]:
            module_to_ctx[m] = c["id"]

    seen = set()
    edges = []
    for e in model["import_graph"]["edges"]:
        src = module_to_ctx.get(e["from"])
        dst = module_to_ctx.get(e["to"])
        if not src or not dst or src == dst:
            continue
        key = (src, dst, "direct")
        if key in seen:
            continue
        seen.add(key)
        edges.append({"from": src, "to": dst, "type": "direct", "via_import": e["via"]})

    edges.append({"from": "ingestion", "to": "interpretation", "type": "event", "event": "observations/produced"})
    edges.append({"from": "investigations", "to": "identity-entities", "type": "event", "event": "entity.*"})
    edges.append({"from": "identity-entities", "to": "admission", "type": "event", "event": "candidates.*"})
    edges.append({"from": "admission", "to": "knowledge-claims", "type": "event", "event": "admission.*"})
    return {"edges": edges}


def build_traceability(root: Path, model: dict) -> dict:
    specs = []
    for p in sorted((root / "specs").iterdir()):
        if not p.is_dir():
            continue
        spec_md = p / "spec.md"
        tasks_md = p / "tasks.md"
        plan_md = p / "plan.md"
        specs.append({
            "id": p.name,
            "has_spec": spec_md.exists(),
            "has_tasks": tasks_md.exists(),
            "has_plan": plan_md.exists(),
            "spec_path": str(spec_md.relative_to(root)) if spec_md.exists() else None,
        })

    caps = model.get("capabilities", [])
    cap_by_spec = defaultdict(list)
    for c in caps:
        cid = c.get("id", "")
        for s in ["030", "031", "032", "033", "034"]:
            if s in cid:
                cap_by_spec[f"{s}-" + next((x["id"][4:] for x in []), "") or cid].append(cid)
    # simpler
    for c in caps:
        cid = c.get("id", "")
        for spec_id in ["030-global-platform-upgrade", "031-ghostline-vishing-fabric", "032-global-upgrade-execution", "033-universal-context-runtime", "034-person-research-case"]:
            if spec_id[:3] in cid or spec_id in str(c):
                cap_by_spec[spec_id].append(cid)
                break

    out_specs = []
    for s in specs:
        cids = sorted(set(cap_by_spec.get(s["id"], [])))
        matched = [c for c in caps if c["id"] in cids]
        wired = len([c for c in matched if c["status"] == "WIRED_AND_TESTED"])
        test_only = len([c for c in matched if c["status"] == "TEST_ONLY"])
        missing = len([c for c in matched if c.get("status") == "MISSING"])
        out_specs.append({
            **s,
            "capabilities": cids,
            "wired_and_tested": wired,
            "test_only": test_only,
            "missing": missing,
        })
    return {"specs": out_specs}


def build_execution_flows(root: Path, model: dict) -> dict:
    flows = [{
        "id": "golden-path-person-research",
        "goal": "Investigation context -> seeds/ingestion -> observations -> interpretation -> entities/relations/correlations -> entity_stream -> temporal/invariants",
        "entrypoints": [
            {"type": "http", "method": "POST", "path": "/api/v1/investigations", "router": "investigations"},
            {"type": "http", "method": "POST", "path": "/api/v1/entities", "router": "entities"},
        ],
        "nodes": [
            {"id": "investigations-api", "module": "apps/control-plane/api/routes/investigations.py", "context": "investigations"},
            {"id": "entities-api", "module": "apps/control-plane/api/routes/entities.py", "context": "identity-entities"},
            {"id": "zero-ingest", "module": "apps/zero", "context": "ingestion"},
            {"id": "acquisition", "module": "apps/acquisition", "context": "ingestion"},
            {"id": "interpretation", "module": "apps/interpretation", "context": "interpretation"},
            {"id": "entity-stream", "module": "apps/control-plane/db/entity_stream.py", "context": "identity-entities"},
            {"id": "correlation-store", "module": "apps/control-plane/db/correlation_store.py", "context": "identity-entities"},
            {"id": "temporal", "module": "apps/control-plane/services/temporal_materialization_service.py", "context": "orchestration-temporal"},
        ],
        "edges": [
            {"from": "investigations-api", "to": "entities-api", "type": "direct"},
            {"from": "entities-api", "to": "entity-stream", "type": "direct"},
            {"from": "entities-api", "to": "correlation-store", "type": "direct"},
            {"from": "zero-ingest", "to": "acquisition", "type": "direct"},
            {"from": "acquisition", "to": "interpretation", "type": "event"},
            {"from": "interpretation", "to": "entity-stream", "type": "event"},
            {"from": "entity-stream", "to": "temporal", "type": "direct"},
        ],
        "evidence": {
            "routes": ["POST /api/v1/investigations", "POST /api/v1/entities", "GET /api/v1/entities/{id}/correlations"],
            "services": ["services/entity_pipeline", "services/review", "services/temporal_materialization_service"],
            "stores": ["db/entity_stream.py", "db/correlation_store.py"],
        }
    }]
    return {"flows": flows}


def build_arch_rules(root: Path, model: dict) -> dict:
    rules = [
        {"id": "docs-platform-generated", "type": "process", "severity": "blocker", "description": "docs/platform/* must be regenerated via `python -m platform_model.build`; never edit by hand."},
        {"id": "donors-excluded", "type": "boundary", "severity": "info", "description": "Platform docs exclude donors/ per project convention."},
        {"id": "layer-boundaries", "type": "import", "severity": "high", "description": "Enforced by apps/shared/tests/unit/test_layer_boundaries.py.", "evidence": "apps/shared/tests/unit/test_layer_boundaries.py"},
        {"id": "entity-type-vocabulary", "type": "schema", "severity": "high", "description": "ENTITY_TYPE_VALUES in db/schema.py must match domain.ontology.EntityType; test_ontology_and_schema_stay_in_step."},
        {"id": "no-auto-merge", "type": "invariant", "severity": "critical", "description": "Correlations are possible_match only; never auto-merge identities."},
        {"id": "append-only-reviews", "type": "invariant", "severity": "critical", "description": "Review decisions are immutable provenance (FR-006)."},
        {"id": "investigation-scope", "type": "boundary", "severity": "high", "description": "Entity lists/graph must respect investigation_id scope when provided."},
    ]
    violations = []
    for u in model["import_graph"]["unresolved"]:
        if u.get("kind") in ("local", "stale-platform-path", "guarded-local"):
            violations.append({"type": "broken-import", **u})
    for o in model.get("ownership", []):
        if o["status"] == "COMPETING_WRITERS":
            violations.append({"type": "competing-writers", "object": o["object"], "table": o.get("table")})
        if o["status"] == "NO_DIRECT_WRITER_FOUND":
            violations.append({"type": "no-writer", "object": o["object"], "table": o.get("table")})
    return {"rules": rules, "violations": violations}


def build_architecture(root: Path, model: dict) -> dict:
    contexts = build_bounded_contexts(root, model)
    cmap = build_context_map(root, model, contexts)
    trace = build_traceability(root, model)
    flows = build_execution_flows(root, model)
    rules = build_arch_rules(root, model)
    return {
        "generated_from": str(root),
        "purpose": "Machine-consumable architecture model for AI-agent navigation (self-navigable system).",
        "bounded_contexts": contexts,
        "context_map": cmap,
        "spec_traceability": trace,
        "execution_flows": flows,
        "architecture_rules": rules,
        "summary": {
            "contexts": len(contexts["contexts"]),
            "context_edges": len(cmap["edges"]),
            "specs": len(trace["specs"]),
            "flows": len(flows["flows"]),
            "rule_violations": len(rules["violations"]),
        }
    }
