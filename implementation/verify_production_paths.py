#!/usr/bin/env python3
"""Fail-closed source audit for known fake/no-op production paths in COGNITIVE.

Run from a checkout: python implementation/verify_production_paths.py .
This checks known anti-patterns by exact source signatures. A clean report is *not* an
end-to-end readiness certificate; service-backed acceptance is still mandatory.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def read(root: Path, relative: str) -> str | None:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".", help="COGNITIVE repository root")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    problems: list[str] = []
    checked: list[str] = []

    def check(relative: str, pattern: str, reason: str, *, missing_is_problem: bool = False) -> None:
        compiled = re.compile(pattern, flags=re.MULTILINE | re.DOTALL)
        source = read(root, relative)
        checked.append(relative)
        if source is None:
            if missing_is_problem:
                problems.append(f"MISSING {relative}: {reason}")
            return
        if compiled.search(source):
            problems.append(f"FORBIDDEN {relative}: {reason}")

    check(
        "apps/acquisition/dispatcher/scheduler.py",
        r"class ScopeLimits[\s\S]{0,1800}?def allows\([\s\S]{0,500}?return\s+True\s*,\s*['\"]['\"]",
        "ScopeLimits quota gate is a no-op",
    )
    check(
        "apps/acquisition/dispatcher/scheduler.py",
        r"def emit_request\([\s\S]{0,1600}?if self\._producer is None:\s*\n\s*return",
        "dispatch silently succeeds when producer is missing",
    )
    check(
        "apps/shared/events/kafka.py",
        r"self\._dedup\s*=\s*deduplicator\s+or\s+InMemoryDeduplicator\(\)",
        "production consumer defaults to volatile deduplication",
    )
    check(
        "apps/shared/events/kafka.py",
        r"class Deduplicator[\s\S]{0,900}?async def release\([^)]*\):\s*\n\s*['\"]{3}[\s\S]*?\n\s*return None",
        "base deduplicator release operation silently does nothing",
    )
    check(
        "apps/admission/resolution/blocking.py",
        r"if len\(indexed\[bucket\]\) < self\._max_bucket:\s*\n\s*indexed\[bucket\]\.append",
        "blocking truncates bucket before checking overflow; pairs can be silently lost",
    )
    check(
        "apps/admission/resolution/resolver.py",
        r"SequenceMatcher[\s\S]{0,1800}?heuristic\s*=\s*max\(scores\.values\(\), default=0\.0\)",
        "handwritten heuristic pair scorer remains in the resolution implementation; verify no person-case production caller",
    )
    check(
        "apps/control-plane/api/routes/entities.py",
        r"^_observations\s*=\s*\{[\s\S]{0,1200}?^_catalog\s*=\s*Catalog\(",
        "module-level fixture catalog is mixed with the production API router",
    )
    check(
        "donors/TraceMatrix/orchestrator/app/main.py",
        r"def search_stub\(",
        "donor search stub exists; ensure no production import or route uses it",
    )
    check(
        "apps/projection/analytics/store.py",
        r"in-memory ClickHouse-analog",
        "dictionary-backed analytic store must not be the production serving path",
    )

    required = {
        "apps/control-plane/services/model_gateway.py": "central model gateway adapter is missing",
        "apps/acquisition/policies/person_case_sources.yaml": "runtime source-policy file is missing",
        "apps/control-plane/context_engine/person_case_profile.py": "person case profile pack is missing",
        "apps/control-plane/services/research_case_service.py": "person case application service is missing",
        "apps/control-plane/services/research_case_policy.py": "person case policy gate is missing",
        "apps/control-plane/api/routes/research_cases.py": "person case API routes are missing",
        "apps/science/context/person_case.lark": "person case Lark grammar is missing",
    }
    for relative, reason in required.items():
        checked.append(relative)
        if read(root, relative) is None:
            problems.append(f"MISSING {relative}: {reason}")

    print(f"Checked {len(checked)} known production seams in {root}")
    if problems:
        print(f"BLOCKED: {len(problems)} production-path issue(s) remain")
        for problem in problems:
            print(f" - {problem}")
        return 1
    print("No known fake/no-op signature found. This is not a substitute for service-backed E2E acceptance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
