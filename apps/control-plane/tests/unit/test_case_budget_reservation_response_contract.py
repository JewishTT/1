from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from services.research_case_runtime import PostgresCaseBudgetService


class _Rows:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def first(self) -> dict[str, Any] | None:
        return self._row

    def one(self) -> dict[str, Any]:
        assert self._row is not None
        return self._row


class _Result:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> _Rows:
        return _Rows(self._row)


class _Session:
    def __init__(self) -> None:
        self.insert_params: dict[str, Any] | None = None
        self._budget = {
            "budget_id": "budget-1",
            "tenant_id": "tenant-1",
            "investigation_id": "investigation-1",
            "limits": {
                "person_research_case": {
                    "max_requests": 10,
                    "max_raw_bytes": 1_000_000,
                    "max_records": 100,
                    "max_concurrency": 2,
                    "max_wall_seconds": 600,
                }
            },
            "current_usage": {},
        }

    async def execute(self, statement: Any, params: dict[str, Any]) -> _Result:
        sql = str(statement)
        if "FROM budgets" in sql:
            return _Result(self._budget)
        if "SELECT COALESCE(SUM" in sql:
            return _Result(
                {
                    "requests": 0,
                    "raw_bytes": 0,
                    "records": 0,
                    "concurrency": 0,
                    "wall_seconds": 0,
                }
            )
        if "INSERT INTO person_case_budget_reservations" in sql:
            self.insert_params = params
            return _Result(None)
        raise AssertionError(f"unexpected SQL in budget reservation test: {sql}")


@pytest.mark.asyncio
async def test_new_reservation_exposes_request_count_expected_by_dispatcher() -> None:
    session = _Session()

    @asynccontextmanager
    async def session_factory():
        yield session

    service = PostgresCaseBudgetService(session_factory)
    reservation = await service.reserve_case(
        budget_ref="budget-1",
        tenant_id="tenant-1",
        case_id="case-1",
        investigation_id="investigation-1",
        idempotency_key="run-1",
        scope_digest="sha256:" + "a" * 64,
        policy_digest="sha256:" + "b" * 64,
        requests=2,
        raw_bytes=2_000,
        records=20,
        concurrency=1,
        wall_seconds=120,
        source_refs=("crossref_works",),
    )

    assert reservation["requests"] == 2
    assert reservation["request_count"] == 2
    assert session.insert_params is not None
    assert session.insert_params["request_count"] == reservation["request_count"]
