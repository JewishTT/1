"""Shared fixtures for the spec-ops test suite (Feature 027 + 031).

One fixture here that both GhostLine test modules would otherwise each write: the
process-wide configuration cache and the two process-wide registries beside it.

``specops.ghostline.config.get_config`` is ``lru_cache``d because the runtime status
endpoint polls it and re-reading a dozen environment variables per request is waste.
That optimisation is exactly what makes ``monkeypatch.setenv`` inert in a test — the
first test to call it pins the values, and every later test that sets an environment
variable is silently ignored. The failure mode is nasty because it is order-dependent:
the suite passes in one order and writes test fixtures into the real ``logs/``
directory in another.

The ordering inside the fixture is load-bearing and was wrong twice already. The cache
has to be cleared *after* everything else in setup: ``runtime().stop()`` reads
``get_config()`` to build the state it returns, so clearing first lets the fixture
prime the cache itself, and every ``monkeypatch.setenv`` in a test body is then
ignored — silently, and only in the tests that bother to set one.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_ghostline_state(tmp_path, monkeypatch):
    """Give every test a private ledger, a private config and a stopped runtime.

    Three pieces of global state, one fixture, because leaking any of them produces a
    test that passes in one order and fails in another — or worse, one that silently
    writes into the operator's real ``logs/ghostline/``.

    * ``GHOSTLINE_LEDGER_DIR`` — the call ledger and the voice registry both live under
      it, so pointing it at ``tmp_path`` makes the suite hermetic.
    * ``clear_config_cache`` — the LAST statement in setup, not the first. Anything the
      fixture itself calls (``runtime().stop()`` reads the config to build its state)
      would otherwise prime the cache and make every ``monkeypatch.setenv`` in the test
      body inert.
    * ``runtime().stop()`` — the runtime controller is a deliberate singleton, so a test
      that leaves it ``blocked`` would leak that into every later test.
    """
    from specops.ghostline.config import clear_config_cache
    from specops.ghostline.runtime import runtime

    monkeypatch.setenv("GHOSTLINE_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("GHOSTLINE_SAMPLES_ROOT", str(tmp_path / "samples"))
    runtime().stop()
    clear_config_cache()
    yield
    runtime().stop()
    clear_config_cache()
