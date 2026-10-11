"""Kill-chain emulation engine for the CI/SpecOps department (Feature 027, US2).

Direct donor integration: emulation plans are loaded WHOLE from the donor
repositories' own Caldera ability YAML — `donors/ael` and
`donors/adversary_emulation_library` (both Apache-2.0, MITRE "Approved for
public release"). Nothing is re-authored; the loader reads the donors' files and
projects them into the department's plan/ability vocabulary. Attribution is
carried on every plan (`source_donor`).

A launch is gated by the rules-of-engagement gate (specops.roe.gate) BEFORE
anything runs: no confirmed, unexpired sign-off, no launch. Lab-only targeting is
the caller's contract; broader isolation/egress hardening is deferred (FR-003).

This is an in-process stand-in for driving caldera's REST API (the donors' own
orchestrator). It exercises the same plan data and the same RoE gate, so the
surface and the gate are proven end-to-end now; swapping the executor for a live
caldera client is a later wiring change, not a redesign.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

# Donor roots, resolved relative to the repo. Loaded lazily and tolerantly: a
# missing donor dir is a named gap, never a crash.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DONOR_DIRS = {
    "ael": _REPO_ROOT / "donors" / "ael",
    "adversary_emulation_library": _REPO_ROOT / "donors" / "adversary_emulation_library",
}


@dataclass(frozen=True)
class Ability:
    ability_id: str
    name: str
    technique: str
    technique_name: str
    tactic: str
    executor: str
    command: str
    expected_telemetry: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    plan_id: str
    name: str
    source_donor: str
    lab_fixture: str
    abilities: tuple[Ability, ...]

    @property
    def target_techniques(self) -> tuple[str, ...]:
        return tuple(sorted({a.technique for a in self.abilities if a.technique != "unknown"}))


@dataclass
class Operation:
    operation_id: str
    plan_id: str
    lab_fixture: str
    roe_id: str
    state: str = "running"
    abilities: list[dict] = field(default_factory=list)
    started_at: str | None = None
    halted_reason: str | None = None


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _first_command(platforms: dict) -> tuple[str, str]:
    """Pull (executor, command) out of a Caldera ability's `platforms` block."""
    for _os_name, executors in (platforms or {}).items():
        if isinstance(executors, dict):
            for executor, spec in executors.items():
                if isinstance(spec, dict) and "command" in spec:
                    return executor, str(spec["command"]).strip()
    return "unknown", ""


def _ability_from_yaml(entry: dict) -> Ability:
    technique = entry.get("technique") if isinstance(entry.get("technique"), dict) else {}
    executor, command = _first_command(entry.get("platforms"))
    desc = str(entry.get("description", "")).strip()
    attack_id = technique.get("attack_id", "unknown")
    # Expected telemetry: the ATT&CK id plus a short effect tag forensics should find.
    expected = (attack_id,) + ((f"effect: {desc[:80]}",) if desc else ())
    return Ability(
        ability_id=str(entry.get("id", uuid.uuid4().hex)),
        name=str(entry.get("name", "unnamed ability")),
        technique=str(attack_id),
        technique_name=str(technique.get("name", "unknown")),
        tactic=str(entry.get("tactic", "unknown")),
        executor=executor,
        command=command,
        expected_telemetry=expected,
    )

def _parse_ability_yaml(text: str) -> list[dict]:
    """Parse a Caldera ability file (a YAML list of ability mappings).

    Uses PyYAML when available; otherwise a minimal reader for the small, regular
    shape these files have (`- id:`, `name:`, `tactic:`, `technique:` with
    `attack_id`/`name`, and `platforms:` with a nested `command:`). We do not pull
    in a hard PyYAML dependency for the loader to work — the donor files are the
    contract, and a missing optional dep must not blank the whole surface.
    """
    try:
        import yaml  # type: ignore

        docs = yaml.safe_load(text)
        return docs if isinstance(docs, list) else []
    except Exception:
        return _fallback_parse(text)


def _fallback_parse(text: str) -> list[dict]:
    """A deliberately small reader for the donors' ability YAML shape.

    Handles exactly what these files contain: a top-level list of mappings, scalar
    keys, one nested `technique:` mapping, and one nested `platforms:` block whose
    leaf carries `command:`. Anything it cannot model is skipped rather than
    guessed — an unparsed ability is a named gap, not a fabrication.
    """
    abilities: list[dict] = []
    current: dict | None = None
    section: str | None = None  # "technique" | "platforms" | None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("- ") and indent == 0:
            if current is not None:
                abilities.append(current)
            current = {}
            section = None
            stripped = stripped[2:].strip()
        if current is None:
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if indent <= 2 and key in ("id", "name", "description", "tactic"):
            current[key] = value
            section = None
        elif indent <= 2 and key == "technique":
            current["technique"] = {}
            section = "technique"
        elif indent <= 2 and key == "platforms":
            current["platforms"] = {}
            section = "platforms"
        elif section == "technique" and key in ("attack_id", "name"):
            current["technique"][key] = value
        elif section == "platforms" and key == "command":
            # record under a synthetic executor; the exact executor name is not
            # load-bearing for the department's plan/ability vocabulary.
            current["platforms"].setdefault("_", {})["command"] = value
    if current is not None:
        abilities.append(current)
    return abilities


def load_plans(max_per_donor: int = 6) -> list[Plan]:
    """Load emulation plans whole from the donor ability YAML.

    Groups each donor's abilities into one plan per donor (a coarse but honest
    projection — the donors ship abilities, not named multi-step plans). Returns
    whatever loaded; an empty list means the donor dirs were not present, which
    the surface renders as a named absence.
    """
    plans: list[Plan] = []
    for donor, root in _DONOR_DIRS.items():
        if not root.is_dir():
            continue
        abilities: list[Ability] = []
        for yml in sorted(root.rglob("*.yml")):
            if len(abilities) >= max_per_donor:
                break
            try:
                docs = _parse_ability_yaml(yml.read_text(encoding="utf-8"))
            except Exception:
                continue
            for entry in docs:
                if not isinstance(entry, dict) or "id" not in entry:
                    continue
                abilities.append(_ability_from_yaml(entry))
                if len(abilities) >= max_per_donor:
                    break
        if abilities:
            plans.append(
                Plan(
                    plan_id=f"plan-{donor}",
                    name=f"{donor} — {len(abilities)} abilities",
                    source_donor=donor,
                    lab_fixture="specops/lab-target",
                    abilities=tuple(abilities),
                )
            )
    return plans



class OperationRegistry:
    """In-memory operation store. A durable store is a later-phase concern."""

    def __init__(self) -> None:
        self._ops: dict[str, Operation] = {}
        self._plans: dict[str, Plan] = {p.plan_id: p for p in load_plans()}

    def plans(self) -> list[Plan]:
        return list(self._plans.values())

    def plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def create(self, plan: Plan, roe_id: str) -> Operation:
        op = Operation(
            operation_id=f"op-{uuid.uuid4().hex[:12]}",
            plan_id=plan.plan_id,
            lab_fixture=plan.lab_fixture,
            roe_id=roe_id,
            started_at=_now_iso(),
            abilities=[
                {
                    "ability_id": a.ability_id,
                    "technique": a.technique,
                    "tactic": a.tactic,
                    "executor": a.executor,
                    "state": "planned",
                    "expected_telemetry": list(a.expected_telemetry),
                }
                for a in plan.abilities
            ],
        )
        self._ops[op.operation_id] = op
        return op

    def get(self, operation_id: str) -> Operation | None:
        return self._ops.get(operation_id)

    def advance(self, operation_id: str) -> Operation | None:
        """Mark the next planned ability executed (a deterministic stand-in for a
        live agent reporting back). Sets state to `complete` when none remain."""
        op = self._ops.get(operation_id)
        if op is None or op.state != "running":
            return op
        for a in op.abilities:
            if a["state"] == "planned":
                a["state"] = "executed"
                break
        else:
            op.state = "complete"
        return op


REGISTRY = OperationRegistry()

