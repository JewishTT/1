"""Bounded parallel seed processing and deterministic wave ordering."""
from __future__ import annotations

import threading
import time

from zero.harvest_wave import HarvestWave
from zero.harvesters.public_document import PublicDocumentHarvester
from zero.harvesters.registry import HarvesterRegistry
from zero.type_detector import TypeDetector


class ConcurrentTransport:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.maximum = 0
        self.calls: list[str] = []

    def fetch(self, url: str, timeout: float = 5.0) -> str:
        with self._lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            self.calls.append(url)
        try:
            time.sleep(0.03)
            return f"<html><head><title>Public page {url}</title></head><body></body></html>"
        finally:
            with self._lock:
                self.active -= 1

    def exists(self, url: str, timeout: float = 5.0) -> bool:
        return False


def test_seed_processing_is_parallel_bounded_and_ordered() -> None:
    transport = ConcurrentTransport()
    registry = HarvesterRegistry(max_workers=1)
    registry.register(PublicDocumentHarvester())
    wave = HarvestWave(
        detector=TypeDetector(),
        registry=registry,
        transport=transport,
        max_depth=1,
        min_new_seeds=0,
        enable_enrichment=False,
        max_seed_workers=3,
    )

    summaries = wave.run([
        "https://example.org/c",
        "https://example.org/a",
        "https://example.org/b",
        "https://example.org/a",
    ])

    assert summaries[0].seeds_in == 3
    assert len(transport.calls) == 3
    assert transport.maximum == 3
    harvest_records = [record for record in wave.stage_records if record.stage == "HARVEST"]
    assert [record.seed_value for record in harvest_records] == [
        "https://example.org/a",
        "https://example.org/b",
        "https://example.org/c",
    ]
    assert all(record.as_dict()["claim_admission_allowed"] is False for record in wave.stage_records)


def test_seed_worker_limit_is_validated() -> None:
    try:
        HarvestWave(max_seed_workers=0)
    except ValueError as exc:
        assert "max_seed_workers" in str(exc)
    else:  # pragma: no cover - test assertion
        raise AssertionError("zero seed workers must be rejected")
