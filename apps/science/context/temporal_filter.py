"""Honour the temporal clause — `CURRENT`, `AS_OF` and `INTERVAL` are different questions.

The query compiler already parses all three (``query_grammar`` → ``TemporalClause``) and
validates them (``AS_OF`` needs a timestamp, ``INTERVAL`` needs a bound). Nothing executed
them: the clause was carried through the AST and dropped, so a caller who asked ``as_of
2025-06-01`` received the same rows as a caller who asked for ``current``. That is the
blueprint's §7 failure in its purest form — a temporal question answered with a different
question.

The three modes, as the blueprint defines them:

``CURRENT``
    The current reconstruction: every fact whose validity covers the instant the caller
    names, restricted to what has been recorded by then. There is no wall clock here; the
    caller supplies ``now``, because a filter that reads a clock cannot be replayed.

``AS_OF(t)``
    **What the system knew at ``t``** — not what was true then. A fact captured in 2026 about
    2020 was not known in 2025 and must not appear in an ``AS_OF(2025)`` answer, even though
    its validity covers that year. This is the distinction the blueprint calls
    ``AS_OF(known_time)`` versus ``INTERVAL(valid_time)``.

``INTERVAL(a, b)``
    What was true in a window, regardless of when it was learned. A late capture *does* refine
    this answer: that is the point of ``INTERVAL``. It is also why ``AS_OF`` must not be
    implemented as ``INTERVAL`` — doing so rewrites history by making the platform appear to
    have known in 2025 what it learned in 2026.

Unknown clocks are excluded from the mode that needs them and counted, never guessed. A fact
with no ``known_at`` cannot be shown to have been known at ``t``, so it is not returned for
``AS_OF(t)``; a fact with no validity cannot be shown to cover a window, so it is not returned
for ``INTERVAL``. Both absences are reported, because "the platform has no such fact" and "the
platform has it and cannot date it" are different answers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from context.completeness import TemporalMode
from context.query_ast import TemporalClause

__all__ = [
    "TemporalFact",
    "TemporalSelection",
    "apply_temporal",
    "parse_instant",
]


def parse_instant(text: str | None) -> datetime | None:
    """Parse an ISO-8601 instant, or ``None`` when there is no instant to parse.

    Refuses to invent one: an empty string, a date without a time, and a naive datetime all
    return ``None`` rather than being assumed UTC. A timestamp the platform made up is worse
    than a missing one, because it survives every downstream comparison.
    """
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


@dataclass(frozen=True, slots=True)
class TemporalFact:
    """One dated, recorded fact — the minimum a temporal filter needs.

    ``known_at`` is when the platform recorded it; ``valid_from``/``valid_to`` is the period
    it speaks about. Either may be ``None``, meaning genuinely unknown; the filter never
    substitutes a value.
    """

    fact_id: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    known_at: datetime | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def covers(self, moment: datetime) -> bool:
        """Whether the validity interval contains ``moment``; a half-open interval."""
        if self.valid_from is None and self.valid_to is None:
            return False
        if self.valid_from is not None and moment < self.valid_from:
            return False
        if self.valid_to is not None and moment >= self.valid_to:
            return False
        return True

    def overlaps(self, start: datetime | None, end: datetime | None) -> bool:
        """Whether the validity interval intersects ``[start, end)``.

        An unbounded validity intersects any finite window — that is what unbounded means —
        but a fact with *no* validity bounds at all has no interval to intersect and is not
        returned. The distinction is ``unbounded`` versus ``undated``.
        """
        if self.valid_from is None and self.valid_to is None:
            return False
        if end is not None and self.valid_from is not None and self.valid_from >= end:
            return False
        if start is not None and self.valid_to is not None and self.valid_to <= start:
            return False
        return True

    def known_by(self, moment: datetime) -> bool:
        return self.known_at is not None and self.known_at <= moment


@dataclass(frozen=True, slots=True)
class TemporalSelection:
    """The selected facts, the mode that selected them, and what could not be decided."""

    mode: TemporalMode
    facts: tuple[TemporalFact, ...]
    excluded_unknown_known_at: tuple[str, ...] = ()
    excluded_unknown_validity: tuple[str, ...] = ()
    known_cut: datetime | None = None

    @property
    def fact_ids(self) -> tuple[str, ...]:
        return tuple(fact.fact_id for fact in self.facts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "known_cut": self.known_cut.isoformat() if self.known_cut else None,
            "fact_ids": list(self.fact_ids),
            "excluded_unknown_known_at": list(self.excluded_unknown_known_at),
            "excluded_unknown_validity": list(self.excluded_unknown_validity),
        }


def apply_temporal(
    facts: Iterable[TemporalFact],
    clause: TemporalClause,
    *,
    now: datetime | None = None,
) -> TemporalSelection:
    """Filter ``facts`` by ``clause``.

    ``now`` is required for ``CURRENT`` and is deliberately not defaulted to the wall clock:
    a reconstruction that cannot be replayed is not a reconstruction. It is ignored for the
    other two modes, which are both defined by an explicit bound.
    """
    pool = tuple(facts)
    mode = TemporalMode(clause.mode)

    if mode is TemporalMode.CURRENT:
        if now is None:
            raise ValueError(
                "CURRENT needs the instant it is current at; a filter that reads the wall clock "
                "cannot be replayed against the same evidence"
            )
        return TemporalSelection(
            mode=mode,
            facts=tuple(f for f in pool if f.covers(now) and (f.known_at is None or f.known_by(now))),
            known_cut=now,
        )

    if mode is TemporalMode.AS_OF:
        cut = parse_instant(clause.timestamp)
        if cut is None:
            raise ValueError(
                f"AS_OF needs a parseable, timezone-aware timestamp; got {clause.timestamp!r}. "
                "Assuming a zone would silently shift the knowledge cut"
            )
        dated = [f for f in pool if f.known_at is not None]
        undated = tuple(f.fact_id for f in pool if f.known_at is None)
        return TemporalSelection(
            mode=mode,
            facts=tuple(f for f in dated if f.known_by(cut)),
            excluded_unknown_known_at=undated,
            known_cut=cut,
        )

    if mode is TemporalMode.INTERVAL:
        start = parse_instant(clause.start)
        end = parse_instant(clause.end)
        if start is None and end is None:
            raise ValueError(
                f"INTERVAL needs at least one parseable bound; got start={clause.start!r} "
                f"end={clause.end!r}"
            )
        undated = tuple(f.fact_id for f in pool if f.valid_from is None and f.valid_to is None)
        return TemporalSelection(
            mode=mode,
            facts=tuple(f for f in pool if f.overlaps(start, end)),
            excluded_unknown_validity=undated,
        )

    raise ValueError(f"unknown temporal mode {mode!r}")
