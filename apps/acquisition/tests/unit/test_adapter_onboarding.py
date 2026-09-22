"""Adapter onboarding unit tests (US2 Scenario B): registration is the only path."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

import importlib

import adapters.commoncrawl  # noqa: F401 (registers 'commoncrawl')
import adapters.scrapy  # noqa: F401  (registers 'webpage')
import adapters.warc  # noqa: F401   (registers 'webarchive')
import pytest
from adapters.registry import REGISTRY, CapabilityGap

worker_dataset = importlib.import_module("worker-dataset")  # registers 'dataset'


@pytest.fixture(autouse=True)
def _clean_registry():
    adapters = REGISTRY._sources
    saved = dict(adapters)
    adapters.clear()
    yield
    adapters.clear()
    adapters.update(saved)


def _reregister_all() -> None:
    from adapters.commoncrawl.index import discover
    from adapters.registry import register
    from adapters.scrapy.stream import scrapy_crawl
    from adapters.warc.collect import adapt_warc

    acquire = worker_dataset.acquire
    register("webpage", execution_class="http", capabilities={"http", "get"}, adapter=scrapy_crawl)
    register(
        "webarchive",
        execution_class="archival",
        capabilities={"warc", "range-read"},
        adapter=adapt_warc,
    )
    register(
        "commoncrawl",
        execution_class="archival",
        capabilities={"warc", "range-read", "bulk"},
        adapter=discover,
    )
    register(
        "dataset",
        execution_class="dataset",
        capabilities={"parquet", "bulk", "range-read"},
        adapter=acquire,
    )


def test_every_new_engine_registers_without_core_edits() -> None:
    _reregister_all()
    types = {reg.source_type for reg in REGISTRY}
    assert {"webpage", "webarchive", "commoncrawl", "dataset"} <= types


@pytest.mark.parametrize(
    ("required", "expected"),
    [
        ({"http", "get"}, "webpage"),
        ({"warc", "range-read"}, "webarchive"),
        ({"warc", "range-read", "bulk"}, "commoncrawl"),
        ({"parquet", "bulk"}, "dataset"),
        ({"javascript"}, None),
    ],
)
def test_capability_intersection_selects_without_misroute(required, expected) -> None:
    _reregister_all()
    selection = REGISTRY.select(required=required)
    if expected is None:
        assert isinstance(selection, CapabilityGap)
    else:
        assert selection.source_type == expected


def test_browser_task_never_misroutes_to_http_adapter() -> None:
    _reregister_all()
    _ = REGISTRY.register  # noqa: B018
    selection = REGISTRY.select(required={"browser", "screenshot"})
    assert isinstance(selection, CapabilityGap)
    assert "browser" in selection.missing