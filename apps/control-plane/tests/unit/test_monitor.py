"""Monitor counters, atomic updates, snapshot, late-event parking (T030, US5).

Independent test: counters advance atomically; snapshot persists on close
(COMPLETED); a late event after COMPLETED is parked — state unmutated and a
``governance.quarantined`` refs-only envelope is emitted.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from cp_domain.investigation import (
    MONITOR_COUNTERS,
    Investigation,
    InvestigationMonitor,
    InvestigationState,
    LateEventParked,
)


class _Emitter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, str | None]] = []

    def __call__(self, topic: str, envelope: Any, key: str | None) -> None:
        self.calls.append((topic, envelope, key))


def _investigation(**overrides: Any) -> Investigation:
    kwargs = {
        "investigation_id": "INV-X",
        "name": "probe",
        "tenant_id": "t1",
        "objective": {"question": "who?"},
    }
    kwargs.update(overrides)
    return Investigation(**kwargs)


class TestMonitorCounters:
    def test_default_counters_all_zero(self) -> None:
        monitor = InvestigationMonitor()
        for name in MONITOR_COUNTERS:
            assert monitor.counters[name] == 0

    def test_update_counter_advances_atomically(self) -> None:
        inv = _investigation()
        at = datetime(2026, 1, 1, tzinfo=UTC)
        assert inv.update_counter("items_examined", delta=2, at=at) == 2
        assert inv.update_counter("evidence_ingested", delta=1, at=at) == 1
        assert inv.update_counter("candidates_resolved", delta=2, at=at) == 2
        assert inv.update_counter("candidates_resolved", delta=-1, at=at) == 1
        assert inv.monitor.updates == 4
        assert inv.monitor.counters["items_examined"] == 2

    def test_unknown_counter_rejected(self) -> None:
        inv = _investigation()
        with pytest.raises(ValueError):
            inv.update_counter("nope")

    def test_non_integer_delta_rejected(self) -> None:
        inv = _investigation()
        with pytest.raises(TypeError):
            inv.update_counter("items_examined", delta="2")
        with pytest.raises(TypeError):
            inv.update_counter("items_examined", delta=True)
        assert inv.monitor.counters["items_examined"] == 0

    def test_cannot_undershoot_zero_atomically(self) -> None:
        inv = _investigation()
        with pytest.raises(ValueError):
            inv.update_counter("items_examined", delta=-1)
        assert inv.monitor.counters["items_examined"] == 0
        assert inv.monitor.updates == 0


def _running(overrides: dict[str, Any] | None = None) -> Investigation:
    inv = _investigation(**(overrides or {}))
    inv.start()
    inv.run()
    return inv


class TestSnapshot:
    def test_snapshot_persists_on_close(self) -> None:
        inv = _running()
        inv.update_counter("items_examined", delta=10)
        inv.update_counter("findings_created", delta=3)
        inv.transition(InvestigationState.COMPLETED)
        closed = inv.snapshot()
        assert closed["investigation_id"] == "INV-X"
        assert closed["state"] == "COMPLETED"
        assert closed["counters"] == {
            "items_examined": 10,
            "evidence_ingested": 0,
            "candidates_resolved": 0,
            "findings_created": 3,
        }
        assert closed["counter_updates"] == 2
        assert closed["snapshot_at"]

    def test_snapshot_after_parked_event_is_unchanged(self) -> None:
        inv = _running()
        inv.update_counter("items_examined", delta=5)
        inv.transition(InvestigationState.COMPLETED)
        before = inv.snapshot()["counters"]
        with pytest.raises(LateEventParked):
            inv.update_counter("candidates_resolved", delta=1)
        assert inv.snapshot()["counters"] == before


class TestLateEventParking:
    def test_late_counter_after_completed_is_parked(self) -> None:
        inv = _investigation(state=InvestigationState.COMPLETED)
        with pytest.raises(LateEventParked) as exc_info:
            inv.update_counter("items_examined", delta=1)
        assert exc_info.value.investigation_id == "INV-X"
        assert exc_info.value.counter == "items_examined"
        assert exc_info.value.state is InvestigationState.COMPLETED
        assert inv.monitor.counters["items_examined"] == 0

    def test_archived_is_terminal_too(self) -> None:
        inv = _investigation(state=InvestigationState.ARCHIVED)
        with pytest.raises(LateEventParked):
            inv.update_counter("evidence_ingested")
        assert inv.monitor.counters["evidence_ingested"] == 0

    def test_emits_governance_quarantined_with_emitter(self) -> None:
        emitter = _Emitter()
        inv = _investigation(state=InvestigationState.COMPLETED, emitter=emitter)
        with pytest.raises(LateEventParked):
            inv.update_counter("findings_created", delta=2)
        assert len(emitter.calls) == 1
        topic, envelope, key = emitter.calls[0]
        assert topic == "governance"
        assert envelope.event_type == "governance.quarantined"
        assert key == "INV-X"
        body = json.loads(envelope.payload)
        assert body["reason"] == "investigation_late_counter"
        assert body["investigation_id"] == "INV-X"
        assert body["counter"] == "findings_created"
        assert body["delta"] == 2

    def test_emitter_is_idempotent_no_writer_skip(self) -> None:
        before = _investigation(state=InvestigationState.COMPLETED)
        with pytest.raises(LateEventParked):
            before.update_counter("evidence_ingested")
        assert before.monitor.counters["evidence_ingested"] == 0