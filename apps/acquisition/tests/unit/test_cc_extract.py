"""CC capture normalization unit tests (CC-TEMPORALITY v1, task_0006).

Hermetic: raw ``Mapping`` records (the L0/L1 boundary), no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cc_extract import (  # noqa: E402
    CaptureObservation,
    iso_utc_from_cc_timestamp,
    normalize_captures,
)


def test_cc_14_digit_timestamp_to_iso_utc() -> None:
    assert iso_utc_from_cc_timestamp("20231012000000") == "2023-10-12T00:00:00Z"
    assert iso_utc_from_cc_timestamp("20231231235959") == "2023-12-31T23:59:59Z"
    assert iso_utc_from_cc_timestamp(" 20240229120000 ") == "2024-02-29T12:00:00Z"


def test_invalid_timestamps_rejected() -> None:
    assert iso_utc_from_cc_timestamp("") is None
    assert iso_utc_from_cc_timestamp("2023") is None
    assert iso_utc_from_cc_timestamp("2023-10-12T00:00:00Z") is None
    assert iso_utc_from_cc_timestamp("2023101200000a") is None


def test_normalize_single_record() -> None:
    obs = normalize_captures(
        [
            {
                "url": "https://example.com/a",
                "timestamp": "20231012000000",
                "digest": "abc",
                "status": "200",
                "mime": "text/html",
                "length": 456,
                "collection": "CC-MAIN-2023-40",
            }
        ]
    )
    assert obs == [
        CaptureObservation(
            url="https://example.com/a",
            observed_at="2023-10-12T00:00:00Z",
            status=200,
            digest="abc",
            crawl="CC-MAIN-2023-40",
            length=456,
        )
    ]


def test_normalize_sorts_by_observed_at() -> None:
    obs = normalize_captures(
        [
            {"url": "https://e.com/later", "timestamp": "20240101000000", "digest": "d2"},
            {"url": "https://e.com/earlier", "timestamp": "20231012000000", "digest": "d1"},
        ]
    )
    assert [o.url for o in obs] == ["https://e.com/earlier", "https://e.com/later"]


def test_normalize_preserves_locator_provenance() -> None:
    obs = normalize_captures(
        [
            {
                "url": "https://e.com/a",
                "fetch_time": "20231012000000",
                "fetch_status": "200",
                "content_mime_type": "text/html",
                "content_digest": "abc",
                "crawl": "CC-MAIN-2024-10",
                "subset": "warc",
                "warc_filename": "crawl/0.warc.gz",
                "warc_record_offset": 10,
                "warc_record_length": 456,
                "warc_record_id": "record-1",
            }
        ]
    )[0]
    assert obs.crawl == "CC-MAIN-2024-10"
    assert obs.subset == "warc"
    assert obs.locator == "crawl/0.warc.gz@10,456"
    assert obs.warc_record_id == "record-1"


def test_normalize_dedups_by_digest_and_observed_at() -> None:
    raw = [
        {"url": "https://e.com/a", "timestamp": "20231012000000", "digest": "abc"},
        {"url": "https://e.com/a", "timestamp": "20231012000000", "digest": "abc"},
        {"url": "https://e.com/a", "timestamp": "20231012000000", "digest": "xyz"},
        {"url": "https://e.com/a", "timestamp": "20231013000000", "digest": "abc"},
    ]
    obs = normalize_captures(raw)
    assert len(obs) == 3
    assert all(isinstance(o, CaptureObservation) for o in obs)


def test_normalize_drops_malformed_records() -> None:
    obs = normalize_captures(
        [
            {"url": "", "timestamp": "20231012000000", "digest": "d"},
            {"timestamp": "20231012000000", "digest": "d"},
            {"url": "https://e.com/x", "digest": "d"},
            {"url": "https://e.com/x", "timestamp": "not-a-timestamp", "digest": "d"},
        ]
    )
    assert obs == []


def test_normalize_accepts_pre_iso_observed_at() -> None:
    obs = normalize_captures(
        [{"url": "https://e.com/a", "observed_at": "2023-10-12T00:00:00Z", "digest": "d"}]
    )
    assert obs[0].observed_at == "2023-10-12T00:00:00Z"


def test_normalize_empty_input() -> None:
    assert normalize_captures([]) == []


def test_normalize_status_defaults_to_zero() -> None:
    obs = normalize_captures([{"url": "https://e.com/a", "timestamp": "20231012000000"}])
    assert obs[0].status == 0
