"""Worker-side revocation/scope guard for queued Feature 034 tasks."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))

from case_execution_guard import PostgresCaseExecutionGuard, _policy_revision
from sources.executor import AcquisitionError
from sources.connector import AcquisitionTask


class _Result:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement, params):
        sql = str(statement).lower()
        self.queries.append(sql)
        if "from person_case_metadata" in sql:
            return _Result(self.rows.get("metadata"))
        if "from investigation_contexts" in sql:
            return _Result(self.rows.get("context"))
        if "from research_actions" in sql:
            return _Result(self.rows.get("action"))
        if "from person_case_dispatch_intents" in sql:
            return _Result(self.rows.get("intent"))
        if "from person_case_budget_reservations" in sql:
            return _Result(self.rows.get("reservation"))
        raise AssertionError(f"unexpected SQL: {sql}")


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


def _task(**overrides):
    values = {
        "task_id": "TSK-guard-1",
        "source_id": "crossref_doi",
        "source_name": "crossref_doi",
        "query": "public example",
        "category": "knowledge",
        "tenant_id": "tenant-1",
        "investigation_id": "case-investigation-1",
        "case_id": "case-1",
        "scope_digest": "sha256:" + "a" * 64,
        "policy_digest": "sha256:" + "b" * 64,
        "policy_revision": _policy_revision(),
        "scope_revision": 1,
        "budget_reservation_id": "RBR-1",
        "idempotency_key": "idem-1",
        "run_id": "RUN-1",
        "case_policy_source_id": "crossref_works",
        "approved_action_ref": "ACT-1",
        "action_id": "ACT-1",
    }
    values.update(overrides)
    return AcquisitionTask(**values)


def _rows(task=None):
    task = task or _task()
    return {
        "metadata": {
            "tenant_id": task.tenant_id,
            "payload": {
                "tenant_id": task.tenant_id,
                "approved": True,
                "scope_digest": task.scope_digest,
                "scope_revision": task.scope_revision,
                "expires_at": None,
                "allowed_source_ids": [task.case_policy_source_id],
            },
        },
        "context": {
            "investigation_id": task.investigation_id,
            "payload": {
                "investigation_id": task.investigation_id,
                "policy_snapshot_ref": task.policy_revision,
                "state": "uninvestigated",
            },
        },
        "action": {
            "payload": {
                "action_id": task.action_id,
                "status": "approved",
                "requires_operator_approval": False,
                "scope_digest": task.scope_digest,
                "policy_digest": task.policy_digest,
                "source_id": task.case_policy_source_id,
                "catalogue_source_id": task.source_id,
            }
        },
        "intent": {
            "run_id": task.run_id,
            "payload": {
                "state": "PREPARED",
                "run_id": task.run_id,
                "approved_action_refs": [task.action_id],
            },
        },
        "reservation": {
            "reservation_id": task.budget_reservation_id,
            "state": "RESERVED",
            "payload": {"reservation_id": task.budget_reservation_id},
        },
    }


@pytest.mark.asyncio
async def test_valid_task_passes_all_durable_authority_checks():
    task = _task()
    session = _Session(_rows(task))
    guard = PostgresCaseExecutionGuard(_SessionFactory(session))

    await guard(task)

    assert len(session.queries) == 5
    assert any("person_case_metadata" in query for query in session.queries)
    assert any("investigation_contexts" in query for query in session.queries)
    assert any("research_actions" in query for query in session.queries)
    assert any("person_case_dispatch_intents" in query for query in session.queries)
    assert any("person_case_budget_reservations" in query for query in session.queries)


@pytest.mark.asyncio
async def test_revoked_approval_blocks_before_action_or_budget_checks():
    task = _task()
    rows = _rows(task)
    rows["metadata"]["payload"]["approved"] = False
    session = _Session(rows)
    guard = PostgresCaseExecutionGuard(_SessionFactory(session))

    with pytest.raises(AcquisitionError, match="not currently approved"):
        await guard(task)

    assert len(session.queries) == 1


@pytest.mark.asyncio
async def test_scope_revision_digest_and_source_allowlist_are_rechecked():
    task = _task()
    rows = _rows(task)
    rows["metadata"]["payload"]["scope_revision"] = 2
    session = _Session(rows)
    guard = PostgresCaseExecutionGuard(_SessionFactory(session))

    with pytest.raises(AcquisitionError, match="scope changed"):
        await guard(task)

    rows = _rows(task)
    rows["metadata"]["payload"]["allowed_source_ids"] = ["another-source"]
    session = _Session(rows)
    with pytest.raises(AcquisitionError, match="in the approved source allowlist"):
        await PostgresCaseExecutionGuard(_SessionFactory(session))(task)


@pytest.mark.asyncio
async def test_policy_action_and_budget_revisions_are_independently_enforced():
    task = _task()
    rows = _rows(task)
    rows["action"]["payload"]["status"] = "proposed"
    with pytest.raises(AcquisitionError, match="action approval"):
        await PostgresCaseExecutionGuard(_SessionFactory(_Session(rows)))(task)

    rows = _rows(task)
    rows["reservation"] = None
    with pytest.raises(AcquisitionError, match="budget reservation"):
        await PostgresCaseExecutionGuard(_SessionFactory(_Session(rows)))(task)


@pytest.mark.asyncio
async def test_policy_file_change_invalidates_already_queued_tasks(monkeypatch):
    task = _task(policy_revision="1:sha256:" + "0" * 64)
    session = _Session(_rows(task))
    with pytest.raises(AcquisitionError, match="policy changed after dispatch"):
        await PostgresCaseExecutionGuard(_SessionFactory(session))(task)
    assert session.queries == []
