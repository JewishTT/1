"""Unit tests: CC temporality orchestrator (CC-TEMPORALITY v1).

Hermetic: a fake L0 session (list of fixture index rows) — no networks, no
CC_INDEX_PATH. Honesty (I-3) cases are covered explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from api.sse import hub
from network.cc_session import CCPageRecord
from services.cc_temporality import run_cc_temporality


class FakeIndexSession:
    """Fake CC index slice: deterministic rows, no DuckDB, no I/O (I-11)."""

    crawl = "CC-MAIN-2023-40"

    def __init__(self, rows: list[CCPageRecord]) -> None:
        self._rows = rows
        self.queries: list[str] = []

    def query_domain(self, url_pattern: str) -> list[CCPageRecord]:
        self.queries.append(url_pattern)
        return self._rows


def _row(url: str, ts: str, digest: str, status: int = 200) -> CCPageRecord:
    return CCPageRecord(
        url=url,
        timestamp=ts,
        status=status,
        mime="text/html",
        digest=digest,
        warc_filename="crawl.warc.gz",
        offset=0,
        length=1024,
        crawl="CC-MAIN-2023-40",
    )


def _session() -> FakeIndexSession:
    return FakeIndexSession(
        [
            _row("https://example.com/a", "20231012030104", "sha256:a1"),
            _row("https://example.com/b", "20231014000000", "sha256:b2"),
            # duplicate digest — collapsed by L0 transport dedup
            _row("https://example.com/a-mirror", "20231012030104", "sha256:a1"),
        ]
    )


DOMAIN_IDENTITY = {"domain": "example.com"}


@pytest.mark.unit
class TestRunCcTemporality:
    def test_full_circle_domain_identity(self) -> None:
        session = _session()
        payload = run_cc_temporality("ENT-CC-1", DOMAIN_IDENTITY, session=session)

        assert session.queries == ["example.com"]
        assert payload["plan"]["kind"] == "domain"
        assert payload["plan"]["match_type"] == "domain"
        assert payload["plan"]["surt_prefix"] == "http://com,example,"
        assert payload["plan"]["limit"] == 50
        # L0 transport dedup collapsed the mirror row
        assert len(payload["captures"]) == 2
        assert payload["captures"][0]["observed_at"] == "2023-10-12T03:01:04Z"
        assert payload["series"] == [
            {"t": "2023-10-12", "count": 1},
            {"t": "2023-10-14", "count": 1},
        ]
        assert payload["metrics"]["events_per_day"] > 0
        assert payload["notes"] == []
        assert payload["entity_id"] == "ENT-CC-1"

    def test_publishes_sse_event(self) -> None:
        published = hub.publish("cc.temporality", {})
        assert published >= 0  # hub stays usable after the orchestrator publishes
        payload = run_cc_temporality("ENT-CC-1", DOMAIN_IDENTITY, session=_session())
        backlog = [p for t, p in hub.backlog() if t == "cc.temporality"]
        assert backlog and backlog[-1]["entity_id"] == payload["entity_id"]

    def test_empty_identity_is_honest(self) -> None:
        payload = run_cc_temporality("ENT-CC-2", {})
        assert payload["plan"] is None
        assert payload["captures"] == []
        assert payload["series"] == []
        assert payload["metrics"] == {"burstiness": None, "events_per_day": None}
        assert any("insufficient data" in n for n in payload["notes"])

    def test_no_captures_is_honest(self) -> None:
        payload = run_cc_temporality(
            "ENT-CC-3", DOMAIN_IDENTITY, session=FakeIndexSession([])
        )
        assert payload["plan"] is not None  # the plan exists, the index is just empty
        assert payload["captures"] == []
        assert payload["series"] == []
        assert payload["metrics"]["burstiness"] is None
        assert any("no captures" in n for n in payload["notes"])

    def test_unparseable_timestamps_yield_empty_series_with_note(self) -> None:
        rows = [_row("https://example.com/x", "garbage!!", "sha256:x1")]
        payload = run_cc_temporality(
            "ENT-CC-4", DOMAIN_IDENTITY, session=FakeIndexSession(rows)
        )
        assert payload["captures"] == []
        assert payload["series"] == []
        assert any("insufficient data" in n for n in payload["notes"])

    def test_prefix_match_for_url_identity(self) -> None:
        session = FakeIndexSession(
            [
                _row("https://example.com/docs/x", "20231012030104", "sha256:d1"),
                _row("https://example.com/other", "20231013000000", "sha256:e1"),
            ]
        )
        payload = run_cc_temporality(
            "ENT-CC-5", {"url": "https://example.com/docs"}, session=session
        )
        assert payload["plan"]["kind"] == "url"
        assert payload["plan"]["match_type"] == "prefix"
        # only the /docs/ subtree survives the prefix filter
        assert [c["url"] for c in payload["captures"]] == ["https://example.com/docs/x"]
        assert payload["series"] == [{"t": "2023-10-12", "count": 1}]

    def test_single_capture_burstiness_is_none_not_fabricated(self) -> None:
        rows = [_row("https://example.com/one", "20231012030104", "sha256:f1")]
        payload = run_cc_temporality(
            "ENT-CC-6", DOMAIN_IDENTITY, session=FakeIndexSession(rows)
        )
        assert len(payload["captures"]) == 1
        assert payload["metrics"]["burstiness"] is None
        assert payload["metrics"]["events_per_day"] > 0
