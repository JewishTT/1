"""A sick backend degrades the query; it does not delete it (T005/T007, D7).

Before the fix, ``QueryPlanner.execute`` awaited a bare
``asyncio.gather(*tasks.values())``. One raising backend -- a Quickwit timeout,
a Neo4j connection refusal -- propagated straight out of ``execute`` and the
caller received **zero** results, including everything the healthy backends
could have answered.

Three properties are pinned here:

1. Partial failure still answers, and names the failure.
2. **Total** failure raises ``AllBackendsFailed``; it never returns ``[]``.
   An empty result set means "no matches", and conflating that with "everything
   is down" is the ambiguity Constitution Invariant 9 exists to prevent.
3. The surfaced error is a bounded ``type: message`` string -- never a
   traceback, never a host filesystem path.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from services.query_planner import (
    DEGRADED_ERROR_MAX,
    AllBackendsFailed,
    BackendHit,
    QueryPlanner,
)

OBS = {
    "OBS-1": {"observation_id": "OBS-1", "uri": "http://fixtures.local/a", "content_hash": "sha256:aa"},
}

TRACEBACKY = (
    "index shard unreachable\n"
    "Traceback (most recent call last):\n"
    '  File "C:\\Users\\tim\\Desktop\\COGNITIVE\\1\\apps\\control-plane\\services\\query_planner.py", '
    "line 81, in search\n"
    "    await self._client.fetch(plan.query)\n"
    "TimeoutError: timed out after 30s"
)


class StubBackend:
    def __init__(self, hits: list[BackendHit] | None = None, error: BaseException | None = None) -> None:
        self.hits = list(hits or [])
        self.error = error
        self.calls = 0

    async def search(self, text: str, filters, limit: int = 20) -> list[BackendHit]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.hits[:limit])


def hits(*doc_ids: str) -> list[BackendHit]:
    return [
        BackendHit(
            doc_id=d,
            kind="document",
            score=0.8,
            backend="opensearch",
            observation_id="OBS-1",
            source_id="src-a",
            payload={"text": "Yard account transfers"},
        )
        for d in doc_ids
    ]


def planner_for(backends: dict[str, StubBackend]) -> QueryPlanner:
    return QueryPlanner(backends=dict(backends), observations=OBS)


def error_of(result) -> str:
    return result.degraded_backends[0]["error"]


class TestPartialFailureStillAnswers:
    async def test_one_sick_backend_returns_the_healthy_backends_results(self) -> None:
        healthy = StubBackend(hits("DOC-1", "DOC-2"))
        planner = planner_for({
            "opensearch": healthy,
            "graph": StubBackend(error=TimeoutError("neo4j bolt handshake timed out")),
        })

        results = await planner.execute(planner.plan("Yard"))

        assert {r.doc_id for r in results} == {"DOC-1", "DOC-2"}
        assert healthy.calls == 1

    async def test_degraded_backends_names_the_failure(self) -> None:
        planner = planner_for({
            "opensearch": StubBackend(hits("DOC-1")),
            "graph": StubBackend(error=ConnectionRefusedError("bolt://neo4j:7687 refused")),
        })

        (result,) = await planner.execute(planner.plan("Yard"))

        assert [d["backend"] for d in result.degraded_backends] == ["graph"]
        assert error_of(result) == "ConnectionRefusedError: bolt://neo4j:7687 refused"
        # The query still answered, so the degradation is recoverable.
        assert result.degraded_backends[0]["recoverable"] is True

    async def test_degraded_entry_shape_is_backend_error_recoverable(self) -> None:
        planner = planner_for({
            "opensearch": StubBackend(hits("DOC-1")),
            "graph": StubBackend(error=TimeoutError("timed out")),
        })

        (result,) = await planner.execute(planner.plan("Yard"))

        assert set(result.degraded_backends[0]) == {"backend", "error", "recoverable"}

    async def test_degraded_backends_is_empty_when_everything_answered(self) -> None:
        """Invariant: non-empty iff at least one selected backend failed."""
        planner = planner_for({
            "opensearch": StubBackend(hits("DOC-1")),
            "graph": StubBackend(hits("DOC-1")),
        })

        results = await planner.execute(planner.plan("Yard"))

        assert results
        assert all(r.degraded_backends == [] for r in results)

    async def test_a_healthy_but_empty_backend_is_not_a_degradation(self) -> None:
        """Zero hits is a legitimate answer; only a raise is a failure."""
        planner = planner_for({
            "opensearch": StubBackend([]),
            "graph": StubBackend([]),
        })

        results = await planner.execute(planner.plan("Yard"))

        assert results == []

    async def test_multiple_failures_are_all_named_in_stable_order(self) -> None:
        planner = planner_for({
            "opensearch": StubBackend(hits("DOC-1")),
            "graph": StubBackend(error=TimeoutError("g1")),
            "clickhouse": StubBackend(error=RuntimeError("ch1")),
        })

        results = await planner.execute(planner.plan("Yard"))

        assert all(
            [d["backend"] for d in r.degraded_backends] == ["clickhouse", "graph"] for r in results
        )


class TestTotalFailureIsNotAnEmptyResultSet:
    async def test_all_backends_failing_raises(self) -> None:
        planner = planner_for({
            "opensearch": StubBackend(error=TimeoutError("quickwit timeout")),
            "graph": StubBackend(error=ConnectionRefusedError("bolt refused")),
        })

        with pytest.raises(AllBackendsFailed):
            await planner.execute(planner.plan("Yard"))

    async def test_all_backends_failing_does_not_return_an_empty_list(self) -> None:
        """`[]` would be indistinguishable from a genuine 'no matches'."""
        planner = planner_for({"opensearch": StubBackend(error=TimeoutError("quickwit timeout"))})

        outcome: object = None
        try:
            outcome = await planner.execute(planner.plan("Yard"))
        except AllBackendsFailed:
            outcome = "raised"
        assert outcome == "raised"

    async def test_empty_matches_and_total_outage_are_distinguishable(self) -> None:
        """The contrast that matters: same planner, two different outcomes."""
        quiet = planner_for({"opensearch": StubBackend([])})
        assert await quiet.execute(quiet.plan("Yard")) == []

        dead = planner_for({"opensearch": StubBackend(error=TimeoutError("down"))})
        with pytest.raises(AllBackendsFailed):
            await dead.execute(dead.plan("Yard"))

    async def test_raised_exception_names_every_failed_backend(self) -> None:
        planner = planner_for({
            "opensearch": StubBackend(error=TimeoutError("quickwit timeout")),
            "graph": StubBackend(error=ConnectionRefusedError("bolt refused")),
        })

        with pytest.raises(AllBackendsFailed) as excinfo:
            await planner.execute(planner.plan("Yard"))

        degraded = excinfo.value.degraded_backends
        assert [d["backend"] for d in degraded] == ["graph", "opensearch"]
        assert [d["error"] for d in degraded] == [
            "ConnectionRefusedError: bolt refused",
            "TimeoutError: quickwit timeout",
        ]
        # Nothing answered, so nothing about this failure was recoverable.
        assert all(d["recoverable"] is False for d in degraded)

    async def test_cancellation_is_not_mistaken_for_a_degraded_backend(self) -> None:
        """A cancelled query is not a sick backend, and must not be swallowed."""
        planner = planner_for({
            "opensearch": StubBackend(hits("DOC-1")),
            "graph": StubBackend(error=asyncio.CancelledError()),
        })

        with pytest.raises(asyncio.CancelledError):
            await planner.execute(planner.plan("Yard"))

    async def test_selecting_no_backend_is_a_planner_error_not_an_outage(self) -> None:
        """Zero backends attempted is not "every backend failed" -- it is misuse,
        and reporting it as an outage would put a lie in `degraded_backends`."""
        planner = planner_for({"opensearch": StubBackend(hits("DOC-1"))})
        plan = planner.plan("Yard")
        plan.backends = []

        with pytest.raises(ValueError):
            await planner.execute(plan)


class TestSurfacedErrorIsBounded:
    async def test_error_is_type_colon_message(self) -> None:
        planner = planner_for({
            "opensearch": StubBackend(hits("DOC-1")),
            "graph": StubBackend(error=TimeoutError("bolt handshake timed out")),
        })

        (result,) = await planner.execute(planner.plan("Yard"))

        head, _, tail = error_of(result).partition(": ")
        assert head == "TimeoutError"
        assert tail == "bolt handshake timed out"

    async def test_long_error_is_truncated(self) -> None:
        planner = planner_for({
            "opensearch": StubBackend(hits("DOC-1")),
            "graph": StubBackend(error=TimeoutError("x" * 5000)),
        })

        (result,) = await planner.execute(planner.plan("Yard"))

        assert len(error_of(result)) == DEGRADED_ERROR_MAX
        assert len(error_of(result)) < 5000

    async def test_error_carries_no_traceback(self) -> None:
        planner = planner_for({
            "opensearch": StubBackend(hits("DOC-1")),
            "graph": StubBackend(error=RuntimeError(TRACEBACKY)),
        })

        (result,) = await planner.execute(planner.plan("Yard"))

        assert "Traceback" not in error_of(result)
        assert "\n" not in error_of(result)
        assert "await self._client.fetch" not in error_of(result)

    async def test_error_carries_no_filesystem_path(self) -> None:
        planner = planner_for({
            "opensearch": StubBackend(hits("DOC-1")),
            "graph": StubBackend(
                error=OSError("cannot open C:\\Users\\tim\\Desktop\\COGNITIVE\\1\\shard-0001.idx")
            ),
        })

        (result,) = await planner.execute(planner.plan("Yard"))

        assert "C:" not in error_of(result)
        assert "shard-0001" not in error_of(result)
        assert "\\" not in error_of(result)
        assert "<path>" in error_of(result)

    async def test_exception_type_without_a_message_still_surfaces(self) -> None:
        planner = planner_for({"opensearch": StubBackend(error=RuntimeError())})

        with pytest.raises(AllBackendsFailed) as excinfo:
            await planner.execute(planner.plan("Yard"))

        assert excinfo.value.degraded_backends[0]["error"].startswith("RuntimeError")
