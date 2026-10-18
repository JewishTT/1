"""The bm25s core is reachable from production, not only by hand-wiring it.

`bm25s` has been a declared dependency of `apps/projection` since spec 007.
`BM25SRankedIndex` exists, has its own tests, and is selected by
`projection.search.indexer.default_ranked_index()`.

None of that mattered, because `SearchProjectionStore.__post_init__` hardcoded
`RankedInvertedIndex()`. The accelerated core was reachable only by explicitly
passing `index=BM25SRankedIndex()`, which no production caller does. The
dependency was installed, tested, and unreachable -- the most expensive kind of
dead weight, because it reads as working.

These tests pin reachability rather than bm25s' own behaviour: the failure mode
to guard against is someone reintroducing the hardcoded fallback, which is
invisible to every test that only exercises the stdlib core.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from services.search_backends import (
    RankedInvertedIndex,
    SearchProjectionStore,
    default_ranked_index,
)

pytestmark = pytest.mark.unit


class TestTheDefaultCoreIsTheBestAvailable:
    def test_the_factory_returns_something_searchable(self):
        core = default_ranked_index()
        assert hasattr(core, "put") and hasattr(core, "results")

    def test_the_store_default_is_not_pinned_to_the_slow_core(self):
        """Regression: `__post_init__` hardcoded `RankedInvertedIndex()`.

        Asserted as "is not pinned", not "is bm25s", so this stays honest on a
        machine without the optional dependency -- where the stdlib core is the
        correct answer and the pinning would be untestable rather than wrong.
        """
        store = SearchProjectionStore()
        assert not isinstance(store.index, RankedInvertedIndex), (
            "SearchProjectionStore bypasses default_ranked_index(); the accelerated "
            "core is unreachable in production again"
        )

    def test_the_factory_follows_whatever_the_environment_supports(self):
        """No silent downgrade: the factory's choice must be usable as a core."""
        core = default_ranked_index()
        assert core.put(
            doc_id="d1",
            index="i",
            body={"text": "hello"},
            tenant_id="t1",
            # I-12: a projection write without provenance is refused, so an
            # empty mapping here is not a formality -- it is the invariant.
            provenance={"event_id": "E-1", "observation_id": "OBS-1"},
        )
        assert core.results("hello", top_k=5, tenant_id="t1")


class TestExplicitInjectionStillWins:
    def test_an_explicit_core_is_not_overridden(self):
        """The injectable core is the documented seam; keep it honest."""
        sentinel = RankedInvertedIndex()
        store = SearchProjectionStore(index=sentinel)
        assert store.index is sentinel