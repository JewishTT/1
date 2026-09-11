"""Temporal conflict detection for investigation timelines (spec 004).

Attribution / license
=====================
Source: `investigator` (MIT, Copyright (c) 2026 Dima S)
  - ``src/investigator/graph/temporal_consistency.py``
  - date primitives from ``src/investigator/graph/dedup.py``
    (``_event_dates``, ``_parse_iso_date``, ``to_iso_date``, ``_dates_compatible``)
License: MIT.

Adaptation notes
================
- Donor imports of the whole dedup module's heavy deps (numpy/semhash/wordllama)
  are removed: only the stdlib date primitives are cut.
- Names renamed to COGNITIVE style (private ``_x`` → public ``x`` where used
  across functions; ``_dates_compatible`` → ``dates_compatible``).
- ``scan`` result key ``events`` maps event-id → conflict (unchanged), plus
  ``orderings`` for directed ``event_followed_by`` edges whose dates disagree.
- No pipeline re-run: pure read-time pass over ``{event_id: [date, ...]}`` maps.
"""

from __future__ import annotations

import calendar
import datetime
import re

__all__ = [
    "DATE_CONFLICT_DAYS",
    "as_date_list",
    "date_spread_conflict",
    "dates_compatible",
    "ordering_conflicts",
    "parse_iso_date",
    "scan",
    "to_iso_date",
]

DATE_CONFLICT_DAYS = 30


def as_date_list(value) -> list[str]:
    """Normalise a (possibly scalar / None) date value to a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if x]
    return [str(value).strip()] if str(value).strip() else []


def parse_iso_date(s: str) -> tuple[int, int, int] | None:
    """Best-effort parse of ISO-8601 dates (YYYY, YYYY-MM, YYYY-MM-DD) into a
    (year, month, day) tuple. Returns None when unrecognisable. Missing
    components are filled with 0 (a sentinel; date comparison treats 0-month
    and 0-day as wildcards)."""
    if not s:
        return None
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", s)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


def to_iso_date(value) -> str:
    """Normalise a publication-date string to ``YYYY-MM-DD`` (or "" if
    unparseable). Article sources emit several formats (RFC-2822, GDELT compact,
    plain ISO); this collapses them to a plain ISO day (time-of-day dropped)."""
    s = str(value or "").strip()
    if not s:
        return ""
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    if m:
        return m.group(0)
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt.date().isoformat()
    except Exception:  # noqa: BLE001 - best-effort normalisation
        pass
    return ""


def dates_compatible(a_dates: list[str], b_dates: list[str], *, window_days: int) -> bool:
    """True iff at least one date on each side is within ``window_days`` of the
    other. Wildcards (missing day, missing month, empty) match liberally."""
    if not a_dates or not b_dates:
        return True
    for a in a_dates:
        pa = parse_iso_date(a)
        if pa is None:
            continue
        ya, ma, da = pa
        for b in b_dates:
            pb = parse_iso_date(b)
            if pb is None:
                continue
            yb, mb, db = pb
            if ya != yb:
                continue
            if ma == 0 or mb == 0:
                return True
            if ma != mb:
                try:
                    da_x = datetime.date(ya, ma, da or 1)
                    db_x = datetime.date(yb, mb, db or 1)
                    if abs((da_x - db_x).days) <= window_days:
                        return True
                except ValueError:
                    pass
                continue
            if da == 0 or db == 0:
                return True
            if abs(da - db) <= window_days:
                return True
    return False


def _interval(s: str) -> tuple[datetime.date, datetime.date] | None:
    """A date string -> the [earliest, latest] day it could mean, or None when
    too imprecise (year-only) or unparseable. Month-only -> the whole month."""
    p = parse_iso_date(s)
    if p is None:
        return None
    y, m, d = p
    if m == 0:
        return None
    try:
        if d == 0:
            return datetime.date(y, m, 1), datetime.date(y, m, calendar.monthrange(y, m)[1])
        return datetime.date(y, m, d), datetime.date(y, m, d)
    except ValueError:
        return None


def _intervals(dates) -> list[tuple[datetime.date, datetime.date]]:
    out = []
    for s in as_date_list(dates):
        iv = _interval(str(s))
        if iv:
            out.append(iv)
    return out


def date_spread_conflict(dates, *, tol_days: int = DATE_CONFLICT_DAYS) -> dict | None:
    """Flag a date set that cannot all fall within ``tol_days``.

    Conservative: uses the latest lower-bound and earliest upper-bound across
    the precision-aware intervals, so imprecise dates can't manufacture a
    conflict. Returns ``{"min", "max", "daysApart"}`` or None."""
    ivs = _intervals(dates)
    if len(ivs) < 2:
        return None
    latest_lo = max(lo for lo, _ in ivs)
    earliest_hi = min(hi for _, hi in ivs)
    gap = (latest_lo - earliest_hi).days
    if gap > tol_days:
        return {
            "min": min(lo for lo, _ in ivs).isoformat(),
            "max": max(hi for _, hi in ivs).isoformat(),
            "daysApart": gap,
        }
    return None


def _edge_ends(e: dict) -> tuple[str | None, str | None]:
    """Endpoints of an ordering edge, tolerant of the sidecar (src/dst) and
    payload/raw (source/target, src_identifier/dst_identifier) key names."""
    src = e.get("src") or e.get("source") or e.get("src_identifier")
    dst = e.get("dst") or e.get("target") or e.get("dst_identifier")
    return src, dst


def ordering_conflicts(
    event_dates: dict,
    ordering_edges: list,
    *,
    tol_days: int = DATE_CONFLICT_DAYS,
) -> list[dict]:
    """Flag ``event_followed_by`` edges (src = earlier, dst = later) whose dates
    contradict the ordering: the earliest src can be is still later than the
    latest dst can be, by more than ``tol_days``."""
    out = []
    for e in ordering_edges or []:
        if (e.get("type") or "") != "event_followed_by":
            continue
        src, dst = _edge_ends(e)
        sd = _intervals(event_dates.get(src, []))
        dd = _intervals(event_dates.get(dst, []))
        if not sd or not dd:
            continue
        src_lo = min(lo for lo, _ in sd)
        dst_hi = max(hi for _, hi in dd)
        gap = (src_lo - dst_hi).days
        if gap > tol_days:
            out.append({
                "src": src,
                "dst": dst,
                "srcDate": src_lo.isoformat(),
                "dstDate": dst_hi.isoformat(),
                "daysApart": gap,
            })
    return out


def scan(
    event_dates: dict,
    ordering_edges: list,
    *,
    tol_days: int = DATE_CONFLICT_DAYS,
) -> dict:
    """Run both detectors over an ``{event_id: [date, ...]}`` map + ordering
    edges. Returns ``{"events": {id: conflict}, "orderings": [conflict, ...]}``."""
    events = {}
    for eid, dates in (event_dates or {}).items():
        c = date_spread_conflict(dates, tol_days=tol_days)
        if c:
            events[eid] = c
    return {
        "events": events,
        "orderings": ordering_conflicts(event_dates, ordering_edges, tol_days=tol_days),
    }