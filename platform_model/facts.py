"""Raw fact extraction from source tree. No inference, no 'should be'."""
from __future__ import annotations

import json
import re
from pathlib import Path


SCAN_ROOTS = ("apps", "bench", "tools", "deploy", "platform_model")
EXTRA_ROOT_FILES = ("conftest.py", "pyproject.toml", "README.md")


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def collect_fs(root: Path) -> dict:
    items = []
    for base in SCAN_ROOTS:
        b = root / base
        if not b.exists():
            continue
        for p in b.rglob("*"):
            if any(part in p.parts for part in (".venv", "node_modules", "__pycache__", "dist", "build")):
                continue
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                items.append({"path": rel, "ext": p.suffix, "size": p.stat().st_size})
    for name in EXTRA_ROOT_FILES:
        p = root / name
        if p.exists() and p.is_file():
            items.append({"path": name, "ext": p.suffix, "size": p.stat().st_size})
    return {"files": sorted(items, key=lambda x: x["path"]), "count": len(items)}


def collect_routes(root: Path) -> list:
    routes = []
    base = root / "apps" / "control-plane" / "api" / "routes"
    if not base.exists():
        return routes
    rx = re.compile(r'@(?:router|app)\.(get|post|put|delete|patch|head|options)\s*\(\s*["\']([^"\']+)["\']', re.M)
    for p in sorted(base.rglob("*.py")):
        txt = _read(p)
        for m in rx.finditer(txt):
            routes.append({"file": p.relative_to(root).as_posix(), "method": m.group(1).upper(), "path": m.group(2), "line": txt[:m.start()].count("\n") + 1})
    return routes


def collect_dbschema(root: Path) -> dict:
    out = {"files": [], "tables": [], "enums": [], "migrations": []}
    for p in root.rglob("schema.py"):
        rel = p.relative_to(root).as_posix()
        if "apps" not in rel:
            continue
        out["files"].append(rel)
        txt = _read(p)
        for m in re.finditer(r'class\s+([A-Za-z][A-Za-z0-9_]*)\s*\(.*Base.*\)', txt):
            out["tables"].append({"class": m.group(1), "file": rel})
        for m in re.finditer(r'class\s+([A-Za-z][A-Za-z0-9_]*)\(str,\s*enum\.Enum\)', txt):
            out["enums"].append({"class": m.group(1), "file": rel})
    migdir = root / "apps" / "control-plane" / "db" / "migrations" / "versions"
    if migdir.exists():
        out["migrations"] = sorted([p.name for p in migdir.glob("*.py") if not p.name.startswith("__")])
    return out


def collect_migrations_count(root: Path) -> list:
    migdir = root / "apps" / "control-plane" / "db" / "migrations" / "versions"
    if not migdir.exists():
        return []
    out = []
    for p in sorted(migdir.glob("*.py")):
        if p.name.startswith("__"):
            continue
        txt = _read(p)
        out.append({"file": p.name, "has_upgrade": "def upgrade" in txt, "has_downgrade": "def downgrade" in txt})
    return out


def collect_services_repos(root: Path) -> list:
    out = []
    for pat in ("apps/*/services/*.py", "apps/*/*/services/*.py"):
        for p in root.glob(pat):
            rel = p.relative_to(root).as_posix()
            name = p.stem
            if re.search(r'(Service|Repository|Store)$', name):
                out.append({"type": "service_or_repo_or_store", "name": name, "path": rel})
    for p in root.glob("apps/*/db/*_store.py"):
        rel = p.relative_to(root).as_posix()
        out.append({"type": "store", "name": p.stem, "path": rel})
    for p in root.glob("apps/*/db/*repository*.py"):
        rel = p.relative_to(root).as_posix()
        out.append({"type": "repository", "name": p.stem, "path": rel})
    return sorted(out, key=lambda x: x["path"])


def collect_events_topics(root: Path) -> dict:
    out = {"files": [], "topics": [], "event_names": []}
    for p in root.rglob("topics.py"):
        rel = p.relative_to(root).as_posix()
        out["files"].append(rel)
        txt = _read(p)
        for m in re.finditer(r'([A-Z][A-Z0-9_]+)\s*=\s*["\']([^"\']+)["\']', txt):
            out["topics"].append({"name": m.group(1), "value": m.group(2), "file": rel})
    for p in root.rglob("kafka.py"):
        rel = p.relative_to(root).as_posix()
        if "site-packages" not in rel:
            out["files"].append(rel)
    for p in root.rglob("events/*.py"):
        rel = p.relative_to(root).as_posix()
        if "site-packages" not in rel:
            out["files"].append(rel)
    return out


def collect_entrypoints(root: Path) -> dict:
    out = {"fastapi_apps": [], "main": []}
    for p in root.rglob("main.py"):
        rel = p.relative_to(root).as_posix()
        if "apps/" in rel and "site-packages" not in rel:
            out["main"].append(rel)
    for p in root.rglob("app.py"):
        rel = p.relative_to(root).as_posix()
        if "apps/" in rel and "site-packages" not in rel:
            out["main"].append(rel)
    for p in root.rglob("api/main.py"):
        rel = p.relative_to(root).as_posix()
        if "apps/" in rel and "site-packages" not in rel:
            out["fastapi_apps"].append(rel)
    return out


def collect_configs(root: Path) -> list:
    out = []
    for pat in ["**/settings*.py", "**/config/*.py", "**/docker-compose*.yml", "**/docker-compose*.yaml"]:
        for p in root.glob(pat):
            if any(x in p.parts for x in (".venv", "node_modules")):
                continue
            rel = p.relative_to(root).as_posix()
            out.append(rel)
    return sorted(set(out))


def collect_cap_owner_donor(root: Path) -> dict:
    bench = root / "specs" / "032-global-upgrade-execution" / "benchmarks"
    out = {}
    for name in ["WP0-capability-matrix.json", "WP0-owner-map.json", "WP0-baseline-failures.json", "WP0-baseline.md", "WP0-signoff.md"]:
        p = bench / name
        if p.exists():
            if p.suffix == ".json":
                try:
                    out[name] = json.loads(_read(p))
                except Exception:
                    out[name] = None
            else:
                out[name] = _read(p)
    d = root / "donors" / "registry.yaml"
    if d.exists():
        out["donors_registry.yaml"] = _read(d)
    return out


def collect_pyproject_deps(root: Path) -> dict:
    out = {}
    for p in [root / "pyproject.toml"] + sorted(root.glob("apps/*/pyproject.toml")) + sorted(root.glob("bench/pyproject.toml")):
        if not p.exists():
            continue
        rel = p.relative_to(root).as_posix()
        out[rel] = _read(p)
    return out


def build_facts(root: Path, model: dict) -> dict:
    return {
        "generated_from": str(root),
        "purpose": "Raw factual snapshot of the platform as it exists now. No inference, no recommendations.",
        "fs": collect_fs(root),
        "entrypoints": collect_entrypoints(root),
        "routes": collect_routes(root),
        "db": collect_dbschema(root),
        "migrations": collect_migrations_count(root),
        "services_repos_stores": collect_services_repos(root),
        "events_topics": collect_events_topics(root),
        "configs": collect_configs(root),
        "pyproject": collect_pyproject_deps(root),
        "capability_owner_donor": collect_cap_owner_donor(root),
        "import_graph_summary": {
            "modules_python": model["python"]["count"],
            "modules_ts": model["typescript"]["count"],
            "edges": model["import_graph"]["edge_count"],
            "unresolved": len(model["import_graph"]["unresolved"]),
            "external": model["import_graph"]["external"],
            "roots": model["import_graph"].get("roots", {}),
        },
        "components": model["components"],
        "api_routers": model.get("api", []),
        "tests_summary": {"files": len(model["tests"]["by_file"]), "total": model["tests"]["total"]},
    }
