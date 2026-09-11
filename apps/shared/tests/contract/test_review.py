"""Contract tests: review append-only provenance (T017, FR-006, Vitni pattern)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest

from domain import ReviewAppendOnlyError, enforce_review_append_only


@pytest.mark.contract
class TestReviewAppendOnly:
    def test_unchanged_review_passes(self) -> None:
        existing = {"review_id": "RV-1", "decision": "ACCEPT", "analyst_id": "a1"}
        assert enforce_review_append_only(existing, {"decision": "ACCEPT"})["review_id"] == "RV-1"

    def test_decision_change_rejected(self) -> None:
        existing = {"review_id": "RV-2", "decision": "ACCEPT"}
        with pytest.raises(ReviewAppendOnlyError):
            enforce_review_append_only(existing, {"decision": "REJECT"})

    def test_analyst_change_rejected(self) -> None:
        existing = {"review_id": "RV-3", "decision": "ACCEPT", "analyst_id": "a1"}
        with pytest.raises(ReviewAppendOnlyError):
            enforce_review_append_only(existing, {"analyst_id": "a2"})

    def test_error_code_is_fr006(self) -> None:
        err = ReviewAppendOnlyError("RV-4")
        assert err.code == "FR-006"
        assert "RV-4" in str(err)