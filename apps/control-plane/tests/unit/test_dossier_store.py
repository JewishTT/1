"""The round trip that decides whether a dossier survives its process.

Writing a sweep down is only half of it; the other half is that reading it back produces the
same dossier. Both halves run against a fake connection here, because a test that needs
PostgreSQL is a test that stops running the moment the database is down, and this is exactly
the code that must be trusted when it is.

The fake is deliberately literal: it records the statements and returns canned result rows, so
a change in the SQL -- a dropped column, a lost join, a renamed table -- fails here rather than
in production. It cannot catch a constraint that does not exist, which is why the record-hash
collision had to be found by running against a real database.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from context.enrichment import CapabilityOffer
from context_engine.dossier_store import DossierReader, PostgresEnrichmentSink

TENANT = "t-test"
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class FakeResult:
    def __init__(self, scalar: Any = None, rows: list[dict[str, Any]] | None = None) -> None:
        self._scalar = scalar
        self._rows = rows or []

    def scalar(self) -> Any:
        return self._scalar

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class FakeConnection:
    """Records what was asked and answers the two queries this module issues."""

    def __init__(self, *, max_sequence: int = 0, rows: list[dict[str, Any]] | None = None) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self._max_sequence = max_sequence
        self._rows = rows or []
        self.begun = 0

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "MAX(sequence)" in sql:
            return FakeResult(scalar=self._max_sequence)
        if sql.strip().upper().startswith("SELECT ENTITY_ID"):
            return FakeResult(rows=self._rows)
        return FakeResult()

    def begin(self) -> "_Transaction":
        self.begun += 1
        return _Transaction()


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _ConnectionContext:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeReport:
    def __init__(self, stream: tuple[dict[str, Any], ...], subject: Any) -> None:
        self.stream = stream
        self.subject = subject


class FakeState:
    def __init__(self, values: tuple[str, ...], sources: tuple[str, ...]) -> None:
        self.values = values
        self.sources = sources


class FakeSubject:
    def __init__(self, entity_ref: str, attributes: dict[str, FakeState]) -> None:
        self.entity_ref = entity_ref
        self.attributes = attributes


def entry(sequence: int, *, source: str, when: datetime = NOW, record_hash: str = "") -> dict[str, Any]:
    return {
        "ts": when,
        "entity_id": "REF-1",
        "kind": f"observation:{source}",
        "sequence": sequence,
        "record_hash": record_hash or f"{'0' * 56}{sequence:08d}",
        "observation_id": "OBS-1",
        "payload": {"attribute": "country", "source": source, "records": 1},
    }


def test_a_sweep_is_written_as_one_transaction() -> None:
    connection = FakeConnection(max_sequence=7)
    report = FakeReport(
        (entry(1, source="rdap"), entry(2, source="crtsh")),
        FakeSubject("REF-1", {}),
    )

    asyncio.run(PostgresEnrichmentSink(lambda: _ConnectionContext(connection), tenant_id=TENANT)(report))

    assert connection.begun == 1, "a half-written sweep leaves a hole that reads as 'nothing happened'"
    inserts = [s for s in connection.statements if "INSERT INTO entity_stream" in s]
    assert len(inserts) == 2


def test_sequence_continues_the_stream_instead_of_restarting() -> None:
    """A second sweep must not collide with the first at sequence 1.

    The service numbers events within a run, which is right for a run and wrong for storage:
    restarting at 1 hits the composite primary key and every observation of the second sweep
    is dropped by the conflict clause.
    """
    connection = FakeConnection(max_sequence=41)
    report = FakeReport((entry(1, source="rdap"),), FakeSubject("REF-1", {}))

    asyncio.run(PostgresEnrichmentSink(lambda: _ConnectionContext(connection), tenant_id=TENANT)(report))

    assert connection.params[-1]["sequence"] == 42


def test_values_travel_with_the_source_that_produced_them() -> None:
    connection = FakeConnection()
    subject = FakeSubject("REF-1", {"country": FakeState(("US",), ("rdap",))})
    report = FakeReport((entry(1, source="rdap"),), subject)

    asyncio.run(PostgresEnrichmentSink(lambda: _ConnectionContext(connection), tenant_id=TENANT)(report))

    payload = json.loads(connection.params[-1]["payload"])
    assert payload["facts"] == [
        {"attribute": "country", "value": "US", "sources": ["rdap"]}
    ], "provenance that can be separated from its value is provenance that gets lost"


def test_a_sweep_with_no_events_writes_nothing() -> None:
    connection = FakeConnection()
    report = FakeReport((), FakeSubject("REF-1", {}))

    asyncio.run(PostgresEnrichmentSink(lambda: _ConnectionContext(connection), tenant_id=TENANT)(report))

    assert connection.statements == []
    assert connection.begun == 0


def test_a_subject_that_was_never_swept_has_no_dossier() -> None:
    """No rows is not an empty dossier; it is no dossier.

    Returning a blank artefact would make "we never looked" indistinguishable from "we
    looked and there is nothing", which is the distinction the whole coverage vocabulary
    exists to keep.
    """
    reader = DossierReader(lambda: _ConnectionContext(FakeConnection(rows=[])), tenant_id=TENANT)

    assert asyncio.run(reader.read("REF-missing")) is None


def test_a_persisted_sweep_reads_back_as_a_dossier() -> None:
    rows = [
        {
            "entity_id": "REF-1",
            "sequence": 1,
            "record_hash": "a" * 64,
            "kind": "observation:rdap",
            "ts": NOW,
            "observation_id": "OBS-1",
            "payload": {
                "facts": [
                    {"attribute": "country", "value": "US", "sources": ["rdap"]},
                    {"attribute": "registrar", "value": "GoDaddy", "sources": ["rdap"]},
                ]
            },
        },
        {
            "entity_id": "REF-1",
            "sequence": 2,
            "record_hash": "b" * 64,
            "kind": "observation:crtsh",
            "ts": NOW,
            "observation_id": "OBS-2",
            "payload": {
                "facts": [{"attribute": "country", "value": "IE", "sources": ["crtsh"]}]
            },
        },
    ]
    reader = DossierReader(lambda: _ConnectionContext(FakeConnection(rows=rows)), tenant_id=TENANT)

    dossier = asyncio.run(reader.read("REF-1", kind="domain"))

    assert dossier is not None
    assert dossier.identity.revision >= 1
    assert dossier.timeline, "a stream of events must produce a timeline"
    assert all(entry.event_count > 0 for entry in dossier.timeline)


def test_two_sources_disagreeing_produce_a_conflict_not_a_silent_winner() -> None:
    rows = [
        {
            "entity_id": "REF-1",
            "sequence": i + 1,
            "record_hash": chr(97 + i) * 64,
            "kind": "observation:s",
            "ts": NOW,
            "observation_id": f"OBS-{i}",
            "payload": {
                "facts": [{"attribute": "country", "value": value, "sources": [f"s{i}"]}]
            },
        }
        for i, value in enumerate(("US", "IE"))
    ]
    reader = DossierReader(lambda: _ConnectionContext(FakeConnection(rows=rows)), tenant_id=TENANT)

    dossier = asyncio.run(reader.read("REF-1", kind="domain"))

    assert dossier is not None
    disputed = [conflict for conflict in dossier.conflicts if conflict.subject == "country"]
    assert disputed, (
        "last-write-wins would have picked a country the platform has no basis for"
    )
    assert {side.value for side in disputed[0].sides} == {"US", "IE"}, (
        "both answers stay visible; neither is dropped as the stale one"
    )


def test_a_dossier_read_without_offices_says_it_does_not_know_its_coverage() -> None:
    rows = [
        {
            "entity_id": "REF-1",
            "sequence": 1,
            "record_hash": "c" * 64,
            "kind": "observation:rdap",
            "ts": NOW,
            "observation_id": "OBS-1",
            "payload": {},
        }
    ]
    reader = DossierReader(lambda: _ConnectionContext(FakeConnection(rows=rows)), tenant_id=TENANT)

    dossier = asyncio.run(reader.read("REF-1", kind="domain"))

    assert dossier is not None
    assert dossier.coverage.plan_known is False
    assert dossier.coverage.attributes is None, (
        "no offers means no coverage claim, not a coverage claim of none"
    )


def test_offers_turn_a_read_into_a_coverage_statement() -> None:
    rows = [
        {
            "entity_id": "REF-1",
            "sequence": 1,
            "record_hash": "d" * 64,
            "kind": "observation:rdap",
            "ts": NOW,
            "observation_id": "OBS-1",
            "payload": {
                "facts": [{"attribute": "country", "value": "US", "sources": ["rdap"]}]
            },
        }
    ]
    reader = DossierReader(lambda: _ConnectionContext(FakeConnection(rows=rows)), tenant_id=TENANT)
    offers = (
        CapabilityOffer("rdap", ("domain",), ("country", "registrar")),
        CapabilityOffer("crtsh", ("domain",), ("certificate",)),
    )

    dossier = asyncio.run(reader.read("REF-1", kind="domain", offers=offers))

    assert dossier is not None
    assert dossier.coverage.plan_known is True
    assert "registrar" in [gap.attribute for gap in dossier.gaps], (
        "an attribute nobody fetched is a gap, and stays visible"
    )