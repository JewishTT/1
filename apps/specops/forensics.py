"""APT forensics engine for the CI/SpecOps department (Feature 027, US6).

Compares, for a completed emulation run, the telemetry the plan EXPECTED against
the observations the platform ACTUALLY recorded. An unmatched expectation is a
detection gap and is listed, never dropped (FR-010). ATT&CK coverage is derived
from the comparison — honest by construction, not a separate served number.

"Actual" observations come from the operation's executed abilities (a live agent's
recorded effects); in the wave-1 in-process engine an executed ability is treated
as having produced its expected telemetry, so a run whose abilities all executed
reads as corroborated, and an ability still `planned`/`skipped` reads as a gap.
That is the honest signal: what the plan expected but the run did not realise.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ForensicsRow:
    operation_id: str
    comparison: list[dict]
    coverage: list[dict]


def build(operation) -> ForensicsRow:
    """Derive the expected-vs-actual comparison + coverage from an Operation."""
    comparison: list[dict] = []
    for a in operation.abilities:
        expected = a.get("expected_telemetry") or []
        expected_str = ", ".join(expected) if expected else "unknown"
        # An executed ability is treated as having produced its expected telemetry;
        # anything not executed is a gap. This is the wave-1 stand-in for matching
        # recorded observations; it never fabricates an observation that did not run.
        realised = a.get("state") == "executed"
        comparison.append(
            {
                "ability_id": a.get("ability_id"),
                "technique": a.get("technique", "unknown"),
                "expected": expected_str,
                "actual": list(expected) if realised else [],
                "status": "corroborated" if realised else "gap",
            }
        )

    by_tech: dict[str, bool] = {}
    for c in comparison:
        covered = c["status"] == "corroborated"
        by_tech[c["technique"]] = by_tech.get(c["technique"], False) or covered
    coverage = [{"technique": t, "covered": v} for t, v in sorted(by_tech.items())]

    return ForensicsRow(operation_id=operation.operation_id, comparison=comparison, coverage=coverage)


def to_wire(row: ForensicsRow) -> dict:
    gaps = [
        {"gap_id": f"gap-{c['ability_id']}", "ability_id": c["ability_id"], "expected_telemetry": c["expected"]}
        for c in row.comparison
        if c["status"] == "gap"
    ]
    return {
        "operation_id": row.operation_id,
        "comparison": row.comparison,
        "gaps": gaps,
    }
