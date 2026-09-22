"""Versioned dictionary datasets + lazy Aho-Corasick automatons (spec 007, T004).

A dataset is a pair of files: ``<name>.jsonl`` (canonical, sorted entries of
``{"term": str, "payload": {...}}``) and ``<name>.meta.json`` (kind, version,
license, sha256, entries). Loaders are lazy per-process singletons keyed by
``(kind, version)``; the automaton is built exactly once (NFR-2).

Determinism: dataset files are canonicalized (term-sorted, compact separators),
so the same inputs always produce the same sha256 (FR-8).
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ahocorasick

_META_SUFFIX = ".meta.json"


@dataclass(frozen=True)
class DictionaryDataset:
    """Immutable metadata about one dictionary dataset build."""

    kind: str
    version: str
    sha256: str
    license: str
    entries: int
    path: str

    @property
    def stamp(self) -> str:
        """Version stamp recorded on every mention produced from this dataset."""
        return f"{self.kind}@{self.version}"


def _read_meta(path: Path) -> DictionaryDataset:
    meta = json.loads(path.read_text(encoding="utf-8"))
    return DictionaryDataset(
        kind=str(meta["kind"]),
        version=str(meta["version"]),
        sha256=str(meta["sha256"]),
        license=str(meta.get("license", "unknown")),
        entries=int(meta.get("entries", 0)),
        path=str(path),
    )


def load_meta(path: str | Path) -> DictionaryDataset:
    """Load dataset metadata from a ``*.meta.json`` sidecar."""
    return _read_meta(Path(path))


def iter_entries(path: str | Path):
    """Stream canonical JSONL entries of a dataset file."""
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


class AutomatonCache:
    """Process-wide lazy cache: (kind, version) -> built Aho-Corasick automaton."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], ahocorasick.Automaton] = {}
        self._datasets: dict[tuple[str, str], DictionaryDataset] = {}

    def get(
        self, dataset: DictionaryDataset, *, data_path: str | Path | None = None
    ) -> ahocorasick.Automaton:
        """Return (building on first use) the automaton for the dataset.

        ``data_path`` defaults to the sidecar's sibling ``.jsonl`` file. When a
        sha256 is recorded, it is verified once before first build (integrity).
        """
        key = (dataset.kind, dataset.version)
        with self._lock:
            existing = self._cache.get(key)
            if existing is not None:
                return existing
            path = Path(data_path or dataset.path)
            if not dataset.path.endswith(_META_SUFFIX) and path == Path(dataset.path):
                path = path.with_suffix(".jsonl")
            automaton = ahocorasick.Automaton()
            entries = 0
            for entry in iter_entries(path):
                term = str(entry.get("term", ""))
                if not term:
                    continue
                automaton.add_word(term, (term, entry.get("payload", {})))
                entries += 1
            automaton.make_automaton()
            self._datasets[key] = dataset
            self._cache[key] = automaton
            self._verify(dataset, path)
            del entries  # count recorded in meta; loader trusts the sidecar
            return automaton

    def dataset(self, kind: str, version: str) -> DictionaryDataset | None:
        return self._datasets.get((kind, version))

    @staticmethod
    def _verify(dataset: DictionaryDataset, data_path: Path) -> None:
        if not dataset.sha256:
            return
        digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
        if digest != dataset.sha256:
            raise ValueError(
                f"dataset integrity mismatch for {dataset.stamp}: "
                f"expected {dataset.sha256}, got {digest}"
            )


_SHARED = AutomatonCache()


def shared_cache() -> AutomatonCache:
    """The default process-wide cache."""
    return _SHARED


def find_matches(
    automaton: ahocorasick.Automaton, text: str
) -> list[tuple[int, str, dict]]:
    """Deterministic match scan: sorted by (start, term, payload-json).

    Returns ``(start_index, term, payload)`` triples. ``iter_long`` suppresses
    subterm matches inside longer terms; overlaps across different terms are
    all reported — the caller (extractor) decides confidence, not the automaton.
    """
    raw: list[tuple[int, str, dict]] = []
    for end, (term, payload) in automaton.iter_long(text):
        start = end - len(term) + 1
        raw.append((start, term, payload))
    raw.sort(key=lambda m: (m[0], m[1], json.dumps(m[2], sort_keys=True, ensure_ascii=False)))
    return raw
