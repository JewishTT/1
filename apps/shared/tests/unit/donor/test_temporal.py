"""Unit tests for donor/temporal.py (investigator port, spec 004)."""

from donor.temporal import (
    DATE_CONFLICT_DAYS,
    as_date_list,
    date_spread_conflict,
    dates_compatible,
    ordering_conflicts,
    parse_iso_date,
    scan,
    to_iso_date,
)


def test_parse_iso_date_precision() -> None:
    assert parse_iso_date("2024-05-10") == (2024, 5, 10)
    assert parse_iso_date("2024-05") == (2024, 5, 0)
    assert parse_iso_date("2024") == (2024, 0, 0)
    assert parse_iso_date("nope") is None
    assert parse_iso_date("") is None


def test_to_iso_date_normalises_formats() -> None:
    assert to_iso_date("2024-05-10T12:00:00Z") == "2024-05-10"
    assert to_iso_date("20240510T120000Z") == "2024-05-10"
    assert to_iso_date("Wed, 15 May 2024 12:00:00 GMT") == "2024-05-15"
    assert to_iso_date("garbage") == ""


def test_dates_compatible_window() -> None:
    assert dates_compatible(["2024-05-10"], ["2024-05-12"], window_days=3)
    assert not dates_compatible(["2024-05-01"], ["2024-06-01"], window_days=3)


def test_dates_compatible_year_only_is_liberal() -> None:
    assert dates_compatible(["2024"], ["2024-06-01"], window_days=3)


def test_spread_conflict_detected() -> None:
    c = date_spread_conflict(["2024-05-10", "2024-09-20"])
    assert c is not None
    assert c["daysApart"] > DATE_CONFLICT_DAYS
    assert c["min"] == "2024-05-10"
    assert c["max"] == "2024-09-20"


def test_spread_conflict_within_window_is_ok() -> None:
    assert date_spread_conflict(["2024-05-10", "2024-05-20"]) is None


def test_year_only_never_conflicts() -> None:
    assert date_spread_conflict(["2024", "2025"]) is None


def test_single_date_never_conflicts() -> None:
    assert date_spread_conflict(["2024-05-10"]) is None


def test_ordering_conflict_detected() -> None:
    dates = {"ev-1": ["2024-05-10"], "ev-2": ["2024-09-20"]}
    edges = [{"type": "event_followed_by", "src": "ev-2", "dst": "ev-1"}]
    found = ordering_conflicts(dates, edges)
    assert len(found) == 1
    assert found[0]["src"] == "ev-2"
    assert found[0]["dst"] == "ev-1"
    assert found[0]["daysApart"] > DATE_CONFLICT_DAYS


def test_ordering_conflict_skips_wrong_edge_types() -> None:
    dates = {"ev-1": ["2024-05-10"], "ev-2": ["2024-09-20"]}
    edges = [{"type": "mentioned_with", "src": "ev-1", "dst": "ev-2"}]
    assert ordering_conflicts(dates, edges) == []


def test_ordering_conflict_tolerant_of_identifier_keys() -> None:
    dates = {"ev-1": ["2024-05-10"], "ev-2": ["2024-09-20"]}
    edges = [{"type": "event_followed_by", "src_identifier": "ev-2", "dst_identifier": "ev-1"}]
    assert len(ordering_conflicts(dates, edges)) == 1


def test_scan_returns_both_detectors() -> None:
    dates = {
        "ev-1": ["2024-05-10", "2024-09-20"],
        "ev-2": ["2024-05-10"],
    }
    edges = [{"type": "event_followed_by", "src": "ev-1", "dst": "ev-2"}]
    result = scan(dates, edges)
    assert "ev-1" in result["events"]
    assert result["orderings"] == []


def test_scan_empty_inputs_are_stable() -> None:
    assert scan({}, []) == {"events": {}, "orderings": []}


def test_as_date_list_normalises_scalars() -> None:
    assert as_date_list(None) == []
    assert as_date_list("2024-05-10") == ["2024-05-10"]
    assert as_date_list(["a", "", "b"]) == ["a", "b"]