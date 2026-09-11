"""Contract tests: statement-level provenance (T011, FR-001, FollowTheMoney pattern)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest

from domain import StatementProvenanceError, enforce_statement_provenance


@pytest.mark.contract
class TestStatementProvenance:
    def test_complete_statement_passes(self) -> None:
        stmt = {
            "statement_id": "ST-1",
            "dataset_id": "ds-fixtures",
            "extraction_version": "extractor-v1",
            "original_value": "ACME GmbH",
        }
        assert enforce_statement_provenance(stmt)["dataset_id"] == "ds-fixtures"

    @pytest.mark.parametrize("missing", ["dataset_id", "extraction_version", "original_value"])
    def test_missing_field_rejected(self, missing: str) -> None:
        stmt = {
            "statement_id": "ST-2",
            "dataset_id": "ds",
            "extraction_version": "v1",
            "original_value": "x",
        }
        stmt.pop(missing)
        with pytest.raises(StatementProvenanceError):
            enforce_statement_provenance(stmt)

    def test_error_code_is_fr001(self) -> None:
        err = StatementProvenanceError("ST-3", "dataset_id")
        assert err.code == "FR-001"
        assert "ST-3" in str(err)