"""Collector replay / resume journal (T120, T127b)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from observation_gate.replay import (  # noqa: E402
    FileReplayJournal,
    MemoryReplayJournal,
    replay_collector,
)

RECORDS = [
    {"source_type": "http", "uri": "https://a.x/1", "digest": "d1"},
    {"source_type": "http", "uri": "https://a.x/2", "digest": "d2"},
    {"source_type": "warc", "uri": "https://a.x/3", "digest": "d3"},
]


def test_memory_journal_resumes_unprocessed_only() -> None:
    journal = MemoryReplayJournal()
    journal.mark_processed(RECORDS[0])
    pending = journal.resume(RECORDS)
    assert [r["uri"] for r in pending] == ["https://a.x/2", "https://a.x/3"]
    assert journal.processed_count() == 1


def test_file_journal_survives_reopen() -> None:
    path = Path("replay_test.jsonl")
    first = FileReplayJournal(path)
    first.mark_processed(RECORDS[0])
    first.mark_processed(RECORDS[1])
    second = FileReplayJournal(path)
    assert second.is_processed(RECORDS[0])
    assert second.is_processed(RECORDS[1])
    assert not second.is_processed(RECORDS[2])
    assert [r["uri"] for r in second.resume(RECORDS)] == ["https://a.x/3"]
    path.unlink(missing_ok=True)


def test_file_journal_tolerates_corrupt_tail() -> None:
    path = Path("replay_corrupt.jsonl")
    good = FileReplayJournal(path)
    good.mark_processed(RECORDS[0])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{\"broken\": \n")
    revived = FileReplayJournal(path)
    assert revived.is_processed(RECORDS[0])
    assert [r["uri"] for r in revived.resume(RECORDS)] == ["https://a.x/2", "https://a.x/3"]
    path.unlink(missing_ok=True)


def test_replay_collector_skips_processed_and_yields_rest() -> None:
    journal = MemoryReplayJournal()
    journal.mark_processed(RECORDS[0])
    yielded = list(replay_collector(journal, RECORDS))
    assert yielded == [RECORDS[1], RECORDS[2]]


def test_mark_is_idempotent() -> None:
    journal = MemoryReplayJournal()
    journal.mark_processed(RECORDS[0])
    journal.mark_processed(RECORDS[0])
    assert journal.processed_count() == 1