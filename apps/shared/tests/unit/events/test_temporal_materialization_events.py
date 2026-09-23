"""Temporal materialization event contract tests."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from domain.dynamics import StreamRecord
from domain.stream_events import materialization_event_envelope
from domain.temporal_materialization import materialize_history
from events.topics import topic_for


def test_materialization_event_is_refs_only_and_idempotent() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    history = materialize_history(
        [
            StreamRecord(
                entity_id="e1",
                kind="fact",
                ts=t0,
                tenant_id="t1",
                payload={"event_at": t0.isoformat()},
                sequence=1,
            )
        ],
        tenant_id="t1",
        entity_id="e1",
    )
    first = materialization_event_envelope(
        history, event_type="temporal.materialization.ready", run_id="run-1"
    )
    second = materialization_event_envelope(
        history, event_type="temporal.materialization.ready", run_id="run-1"
    )
    assert first.event_id == second.event_id == f"evt-{history.publication.integrity_fingerprint}"
    payload = json.loads(first.payload)
    assert set(payload) == {
        "run_id",
        "entity_id",
        "publication_id",
        "source_cut_id",
        "projection_generation",
        "integrity_fingerprint",
    }
    assert topic_for("temporal.materialization.ready") == "temporal-materialization"
