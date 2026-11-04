from __future__ import annotations

import pytest

from tools.repo_hygiene import classify_tracked_path


@pytest.mark.parametrize("path", [
    "tmp/debug.py", "tmp.123/output.json", "tmpa16zmg01", "logs/baseline.txt",
    "pytest-of-tim/pytest-1/output.txt", "pip-metadata-abc/METADATA",
    "pip-unpack-abc/package.whl", "probe_r4.py", "scratch_probe.py",
    "apps/webapp/tmp/shots/home.png", "apps/webapp/probeA.mjs",
    "apps/webapp/shot3.mjs",
    "apps/acquisition/artifacts/acquisition-integration/run.json",
    "apps/interpretation/artifacts/acquisition-integration/downstream.json",
    "apps/interpretation/artifacts/interpretation/primproc.json",
])
def test_local_and_generated_outputs_are_rejected(path: str) -> None:
    assert classify_tracked_path(path) is not None


@pytest.mark.parametrize("path", [
    "apps/acquisition/_prove_searxng.py", "apps/webapp/shot.mjs",
    "apps/webapp/scripts/shoot-nav.mjs", "bench/fixtures/extraction/corrupt.bin",
    "benchmarks/er-baseline.json",
    "donors/phishingclub/backend/embedded/signingkeys/public1.bin",
    "docs/platform/index.md",
])
def test_reproducible_source_and_curated_fixtures_are_kept(path: str) -> None:
    assert classify_tracked_path(path) is None
