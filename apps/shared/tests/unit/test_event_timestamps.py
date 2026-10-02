"""Feature 024 T013/T014 -- logical-time convention (D5=b).

The convention is specified in specs/024-context-driven-continuous-intelligence/
contracts.md and implemented in events.timestamps. These tests keep the two honest
against each other: the module's behaviour must match what the document promises.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from events.timestamps import (  # noqa: E402
    LOGICAL_TIME,
    NO_LOGICAL_TIME,
    OBSERVED_AT,
    TimestampContractError,
    validate_against_produced_at,
    validate_payload,
)

ET = "observation.created"


def test_observed_at_satisfied():
    validate_payload(ET, {OBSERVED_AT: "2026-10-02T10:00:00Z"})


def test_logical_time_satisfied():
    validate_payload(ET, {LOGICAL_TIME: {"from": "2026-01-01T00:00:00Z", "to": "2026-06-01T00:00:00Z"}})


def test_missing_time_rejected():
    with pytest.raises(TimestampContractError, match="carries no observed_at"):
        validate_payload(ET, {"record_digest": "abc"})


def test_registered_no_logical_time_allowed():
    et = "__test_transport_signal__"
    NO_LOGICAL_TIME[et] = "transport-level health signal, no evidence time"
    try:
        validate_payload(et, {"status": "ok"})
    finally:
        del NO_LOGICAL_TIME[et]


def test_naive_timestamp_rejected():
    with pytest.raises(TimestampContractError, match="timezone-naive"):
        validate_payload(ET, {OBSERVED_AT: "2026-10-02T10:00:00"})


def test_garbage_timestamp_rejected():
    with pytest.raises(TimestampContractError, match="not RFC 3339"):
        validate_payload(ET, {OBSERVED_AT: "yesterday"})


def test_inverted_logical_time_rejected():
    with pytest.raises(TimestampContractError, match="inverted"):
        validate_payload(ET, {LOGICAL_TIME: {"from": "2026-06-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"}})


def test_logical_time_missing_bound_rejected():
    with pytest.raises(TimestampContractError, match="missing 'to'"):
        validate_payload(ET, {LOGICAL_TIME: {"from": "2026-01-01T00:00:00Z"}})


def test_produced_at_copy_rejected():
    ts = "2026-10-02T10:00:00Z"
    with pytest.raises(TimestampContractError, match="not evidence time"):
        validate_against_produced_at(ET, {OBSERVED_AT: ts}, ts)


def test_produced_at_distinct_is_fine():
    validate_against_produced_at(
        ET, {OBSERVED_AT: "2026-01-01T00:00:00Z"}, "2026-10-02T10:00:00Z"
    )


def test_non_mapping_payload_rejected():
    with pytest.raises(TimestampContractError, match="must be a mapping"):
        validate_payload(ET, ["not", "a", "mapping"])
