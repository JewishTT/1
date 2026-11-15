
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
    revision_re = re.compile(r'^revision\s*=\s*"([^"]+)"', re.MULTILINE)
    parent_re = re.compile(r'^down_revision\s*=\s*(?:"([^"]+)"|(None))', re.MULTILINE)
    for path in VERSIONS_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        revision = revision_re.search(source)
        parent = parent_re.search(source)
        assert revision and parent, path.name
        parents[revision.group(1)] = parent.group(1)

    children: dict[str, list[str]] = {}
    for revision, parent in parents.items():
        if parent is not None:
            assert parent in parents, f"{revision} has missing parent {parent}"
            children.setdefault(parent, []).append(revision)
    assert all(len(items) == 1 for items in children.values()), children
    assert len([revision for revision in parents if revision not in children]) == 1


def test_036_creates_and_binds_both_native_types_and_preserves_defaults() -> None:
    module = _load_module()
    upgrade = inspect.getsource(module.upgrade)
    downgrade = inspect.getsource(module.downgrade)

    assert 'name="candidateresolutionstate"' in upgrade
    assert 'name="epistemicstatus"' in upgrade
    assert "candidate_state.create(bind, checkfirst=True)" in upgrade
    assert "epistemic_status.create(bind, checkfirst=True)" in upgrade
    assert upgrade.count('op.alter_column("candidates", column_name, server_default=None)') == 1
    assert 'postgresql_using=f"{column_name}::text::{enum_type.name}"' in upgrade
    assert "server_default=sa.text(f\"({default})::{enum_type.name}\")" in upgrade
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
