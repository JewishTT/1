"""Collector replay / resume journal (T120, T127b).

A collector crash must not re-emit observations it already gated. Before
writing to the store, the observation pipeline marks each accepted record in a
durable journal (the manifest's processed set). On resume, the collector replays
its pending manifest and *skips every already-processed record* — exactly-once
resumable collection without a central dedup service.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

# A record is "processed" once it passed the Observation Gate.
record_key = tuple[str, str, str]  # (source, uri, digest)


def _key(record: dict) -> record_key:
    source = str(record.get("source_type") or record.get("source") or "unknown")
    uri = str(record.get("uri") or "")
    digest = str(record.get("digest") or "")
    return (source, uri, digest)


class Journal(Protocol):
    def mark_processed(self, record: dict) -> None: ...
    def is_processed(self, record: dict) -> bool: ...
    def resume(self, manifest: list[dict]) -> list[dict]: ...
    def processed_count(self) -> int: ...


class MemoryReplayJournal:
    """In-process journal (hermetic tests / single-worker deployments)."""

    def __init__(self) -> None:
        self._seen: set[record_key] = set()

    def mark_processed(self, record: dict) -> None:
        self._seen.add(_key(record))

    def is_processed(self, record: dict) -> bool:
        return _key(record) in self._seen

    def resume(self, manifest: list[dict]) -> list[dict]:
        return [r for r in manifest if not self.is_processed(r)]

    def processed_count(self) -> int:
        return len(self._seen)


class FileReplayJournal:
    """Durable append-only JSONL journal; safe on crash (fsync per line).

    ``path`` is the journal file; ``mark_processed`` appends one JSON line per
    record. Missing/corrupt tail lines are tolerated on load.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._seen: set[record_key] = set()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._seen.add(_key(payload))

    def mark_processed(self, record: dict) -> None:
        key = _key(record)
        if key in self._seen:
            return
        line = json.dumps(
            {"source": key[0], "uri": key[1], "digest": key[2], "at": time.time()},
            separators=(",", ":"),
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
        self._seen.add(key)

    def is_processed(self, record: dict) -> bool:
        return _key(record) in self._seen

    def resume(self, manifest: list[dict]) -> list[dict]:
        return [r for r in manifest if not self.is_processed(r)]

    def processed_count(self) -> int:
        return len(self._seen)


def replay_collector(
    journal: Journal,
    manifest: list[dict],
    *,
    consumed: Iterator[None] | None = None,
) -> Iterator[dict]:
    """Yield manifest records the journal has not yet accepted.

    Calling code feeds the yield to the Observation Gate and then marks the
    record processed — a crash between gate-write and mark is replayed once
    (at-least-once toward the journal, exactly-once toward the gate thanks to
    content addressing).
    """
    for record in journal.resume(manifest):
        if consumed is not None:
            next(consumed, None)
        yield record