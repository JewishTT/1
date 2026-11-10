
"""Migration and ORM parity for the native candidate-state PostgreSQL enums."""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

_APPS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS / "shared"))
sys.path.insert(0, str(_APPS / "control-plane"))

VERSIONS_DIR = _APPS / "control-plane" / "db" / "migrations" / "versions"
MIGRATION = VERSIONS_DIR / "036_candidate_resolution_enum_types.py"


def _load_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "revision_036_candidate_enum_types_under_test", MIGRATION
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_036_is_the_single_head_after_035() -> None:
    assert MIGRATION.is_file()
    module = _load_module()
    assert module.revision == "036_candidate_resolution_enum_types"
    assert module.down_revision == "035_interpretation_mentions_and_entity_versions"

    parents: dict[str, str | None] = {}
    revision_re = re.compile(r'^revision\\s*=\\s*["\\']([^"\\']+)["\\']', re.MULTILINE)
    parent_re = re.compile(r"^down_revision\\s*=\\s*(.+)$", re.MULTILINE)
    for path in VERSIONS_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        revision = revision_re.search(source)
        parent = parent_re.search(source)
        assert revision and parent, path.name
        raw_parent = parent.group(1).strip()
        if raw_parent == "None":
            parents[revision.group(1)] = None
        else:
            value = re.match(r'^[ "\']([^"\']+)[ "\']$', raw_parent)
            assert value, f"unsupported migration parent syntax: {path.name}"
            parents[revision.group(1)] = value.group(1)

    children: dict[str, list[str]] = {}
    for revision, parent in parents.items():
        if parent is not None:
            assert parent in parents, f"{revision} has missing parent {parent}"
            children.setdefault(parent, []).append(revision)
    assert all(len(items) == 1 for items in children.values()), children
    assert len([revision for revision in parents if revision not in children]) == 1


def test_036_creates_both_native_types_idempotently_without_rewriting_legacy_rows() -> None:
    module = _load_module()
    source = MIGRATION.read_text(encoding="utf-8")
    upgrade = inspect.getsource(module.upgrade)
    downgrade = inspect.getsource(module.downgrade)

    assert 'name="candidateresolutionstate"' in source
    assert 'name="epistemicstatus"' in source
    assert ".create(bind, checkfirst=True)" in upgrade
    assert upgrade.count(".create(bind, checkfirst=True)") == 2
    assert "op.create_table" not in upgrade
    assert "op.drop_table" not in upgrade
    assert "forward-only" in downgrade


def test_candidate_orm_native_enum_names_and_members_match_migration() -> None:
    from db.schema import Candidate, CandidateResolutionState, EpistemicStatus

    state_type = Candidate.__table__.c.state.type
    epistemic_type = Candidate.__table__.c.epistemic_status.type
    migration = _load_module()
    assert state_type.name == "candidateresolutionstate"
    assert epistemic_type.name == "epistemicstatus"
    assert tuple(member.name for member in CandidateResolutionState) == migration._CANDIDATE_RESOLUTION
    assert tuple(member.name for member in EpistemicStatus) == migration._EPISTEMIC_STATUS
    assert tuple(state_type.enums) == migration._CANDIDATE_RESOLUTION
    assert tuple(epistemic_type.enums) == migration._EPISTEMIC_STATUS
