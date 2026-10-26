"""Machine-checked gaps registry.

The old ``KNOWN_GAPS`` was free text: the generator copied it into the README and
never checked whether any of it was still true, so it silently republished fixed
defects (a context engine that had moved to Postgres, a workflow that had been
registered, a downgrade that was not a ``NotImplementedError``). This module
replaces it.

Every entry is a *claim that a defect exists*, tied to evidence that can be
re-checked against the tree: a file and a regex that must (or must not) appear.
``verify()`` re-reads the tree and returns, per gap, one of:

``OPEN``      the evidence still holds -- the defect is real and unfixed
``RESOLVED``  the evidence no longer holds -- the defect is gone; the entry is stale
``STALE``     the cited file is missing -- the citation is wrong

The contract test asserts every gap is ``OPEN``. A ``RESOLVED`` or ``STALE`` gap
fails the build, which is the whole point: the registry cannot quietly rot.

``RESOLVED_CLAIMS`` is the mirror: claims that were once true and must stay fixed,
so a regression is caught rather than rediscovered.
"""

from __future__ import annotations

import re
from pathlib import Path


def _ev(path: str, regex: str, *, expect: str = "present", min_count: int = 1) -> dict:
    return {"path": path, "regex": regex, "expect": expect, "min_count": min_count}


#: Open defects, each with re-checkable evidence. Grouped by the golden-path layer
#: they block: ``0`` collection, ``1`` extraction/resolution, ``2`` context engine,
#: ``x`` cross-cutting.
GAPS: list[dict] = [
    # -- cross-cutting: security boundary ------------------------------------
    {
        "id": "roe-in-memory-registry",
        "layer": "x",
        "severity": "critical",
        "claim": "Rules-of-Engagement sign-off is written to an in-process registry, not durable storage.",
        "evidence": [_ev("apps/control-plane/api/routes/specops_roe.py", r"REGISTRY\.record\(roe\)")],
    },
    {
        "id": "roe-approved-by-from-body",
        "layer": "x",
        "severity": "high",
        "claim": "The RoE approver is taken from the request body, not a verified principal.",
        "evidence": [_ev("apps/control-plane/api/routes/specops_roe.py", r"approved_by=body\.approved_by")],
    },
    # -- cross-cutting: operational honesty ----------------------------------
    {
        "id": "metrics-hardcoded",
        "layer": "x",
        "severity": "high",
        "claim": "GET /api/v1/metrics returns hard-coded numbers, never measured.",
        "evidence": [_ev("apps/control-plane/api/routes/metrics.py", r"throughput_per_s=142\.3")],
    },
    {
        "id": "dlq-seeded-record",
        "layer": "x",
        "severity": "high",
        "claim": "GET /api/v1/dlq reads an in-process store seeded with one fake record.",
        "evidence": [_ev("apps/control-plane/api/routes/quarantine.py", r"malformed candidate")],
    },
    {
        "id": "health-is-constant",
        "layer": "x",
        "severity": "medium",
        "claim": "GET /health returns a constant and reflects no dependency availability.",
        "evidence": [_ev("apps/control-plane/api/main.py", r'"status": "ok", "service": "control-plane"')],
    },
    # -- cross-cutting: schema ownership -------------------------------------
    {
        "id": "create-tables-in-production-path",
        "layer": "x",
        "severity": "high",
        "claim": "Operational code creates schema with Base.metadata.create_all, not Alembic.",
        "evidence": [_ev("apps/control-plane/services/temporal_materialization_dispatch.py", r"await create_tables\(\)")],
    },
    {
        "id": "alembic-head-is-not-a-base",
        "layer": "x",
        "severity": "high",
        "claim": "The first Alembic revision has down_revision=None, so upgrade head builds no pre-014 table.",
        "evidence": [_ev("apps/control-plane/db/migrations/versions/014_temporal_materialization.py", r"down_revision = None")],
    },
    # -- cross-cutting: packaging / CI ---------------------------------------
    {
        "id": "wheel-packages-omit-context-engine",
        "layer": "x",
        "severity": "high",
        "claim": "The control-plane wheel omits context_engine/semantic_path, so an installed build differs from checkout.",
        "evidence": [_ev("apps/control-plane/pyproject.toml", r'packages = \["api", "application", "domain", "services", "db", "workflows", "badges", "modifier"\]')],
    },
    # -- layer 0: collection -------------------------------------------------
    {
        "id": "search-tantivy-declared-not-implemented",
        "layer": "1",
        "severity": "medium",
        "claim": "search/tantivy_backend.py declares a BM25 backend but defines no class.",
        "evidence": [
            _ev("apps/projection/search/tantivy_backend.py", r"^_TITLE_DOC_KINDS"),
            _ev("apps/projection/search/tantivy_backend.py", r"^class\s+\w+", expect="absent"),
        ],
    },
    {
        "id": "layer0-pipeline-marked-stub",
        "layer": "0",
        "severity": "medium",
        "claim": "services/layer0_pipeline.py carries stub markers and is test-only.",
        "evidence": [_ev("apps/control-plane/services/layer0_pipeline.py", r"\bstub\b")],
    },
]


#: Claims that were once recorded as gaps and are now fixed. Each must stay
#: absent; a regression makes the evidence match and fails the build.
RESOLVED_CLAIMS: list[dict] = [
    {
        "id": "context-engine-was-in-memory-only",
        "claim": "CognitiveLoop ran entirely on InMemoryContextStore; the fix is a Postgres store.",
        "evidence": [_ev("apps/control-plane/composition.py", r"PostgresContextStore", expect="present")],
    },
    {
        "id": "investigation-workflow-was-unregistered",
        "claim": "InvestigationWorkflow/RecrawlWorkflow were declared but never registered.",
        "evidence": [_ev("apps/control-plane/workflows/worker.py", r"InvestigationWorkflow", expect="present")],
        "note": "Present now: the worker registers them. This entry guards the fix.",
    },
    {
        "id": "all-downgrades-were-not-implemented",
        "claim": "Every migration downgrade raised NotImplementedError.",
        "evidence": [_ev("apps/control-plane/db/migrations/versions/014_temporal_materialization.py", r"op\.drop_table\(\"materialization_outbox\"\)", expect="present")],
        "note": "014 has a real downgrade that drops tables. This entry guards that.",
    },
    {
        "id": "ci-sync-installed-no-test-runner",
        "claim": "CI ran `uv sync --locked` and installed no test runner.",
        "evidence": [
            _ev(".github/workflows/platform-model.yml", r"uv sync --locked --all-packages --all-groups", expect="present"),
            _ev(".github/workflows/donor-registry.yml", r"uv sync --locked --all-packages --all-groups", expect="present"),
        ],
        "note": "Both workflows now install all packages and groups. This entry guards the fix.",
    },
    {
        "id": "auth-anonymous-admin",
        "claim": "Anonymous requests must not receive an administrator role.",
        "evidence": [
            _ev("apps/control-plane/api/auth.py", r'raise HTTPException\(status_code=401, detail="bearer token required"\)'),
            _ev("apps/control-plane/api/auth.py", r"roles=frozenset\(\{Role\.ANALYST\}\)"),
        ],
        "note": "A request without bearer credentials fails closed; the explicit development adapter never grants ADMIN.",
    },
    {
        "id": "auth-unverified-token",
        "claim": "JWT claims must be signed and validated before they can establish identity or role.",
        "evidence": [
            _ev("apps/control-plane/api/auth.py", r"def _verify_jwt"),
            _ev("apps/control-plane/api/auth.py", r"hmac\.compare_digest"),
            _ev("apps/control-plane/api/auth.py", r"json\.loads\(token\)", expect="absent"),
        ],
        "note": "Only HS256 is accepted; signature, issuer, audience and time claims are verified before payload use.",
    },
]


def _check(root: Path, ev: dict) -> dict:
    path = root / ev["path"]
    if not path.exists():
        return {"path": ev["path"], "ok": False, "reason": "missing", "count": 0}
    text = path.read_text(encoding="utf-8", errors="replace")
    count = len(re.findall(ev["regex"], text, re.M))
    if ev.get("expect", "present") == "present":
        ok = count >= ev.get("min_count", 1)
    else:
        ok = count == 0
    return {"path": ev["path"], "ok": ok, "reason": "ok" if ok else "evidence-mismatch", "count": count}


def verify(root: Path) -> dict:
    gaps: list[dict] = []
    for g in GAPS:
        checks = [_check(root, ev) for ev in g["evidence"]]
        if any(c["reason"] == "missing" for c in checks):
            status = "STALE"
        elif all(c["ok"] for c in checks):
            status = "OPEN"
        else:
            status = "RESOLVED"
        gaps.append({**g, "status": status, "checks": checks})

    resolved: list[dict] = []
    for g in RESOLVED_CLAIMS:
        checks = [_check(root, ev) for ev in g["evidence"]]
        if any(c["reason"] == "missing" for c in checks):
            status = "STALE"
        elif all(c["ok"] for c in checks):
            status = "GUARDED"
        else:
            status = "REGRESSED"
        resolved.append({**g, "status": status, "checks": checks})

    return {
        "gaps": gaps,
        "resolved": resolved,
        "open": sum(1 for g in gaps if g["status"] == "OPEN"),
        "stale_or_resolved": sum(1 for g in gaps if g["status"] != "OPEN"),
    }
