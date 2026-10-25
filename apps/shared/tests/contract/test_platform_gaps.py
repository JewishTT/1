"""The gaps registry is machine-checked: a stale or resolved gap fails the build.

``platform_model/gaps.py`` holds every recorded defect with re-checkable evidence
(a file and a regex). This test re-reads the tree and asserts:

* every open gap is still ``OPEN`` -- its evidence still holds. A gap whose
  evidence has disappeared has been fixed; the registry must be updated, not left
  to republish a defect that no longer exists.
* every resolved claim is still ``GUARDED`` -- the fix is present. A regression
  flips it to ``REGRESSED`` and fails here rather than being rediscovered later.

This is the difference between documentation that *says* something is broken and
documentation that *proves* it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "donors").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("could not locate the repository root above this file")


ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_model import gaps as gap_registry  # noqa: E402


@pytest.fixture(scope="module")
def verified() -> dict:
    return gap_registry.verify(ROOT)


def test_every_open_gap_is_still_open(verified: dict) -> None:
    bad = [g for g in verified["gaps"] if g["status"] != "OPEN"]
    assert not bad, (
        "gaps whose evidence no longer holds; update or remove them:\n  "
        + "\n  ".join(f"{g['id']}: {g['status']} ({g['checks']})" for g in bad)
    )


def test_every_resolved_claim_is_still_guarded(verified: dict) -> None:
    bad = [g for g in verified["resolved"] if g["status"] != "GUARDED"]
    assert not bad, (
        "resolved claims whose fix is no longer present:\n  "
        + "\n  ".join(f"{g['id']}: {g['status']} ({g['checks']})" for g in bad)
    )


def test_gap_ids_are_unique() -> None:
    ids = [g["id"] for g in gap_registry.GAPS] + [g["id"] for g in gap_registry.RESOLVED_CLAIMS]
    assert len(ids) == len(set(ids)), "duplicate gap id"
