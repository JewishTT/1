"""Hermetic test bootstrap (spec 007).

The mini datasets live under ``dictionaries/data/`` which is gitignored, so
any fresh checkout must build them before the suite runs. This session fixture
builds them once (offline, pure-Python, deterministic) if any versioned meta
sidecar is missing. Build is cheap (<200ms) and idempotent, so tests stay
hermetic without committing generated artifacts (NFR-1, FR-10, C-7, FR-8).
"""

from __future__ import annotations

import pytest

from dictionaries.build_mini import DATA_DIR, VERSIONS, build_all


@pytest.fixture(scope="session", autouse=True)
def _ensure_datasets() -> None:
    required = [
        DATA_DIR / f"{kind}_{version}.meta.json"
        for kind, version in VERSIONS.items()
    ]
    if any(not path.exists() for path in required):
        build_all(out_dir=DATA_DIR)
    for path in required:
        assert path.exists(), f"dataset sidecar missing: {path.name}"