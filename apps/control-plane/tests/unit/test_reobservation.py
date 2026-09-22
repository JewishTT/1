"""Re-observation dedup + ETag three-way split (T101, R-08)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.reobservation import (
    Reobservation,
    ReobsOutcome,
    classify_reobservation,
    etag_equal,
    reobserve,
)


def test_etag_equal_weak_and_quoted() -> None:
    assert etag_equal('W/"abc"', "abc")
    assert etag_equal('"ABC"', "abc")
    assert not etag_equal("", "abc")
    assert not etag_equal("abc", "def")


def test_first_observation_created() -> None:
    reob = Reobservation(uri="https://a.x/", tenant_id="t1", new_digest="d1")
    assert reob.classify() == ReobsOutcome.CREATED
    assert reob.refetch_required()


def test_same_digest_unchanged() -> None:
    reob = Reobservation(
        uri="https://a.x/",
        tenant_id="t1",
        previous_digest="d1",
        new_digest="d1",
    )
    assert reob.classify() == ReobsOutcome.UNCHANGED
    assert not reob.refetch_required()


def test_different_digest_changed() -> None:
    reob = Reobservation(
        uri="https://a.x/",
        tenant_id="t1",
        previous_digest="d1",
        new_digest="d2",
    )
    assert reob.classify() == ReobsOutcome.CHANGED


def test_etag_match_skips_refetch() -> None:
    reob = Reobservation(
        uri="https://a.x/",
        tenant_id="t1",
        previous_etag='"abc"',
        new_etag="abc",
        previous_digest="d1",
        new_digest=None,
        has_body=False,
    )
    assert reob.classify() == ReobsOutcome.UNCHANGED
    assert not reob.refetch_required()


def test_etag_diff_no_body_requires_refetch() -> None:
    reob = Reobservation(
        uri="https://a.x/",
        tenant_id="t1",
        previous_etag='"abc"',
        new_etag='"def"',
        previous_digest="d1",
        has_body=False,
    )
    assert reob.classify() == ReobsOutcome.CHANGED
    assert reob.refetch_required()


def test_duplicate_coalesced() -> None:
    reob = Reobservation(
        uri="https://a.x/",
        tenant_id="t1",
        new_digest="d3",
        already_seen=True,
    )
    assert reob.classify() == ReobsOutcome.DUPLICATE


def test_classify_reobservation_dict_api() -> None:
    result = classify_reobservation(
        {"digest": "old", "etag": '"x"'},
        {"uri": "https://a.x/", "tenant_id": "t1", "etag": "x"},
    )
    assert result["outcome"] == "unchanged"
    assert result["refetch_required"] is False
    assert result["etag_match"] is True


def test_reobserve_decision_carries_checkpoint() -> None:
    decision = reobserve(
        {"digest": "old"},
        {"uri": "https://a.x/", "tenant_id": "t1", "digest": "new"},
    )
    assert decision.outcome == ReobsOutcome.CHANGED
    assert decision.digest == "new"
    assert "digest-differ" in decision.reasons