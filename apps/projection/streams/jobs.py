"""Flink stateful stream jobs (T079, US3, FR-021).

Genuine stateful work only — temporal windows, stream joins, change/pattern
detection, real-time counters, online signals — never transport. These jobs
enrich/reduce event streams; the durable event history stays in Kafka and each
job is a rebuildable projection. The engines are pure (Flink-agnostic) so they
run in tests and on a real Flink cluster behind a thin adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class WindowEvent:
    key: str
    at: datetime
    value: float = 1.0
    kind: str = "observation"


@dataclass
class WindowedStat:
    key: str
    window_start: datetime
    window_end: datetime
    metric: str = "count"
    value: float = 0.0


class TemporalWindow:
    """Tumbling window aggregation over a keyed stream (stateful job)."""

    def __init__(self, size: timedelta, metric: str = "count") -> None:
        self.size = size
        self.metric = metric
        # window_start(epoch) -> {key: running sum}
        self._state: dict[datetime, dict[str, float]] = {}
        self.completed: list[WindowedStat] = []

    def _window_start(self, at: datetime) -> datetime:
        epoch = int(at.timestamp()) // int(self.size.total_seconds()) * int(self.size.total_seconds())
        return datetime.fromtimestamp(epoch, tz=UTC)

    def add(self, event: WindowEvent) -> None:
        start = self._window_start(event.at)
        bucket = self._state.setdefault(start, {})
        bucket[event.key] = bucket.get(event.key, 0.0) + event.value

    def emit_completed(self, up_to: datetime) -> list[WindowedStat]:
        """Emit and drop windows fully before `up_to` (watermark)."""
        cutoff = self._window_start(up_to)
        emit: list[WindowedStat] = []
        for start in sorted(self._state):
            if start < cutoff:
                bucket = self._state.pop(start)
                for key, value in bucket.items():
                    emit.append(
                        WindowedStat(
                            key=key,
                            window_start=start,
                            window_end=start + self.size,
                            metric=self.metric,
                            value=value,
                        )
                    )
        self.completed.extend(emit)
        return emit


@dataclass
class JoinPair:
    left: dict
    right: dict


class StreamJoin:
    """Windowed stream join for change/pattern detection (e.g., entity mentions
    joined to source/observation metadata)."""

    def __init__(self, window: timedelta) -> None:
        self.window = window
        self._left: list[tuple[datetime, dict]] = []
        self._right: list[tuple[datetime, dict]] = []

    def add_left(self, key: str, at: datetime, fields: dict) -> None:
        self._left.append((at, {"key": key, **fields}))

    def add_right(self, key: str, at: datetime, fields: dict) -> None:
        self._right.append((at, {"key": key, **fields}))

    def join(self, atom: str, grace: timedelta = timedelta(seconds=5)) -> list[JoinPair]:
        """Nested-loop join within the windowed time band (small hermetic test
        of the pattern; production adapter uses Flink interval joins)."""
        pairs: list[JoinPair] = []
        for lat, l in self._left:
            for rat, r in self._right:
                if (
                    l["key"] == r["key"]
                    and atom in (l.get("atom"), r.get("atom"))
                    and abs((lat - rat).total_seconds()) <= (self.window + grace).total_seconds()
                ):
                    pairs.append(JoinPair(left=l, right=r))
        return pairs


class ChangeDetector:
    """Detects a value change for a key across the stream (change/pattern)."""

    def __init__(self) -> None:
        self._last: dict[str, tuple[datetime, object]] = {}

    def observe(self, key: str, at: datetime, value: object) -> bool:
        """Returns True when the value changed for this key."""
        prev = self._last.get(key)
        changed = prev is None or prev[1] != value
        self._last[key] = (at, value)
        return changed