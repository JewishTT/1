"""Temporal metrics of an atomic entity's life-stream (FR-007, 011).

Honest derived statistics over the event series of a single atomic entity —
the *momentary projection* (L1) recomputed from the delimiter stream (L0).
Every measure is a pure, deterministic function of (timestamp, value);
the empty input is mapped to the empty output (Invariant I-3: no fabricated
points, no interpolation).

Measures (processed day / window aggregation):
- ``burstiness``       B = (sigma/mu - 1) / (sigma/mu + 1)  in [-1, 1]
  periodic = -1, Poisson ~ 0, a single dense burst = 1.
- ``causal_fidelity``  c = |temporal shortest paths| / |static paths|:
  how much information a *clock* (ordering) actually carries vs a static
  graph.  == 1.0 means the temporal ordering adds nothing (|| the metric is
  indistinguishable from a plain graph) — a real answer to "why hypergraph?".
- ``characteristic_timescale``  median latency of the time-respecting graph:
  default window for higher-order / TDA slices (no Newtonian instantaneity).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any


def _intervals(timestamps: Sequence[datetime]) -> list[float]:
    """Second-scale deltas between consecutive events (>=2 events)."""
    if len(timestamps) < 2:
        return []
    return [
        (later - earlier).total_seconds()
        for earlier, later in zip(timestamps, timestamps[1:], strict=False)
    ]


def burstiness(timestamps: Sequence[datetime]) -> float:
    """Burstiness B in [-1, 1] (edges to a human-readable density).

    B == -1  perfectly periodic;  B == 0  Poisson;  B == 1  single mega-burst.
    """
    deltas = _intervals(timestamps)
    if not deltas:
        raise ValueError("burstiness requires >=2 events (I-3: no fabrications)")
    mean = sum(deltas) / len(deltas)
    if mean == 0:
        return 1.0
    variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)
    sigma = math.sqrt(variance)
    ratio = sigma / mean
    return (ratio - 1.0) / (ratio + 1.0)


def events_per_day(timestamps: Sequence[datetime]) -> float:
    """Aggregated rate: number of events / wall-clock days spanned."""
    if not timestamps:
        return 0.0
    start, end = min(timestamps), max(timestamps)
    span_days = max((end - start).total_seconds() / 86400.0, 1e-9)
    return len(timestamps) / span_days


def characteristic_timescale(timestamps: Sequence[datetime]) -> float:
    """Median event inter-arrival (seconds) — the *natural* TDA window.

    When the stream is empty, returns 0.0 (I-3).
    """
    deltas = _intervals(timestamps)
    if not deltas:
        return 0.0
    ordered = sorted(deltas)
    n = len(ordered)
    if n % 2 == 1:
        return ordered[n // 2]
    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0


def causal_fidelity(timestamps: Sequence[datetime]) -> float:
    """c in [0, 1] — how much temporal ordering matters (Holme & Saramäki).

    Answer to "why a *temporal* hypergraph and not a static graph?":
    temporal reachability ratio. A time-respecting path between events i<j
    exists iff no intermediate inter-arrival gap exceeds the natural window
    ``w = 3 * mean_gap``. Counting reachable pairs vs ALL ordered pairs:

      - perfectly uniform *clock* stream: every gap is intra-window ⇒ all
        pairs reachable ⇒ c → 1.0 (ordering adds nothing; "static graph" is
        an adequate model);
      - bursty / sparse stream: any gap > w severs every pair that spans it
        ⇒ c → 0 (the *clock matters*; a static graph would lie to you).

    A trivially short stream (2 events) is, by definition, one edge ⇒ c = 1.0.
    """
    n = len(timestamps)
    if n < 2:
        return 0.0
    deltas = _intervals(timestamps)
    mean_gap = sum(deltas) / len(deltas)
    if mean_gap == 0:
        return 1.0
    # a time-respecting path hops event->event; each individual hop must fit
    # inside the natural window (3x the average gap). Pairs are reachable iff
    # EVERY intermediate consecutive gap is within the window — not the total
    # span (a uniform clock stream has all hops within window => c = 1.0).
    window = 3.0 * mean_gap
    reachable = 0
    total = n * (n - 1) // 2
    for start in range(n - 1):
        for end in range(start + 1, n):
            hop_range = deltas[start:end]
            if (max(hop_range) if hop_range else 0.0) <= window:
                reachable += 1
    return max(0.0, min(reachable / max(total, 1), 1.0))


def temporal_metrics(timestamps: Sequence[datetime]) -> dict[str, Any]:
    """Deterministic, honest summary of an atomic life-stream (FR-007).

    Empty stream ⇒ {} (I-3).
    """
    if not timestamps:
        return {}
    try:
        b = burstiness(timestamps)
    except ValueError:
        b = None
    c = causal_fidelity(timestamps)
    return {
        "n_points": len(timestamps),
        "burstiness_b": b,
        "events_per_day": events_per_day(timestamps),
        "characteristic_timescale_s": characteristic_timescale(timestamps),
        "causal_fidelity_c": c,
    }


__all__ = [
    "burstiness",
    "causal_fidelity",
    "characteristic_timescale",
    "events_per_day",
    "temporal_metrics",
]