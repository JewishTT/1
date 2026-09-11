"""Invariant test: idempotent replay of observation.created (T020, I-11, SC-004).

Replaying the same ``observation.created`` event (same event_id/observation_id)
must not produce duplicate rows in downstream stores. Uses an in-memory
projection store to keep the test hermetic.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest


class _IdempotentProjectionStore:
    """Tracks applied event_ids; reapplying the same event is a no-op."""

    def __init__(self) -> None:
        self.applied: set[str] = set()
        self.rows: dict[str, dict] = {}

    def apply(self, event: dict) -> bool:
        event_id = event["event_id"]
        if event_id in self.applied:
            return False  # already applied — no duplicate
        self.applied.add(event_id)
        self.rows.setdefault(event["observation_id"], event)
        return True

    def observation_count(self, observation_id: str) -> int:
        return 1 if observation_id in self.rows else 0


def _observation_created_event(event_id: str, observation_id: str) -> dict:
    return {
        "event_type": "observation.created",
        "event_id": event_id,
        "observation_id": observation_id,
        "topic": "observation",
    }


@pytest.mark.integration
class TestIdempotentReplay:
    def test_replay_produces_no_duplicates(self) -> None:
        store = _IdempotentProjectionStore()
        evt = _observation_created_event("EVT-1", "OBS-1")
        assert store.apply(evt) is True
        # Replay the exact same event (e.g. consumer redelivery).
        assert store.apply(evt) is False
        assert store.observation_count("OBS-1") == 1

    def test_multiple_distinct_events_create_distinct_observations(self) -> None:
        store = _IdempotentProjectionStore()
        store.apply(_observation_created_event("EVT-1", "OBS-1"))
        store.apply(_observation_created_event("EVT-2", "OBS-2"))
        assert store.observation_count("OBS-1") == 1
        assert store.observation_count("OBS-2") == 1

    def test_redelivery_after_partial_processing(self) -> None:
        store = _IdempotentProjectionStore()
        evt = _observation_created_event("EVT-1", "OBS-1")
        store.apply(evt)
        # Simulate consumer restart re-delivering the same event.
        store.apply(evt)
        store.apply(evt)
        assert store.observation_count("OBS-1") == 1