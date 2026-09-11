"""Contract tests: correlation without destruction (T016, FR-004, OpenOSINT pattern)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest

from domain import CorrelationNoMergeError, enforce_correlation_no_merge


@pytest.mark.contract
class TestCorrelationNoMerge:
    def test_possible_match_edge_allowed(self) -> None:
        edge = {"edge_id": "CE-1", "kind": "possible_match", "raw_pair_score": 0.7}
        assert enforce_correlation_no_merge(edge)["kind"] == "possible_match"

    def test_auto_merge_flag_rejected(self) -> None:
        with pytest.raises(CorrelationNoMergeError):
            enforce_correlation_no_merge({"edge_id": "CE-2", "auto_merge": True})

    def test_merge_flag_rejected(self) -> None:
        with pytest.raises(CorrelationNoMergeError):
            enforce_correlation_no_merge({"edge_id": "CE-3", "merge": True})

    def test_error_code_is_i2(self) -> None:
        assert CorrelationNoMergeError().code == "I-2"