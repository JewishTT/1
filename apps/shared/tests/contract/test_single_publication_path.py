"""The single-publication-path ratchet (Feature 032, FR-001/FR-002, blueprint §0.1).

Blueprint §0.1: every executor delivers through one `ArtifactSink` / Observation Gate,
and *"никакой runtime не создаёт собственную независимую версию canonical observation"*.
That invariant is only as good as the set of places that can break it, and a set that
nobody measures grows silently — which is how the `OperatorResult` and DLQ pairs in the
WP0 capability matrix came to exist.

This test measures two capabilities and pins them:

1. **Who mints an observation identity.** `domain.observation_identity` is the single
   writer (its own docstring says so). Three modules are allowed to reach it:
   the writer itself, the gate, and `AcquisitionArtifact.observation_identity`, which
   delegates rather than cutting a digest of its own.
2. **Who constructs a persisted `Observation` row.** In the intended design nobody but
   the Gate does. Today two services do, and they are recorded in
   ``single_publication_debt.json`` with the reason and the exit condition.

The ratchet is deliberately bidirectional: a **new** bypass fails, and so does a debt
entry that has become stale (the file no longer offends, or no longer exists). Stale
debt is how a ratchet quietly stops being one.

Unlike the older `layer_boundaries` guard, the debt file exists from the first commit
here — that guard's file was missing, so its failure message listed every violation as
"new" and the debt count was the only real signal.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[4]
APPS = ROOT / "apps"
DEBT = Path(__file__).with_name("single_publication_debt.json")

#: The modules allowed to mint an observation identity, with the reason each is allowed.
IDENTITY_AUTHORITY = {
    "apps/shared/domain/observation_identity.py": "the single writer itself",
    "apps/shared/events/observation_gate.py": "the gate: the intended publication path",
    "apps/shared/domain/acquisition_artifact.py": "delegates to the writer; cuts no digest of its own",
}


def _production_files() -> list[Path]:
    files: list[Path] = []
    for path in APPS.rglob("*.py"):
        parts = path.parts
        if "__pycache__" in parts or "tests" in parts or path.name.startswith("test_"):
            continue
        files.append(path)
    return sorted(files)


def _rel(path: Path) -> str:
    """Repository-relative path; synthetic fixtures outside the tree fall back to the name."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return f"<synthetic>/{path.name}"


def _identity_minters(files: list[Path]) -> dict[str, list[int]]:
    """Files that call ``ObservationIdentity.for_record`` or ``observation_id_for``."""
    found: dict[str, list[int]] = {}
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        lines: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "for_record":
                lines.append(node.lineno)
            elif isinstance(func, ast.Name) and func.id == "observation_id_for":
                lines.append(node.lineno)
        if lines:
            found[_rel(path)] = sorted(set(lines))
    return found


def _observation_row_writers(files: list[Path]) -> dict[str, list[int]]:
    """Files that construct a persisted ``Observation`` row from ``db.schema``.

    Import-aware on purpose. A bare ``Observation(...)`` call is ambiguous: the
    domain dataclass in ``apps/shared/domain`` and the ORM row share the name, and
    treating both as writes reported two application-layer modules as database
    writers. Only a name bound by ``from db.schema import Observation`` counts.
    """
    found: dict[str, list[int]] = {}
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        local: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("db.schema"):
                for alias in node.names:
                    if alias.name == "Observation":
                        local.add(alias.asname or alias.name)
        if not local:
            continue
        lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in local
        ]
        if lines:
            found[_rel(path)] = sorted(set(lines))
    return found


def _debt() -> dict[str, dict[str, str]]:
    if not DEBT.is_file():
        raise AssertionError(
            f"{DEBT} is missing. The debt list is the ratchet's other half: without it a "
            "bypass is indistinguishable from a new defect, and every run reports the "
            "whole surface as new."
        )
    return json.loads(DEBT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def measured() -> dict[str, dict[str, list[int]]]:
    files = _production_files()
    return {"identity": _identity_minters(files), "rows": _observation_row_writers(files)}


# ---------------------------------------------------------------------------
# 1. Identity minting
# ---------------------------------------------------------------------------


def test_identity_is_minted_only_where_declared(measured):
    recorded = _debt()["identity_bypass"]
    allowed = set(IDENTITY_AUTHORITY) | set(recorded)
    offenders = sorted(set(measured["identity"]) - allowed)
    assert not offenders, (
        "a new module mints observation identity. `domain.observation_identity` is the single "
        "writer (blueprint §3.5.3); a second addresser is how two ids for one observation "
        f"appear. Offenders: {offenders}. If this is deliberate, add it to {DEBT.name} with a "
        "reason and an exit condition — do not widen IDENTITY_AUTHORITY."
    )


def test_identity_authority_is_complete(measured):
    """Every declared authority is still real: a stale allowlist hides a removal."""
    stale = sorted(set(IDENTITY_AUTHORITY) - set(measured["identity"]))
    assert not stale, f"these are listed as identity authorities but no longer mint: {stale}"


# ---------------------------------------------------------------------------
# 2. Observation-row construction
# ---------------------------------------------------------------------------


def test_observation_rows_are_constructed_only_where_recorded(measured):
    recorded = _debt()["row_writers"]
    allowed = set(recorded)
    offenders = sorted(set(measured["rows"]) - allowed)
    assert not offenders, (
        "a new module constructs a persisted Observation row, bypassing the Observation Gate "
        f"(FR-001). Offenders: {offenders}. Record it in {DEBT.name} with a reason, or route it "
        "through the gate."
    )


def test_every_recorded_bypass_still_offends(measured):
    """Stale debt is debt nobody is paying: a fixed bypass must leave the list."""
    recorded = _debt()["row_writers"]
    fixed = sorted(path for path in recorded if path not in measured["rows"])
    assert not fixed, (
        "these paths are recorded as observation-row writers but no longer write rows. If the "
        f"bypass was removed, delete the entry so the ratchet tightens: {fixed}"
    )


def test_every_recorded_bypass_still_exists(measured):
    recorded = _debt()["row_writers"]
    gone = sorted(path for path in recorded if not (ROOT / path).is_file())
    assert not gone, f"debt names files that do not exist: {gone}"


# ---------------------------------------------------------------------------
# 3. The debt list is a decision record, not a suppression list
# ---------------------------------------------------------------------------


def test_each_debt_entry_states_a_reason_and_an_exit_condition():
    debt = _debt()
    incomplete = {
        section: sorted(
            path
            for path, note in entries.items()
            if not str(note.get("reason", "")).strip() or not str(note.get("exit", "")).strip()
        )
        for section, entries in debt.items()
        if isinstance(entries, dict)
    }
    offenders = {section: paths for section, paths in incomplete.items() if paths}
    assert not offenders, (
        "every recorded bypass needs both a `reason` (why it exists) and an `exit` (what would "
        f"remove it). Missing: {offenders}"
    )


# ---------------------------------------------------------------------------
# 4. Non-vacuity: prove the detector can see a violation
# ---------------------------------------------------------------------------


def test_detector_sees_a_synthetic_identity_bypass(tmp_path: Path):
    file = tmp_path / "apps" / "control-plane" / "sneaky.py"
    file.parent.mkdir(parents=True)
    file.write_text(
        "from domain.observation_identity import ObservationIdentity\n"
        "def mint(tenant_id, capture_id, locator, digest):\n"
        "    return ObservationIdentity.for_record(\n"
        "        tenant_id=tenant_id, capture_id=capture_id, locator=locator, record_digest=digest\n"
        "    )\n",
        encoding="utf-8",
    )
    found = _identity_minters([file])
    assert found, "the detector did not see an ObservationIdentity.for_record call"


def test_detector_sees_a_synthetic_row_writer(tmp_path: Path):
    file = tmp_path / "apps" / "control-plane" / "sneaky_rows.py"
    file.parent.mkdir(parents=True)
    file.write_text(
        "from db.schema import Observation as Row\n"
        "def persist(session, observation_id):\n"
        "    session.add(Row(observation_id=observation_id))\n",
        encoding="utf-8",
    )
    found = _observation_row_writers([file])
    assert found, "the detector did not see a db.schema Observation construction"


def test_detector_ignores_the_domain_dataclass(tmp_path: Path):
    """The false positive that a bare-name scan produced: a domain dataclass, not a row."""
    file = tmp_path / "apps" / "control-plane" / "domain_only.py"
    file.parent.mkdir(parents=True)
    file.write_text(
        "from domain.observation import Observation\n"
        "def build():\n"
        "    return Observation(text='x')\n",
        encoding="utf-8",
    )
    assert _observation_row_writers([file]) == {}
