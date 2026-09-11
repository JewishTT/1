"""Tests for Flink stateful stream jobs (T079, US3).

Temporal windows, stream joins, change detection — genuine stateful work only
(FR-021); no transport logic lives here.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from streams.jobs import ChangeDetector, StreamJoin, TemporalWindow, WindowEvent


def _t(y, m, d, h=0, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=UTC)


_at = lambda h, mi, s: _t(2026, 1, 1, h, mi, s)


class TestTemporalWindow:
    def test_counts_into_tumbling_window(self):
        win = TemporalWindow(size=timedelta(minutes=1), metric="count")
        win.add(WindowEvent(key="src-a", at=_at(12, 0, 10)))
        win.add(WindowEvent(key="src-a", at=_at(12, 0, 50)))
        emitted = win.emit_completed(_at(12, 1, 5))
        assert len(emitted) == 1
        assert emitted[0].value == 2
        assert emitted[0].metric == "count"

    def test_different_windows_stay_separate(self):
        win = TemporalWindow(size=timedelta(minutes=1))
        win.add(WindowEvent(key="k", at=_at(12, 0, 5)))
        win.add(WindowEvent(key="k", at=_at(12, 1, 5)))
        emitted = win.emit_completed(_at(12, 2, 0))
        assert len(emitted) == 2

    def test_sums_values(self):
        win = TemporalWindow(size=timedelta(minutes=5), metric="obs_bytes")
        win.add(WindowEvent(key="k", at=_at(0, 0, 0), value=100.0))
        win.add(WindowEvent(key="k", at=_at(0, 1, 0), value=50.0))
        emitted = win.emit_completed(_at(0, 6, 0))
        assert emitted[0].value == 150.0


class TestStreamJoin:
    def test_joins_on_atom_within_window(self):
        join = StreamJoin(window=timedelta(seconds=10))
        join.add_left("ent-1", _at(12, 0, 0), {"atom": "mention", "mention_id": "M1"})
        join.add_right("ent-1", _at(12, 0, 5), {"atom": "observation", "obs_id": "OBS-9"})
        pairs = join.join("mention")
        assert len(pairs) == 1
        assert pairs[0].right["obs_id"] == "OBS-9"

    def test_out_of_window_does_not_join(self):
        join = StreamJoin(window=timedelta(seconds=1))
        join.add_left("ent-1", _at(12, 0, 0), {"atom": "mention", "m": 1})
        join.add_right("ent-1", _at(12, 1, 0), {"atom": "observation", "o": 2})
        assert join.join("mention") == []


class TestChangeDetector:
    def test_detects_value_change(self):
        d = ChangeDetector()
        assert d.observe("acct", _at(0, 0, 0), "A") is True  # first sighting
        assert d.observe("acct", _at(0, 0, 1), "A") is False  # unchanged
        assert d.observe("acct", _at(0, 0, 2), "B") is True  # pattern change

    def test_independent_keys(self):
        d = ChangeDetector()
        d.observe("k1", _at(0, 0, 0), "x")
        assert d.observe("k2", _at(0, 0, 0), "y") is True  # not conflated with k1