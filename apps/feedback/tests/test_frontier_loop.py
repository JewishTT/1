"""Integration: feedback loop closes into the authoritative Postgres frontier.

feedback branch candidates -> PgFrontierSink -> real `frontier_items` ->
PgFrontier.pop_next leases them back to the acquisition loop. Skipped when
Postgres is unreachable.
"""

from __future__ import annotations

import os
import socket
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "control-plane"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "shared"))

import pytest

pytestmark = pytest.mark.integration


def _pg_reachable() -> bool:
    dsn = os.getenv("POSTGRES_DSN", "postgresql://cognitive:cognitive@localhost:5432/cognitive")
    host = dsn.split("@")[-1].split("/")[0]
    h, p = host.split(":")
    try:
        with socket.create_connection((h, int(p)), timeout=3):
            return True
    except OSError:
        return False


pytestmark = [pytestmark, pytest.mark.skipif(not _pg_reachable(), reason="postgres unavailable")]


@pytest.mark.asyncio
async def test_entity_pivots_land_and_lease_back_from_frontier() -> None:
    import uuid as _uuid

    from db.session import create_tables, make_session_factory
    from services.frontier import PgFrontier

    from feedback import EntityResolutionHints, run_entity_feedback
    from feedback.frontier import PgFrontierSink

    await create_tables()
    factory = make_session_factory()
    sink = PgFrontierSink(factory)
    frontier = PgFrontier(factory)
    tenant = "ten-fb-" + _uuid.uuid4().hex[:6]

    hints = EntityResolutionHints(
        entity_id="ENT-FB-1",
        tenant_id=tenant,
        names=["Eagle Eye"],
        aliases=["EE"],
        emails=["ee@example.com"],
        handles=["@ee"],
    )
    candidates = run_entity_feedback(hints)
    assert candidates

    enqueued = [c for c in candidates if await sink.enqueue_candidate(c)]
    assert len(enqueued) == len(candidates)

    # dedup: same tenant + uri does not double-enqueue
    again = [c for c in candidates if await sink.enqueue_candidate(c)]
    assert again == []
    assert await frontier.ready_count(tenant_id=tenant) == len(candidates)

    item = await frontier.pop_next(tenant_id=tenant)
    assert item is not None
    assert item.tenant_id == tenant
    assert item.state == "LEASED"
    await frontier.cancel(item.frontier_id)

    # cleanup the remaining rows so runs stay hermetic
    from db.schema import FrontierItem as Row
    from sqlalchemy import delete

    async with factory() as session:
        await session.execute(delete(Row).where(Row.tenant_id == tenant))
        await session.commit()


@pytest.mark.asyncio
async def test_finding_candidate_becomes_ready_frontier_work() -> None:
    from db.session import create_tables, make_session_factory
    from scoring.scorer import HeuristicUtilityScorer
    from services.frontier import PgFrontier

    from feedback import FindingCandidate, run_finding_feedback
    from feedback.frontier import PgFrontierSink

    await create_tables()
    factory = make_session_factory()
    sink = PgFrontierSink(factory)
    frontier = PgFrontier(factory)
    tenant = "ten-fb-" + uuid.uuid4().hex[:6]

    findings = [
        FindingCandidate(
            finding_id="F-FB-1",
            entity_id="ENT-FB-2",
            tenant_id=tenant,
            confidence=0.95,
            novelty=0.7,
        )
    ]
    candidates = run_finding_feedback(HeuristicUtilityScorer(), findings)
    assert candidates and await sink.enqueue_candidate(candidates[0])
    assert await frontier.ready_count(tenant_id=tenant) == 1
    item = await frontier.pop_next(tenant_id=tenant)
    assert item is not None
    assert item.uri == candidates[0].uri
    await frontier.cancel(item.frontier_id)

    from db.schema import FrontierItem as Row
    from sqlalchemy import delete

    async with factory() as session:
        await session.execute(delete(Row).where(Row.tenant_id == tenant))
        await session.commit()

    # low-value finding stays out of the frontier
    low = run_finding_feedback(
        HeuristicUtilityScorer(),
        [
            FindingCandidate(
                finding_id="F-LOW", entity_id="ENT-FB-2", tenant_id=tenant, estimated_utility=0.02
            )
        ],
    )
    assert low == []
