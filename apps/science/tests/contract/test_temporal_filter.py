"""`CURRENT`, `AS_OF` and `INTERVAL` are three questions, and they get three answers.

The blueprint's §7 is explicit: *"Нельзя подставлять `now()` вместо неизвестного времени.
Нельзя приравнивать source time к capture time"*, and a late capture *"может уточнить текущую
реконструкцию прошлого `INTERVAL`, но не изменяет историю `AS_OF` на время до регистрации
этого capture"*.

Before this suite, all three modes parsed and none executed: the clause reached the AST and was
dropped, so `as_of 2025-06-01` returned the same rows as `current`. These tests are built
around the golden case that exposes the difference — a 2026 capture asserting a fact whose
validity is 2020.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "science"))

from context.completeness import TemporalMode
from context.query_ast import TemporalClause
from context.temporal_filter import TemporalFact, apply_temporal, parse_instant

pytestmark = pytest.mark.contract


def _t(*parts: int) -> datetime:
    year, month, day = parts[0], parts[1], parts[2]
    hour = parts[3] if len(parts) > 3 else 0
    return datetime(year, month, day, hour, tzinfo=UTC)


#: The golden case: a fact about 2020, captured in 2026.
LATE = TemporalFact(
    fact_id="F-LATE",
    valid_from=_t(2020, 1, 1),
    valid_to=_t(2021, 1, 1),
    known_at=_t(2026, 10, 19),
)

#: A fact about 2020 that the platform learned in 2020.
EARLY = TemporalFact(
    fact_id="F-EARLY",
    valid_from=_t(2020, 1, 1),
    valid_to=_t(2021, 1, 1),
    known_at=_t(2020, 3, 1),
)

#: A current fact: valid from 2024, still open.
OPEN = TemporalFact(
    fact_id="F-OPEN",
    valid_from=_t(2024, 1, 1),
    valid_to=None,
    known_at=_t(2024, 1, 5),
)

#: No clocks at all — the case that must never be guessed.
UNDATED = TemporalFact(fact_id="F-UNDATED")

POOL = (LATE, EARLY, OPEN, UNDATED)


# ---------------------------------------------------------------------------
# The three modes answer three different questions
# ---------------------------------------------------------------------------


def test_interval_includes_the_late_capture_because_it_was_true_then() -> None:
    selection = apply_temporal(
        POOL, TemporalClause(mode=TemporalMode.INTERVAL, start="2020-02-01T00:00:00Z", end="2020-06-01T00:00:00Z")
    )

    assert set(selection.fact_ids) == {"F-LATE", "F-EARLY"}, (
        "INTERVAL asks what was true in a window; the platform learned F-LATE in 2026, but "
        "the fact was true in 2020 and a late capture is exactly what refines this answer"
    )


def test_as_of_before_the_capture_excludes_it() -> None:
    selection = apply_temporal(
        POOL, TemporalClause(mode=TemporalMode.AS_OF, timestamp="2025-06-01T00:00:00Z")
    )

    assert selection.fact_ids == ("F-EARLY", "F-OPEN"), (
        "AS_OF asks what the system knew at that instant. F-LATE was learned in 2026, so an "
        "AS_OF(2025) answer that contains it rewrites history"
    )
    assert "F-UNDATED" in selection.excluded_unknown_known_at, (
        "a fact with no known_at cannot be shown to have been known then; it is excluded and "
        "reported, never assumed"
    )


def test_as_of_after_the_capture_includes_it() -> None:
    selection = apply_temporal(
        POOL, TemporalClause(mode=TemporalMode.AS_OF, timestamp="2026-10-20T00:00:00Z")
    )

    assert set(selection.fact_ids) == {"F-LATE", "F-EARLY", "F-OPEN"}


def test_current_returns_what_is_valid_now() -> None:
    selection = apply_temporal(POOL, TemporalClause(mode=TemporalMode.CURRENT), now=_t(2026, 10, 19))

    assert selection.fact_ids == ("F-OPEN",), (
        "only F-OPEN's validity covers 2026; the 2020 facts are historical"
    )


def test_the_three_modes_are_distinct_on_the_same_pool() -> None:
    """The defect this file exists for: all three used to return the same rows."""
    current = apply_temporal(POOL, TemporalClause(mode=TemporalMode.CURRENT), now=_t(2026, 10, 19))
    as_of = apply_temporal(
        POOL, TemporalClause(mode=TemporalMode.AS_OF, timestamp="2025-06-01T00:00:00Z")
    )
    interval = apply_temporal(
        POOL, TemporalClause(mode=TemporalMode.INTERVAL, start="2020-02-01T00:00:00Z", end="2020-06-01T00:00:00Z")
    )

    assert len({current.fact_ids, as_of.fact_ids, interval.fact_ids}) == 3


# ---------------------------------------------------------------------------
# Refusals: no invented instants
# ---------------------------------------------------------------------------


def test_current_requires_an_explicit_instant() -> None:
    with pytest.raises(ValueError, match="cannot be replayed"):
        apply_temporal(POOL, TemporalClause(mode=TemporalMode.CURRENT))


def test_as_of_refuses_an_unparseable_timestamp() -> None:
    with pytest.raises(ValueError, match="parseable"):
        apply_temporal(POOL, TemporalClause(mode=TemporalMode.AS_OF, timestamp="last tuesday"))


def test_a_naive_timestamp_is_not_assumed_utc() -> None:
    assert parse_instant("2025-06-01T00:00:00") is None, (
        "a naive datetime has no zone; assuming UTC silently shifts the knowledge cut by the "
        "caller's offset"
    )
    assert parse_instant("2025-06-01T00:00:00Z") is not None


def test_a_date_without_a_time_is_not_an_instant() -> None:
    assert parse_instant("2025-06-01") is None


def test_interval_refuses_when_neither_bound_parses() -> None:
    with pytest.raises(ValueError, match="at least one parseable bound"):
        apply_temporal(POOL, TemporalClause(mode=TemporalMode.INTERVAL, start="soon"))


# ---------------------------------------------------------------------------
# Interval boundaries: half-open, and undated is not unbounded
# ---------------------------------------------------------------------------


def test_the_interval_end_is_exclusive() -> None:
    at_end = apply_temporal(
        POOL, TemporalClause(mode=TemporalMode.INTERVAL, start="2021-01-01T00:00:00Z", end="2022-01-01T00:00:00Z")
    )
    assert "F-EARLY" not in at_end.fact_ids, "a half-open interval does not include its end"


def test_an_undated_fact_is_not_treated_as_unbounded() -> None:
    selection = apply_temporal(
        POOL, TemporalClause(mode=TemporalMode.INTERVAL, start="2020-01-01T00:00:00Z", end="2027-01-01T00:00:00Z")
    )
    assert "F-UNDATED" not in selection.fact_ids, (
        "a fact with no validity bounds has no interval to intersect; 'unbounded' and "
        "'undated' are different claims"
    )
    assert "F-UNDATED" in selection.excluded_unknown_validity


def test_an_open_ended_fact_stays_current() -> None:
    selection = apply_temporal(POOL, TemporalClause(mode=TemporalMode.CURRENT), now=_t(2030, 1, 1))
    assert "F-OPEN" in selection.fact_ids
