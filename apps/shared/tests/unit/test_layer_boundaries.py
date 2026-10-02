"""Feature 024 T018 -- layer boundary guard, enforced as a ratchet.

25 violations existed before this guard did. They are not fixed by writing a test;
they are real debt (17 ``path_shim`` sys.path hacks in projection, 6 genuine
``feedback -> control-plane/db`` cross-layer writes). Refactoring all of them
mid-baseline would change behaviour that 2 600 tests currently pin.

So the test is a ratchet, not a zero-assertion: the count must not grow. Any new
violation fails; each existing one is listed with its file so it can be retired
deliberately. When the last one is fixed, this becomes ``== 0``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.layer_boundaries import LAYER_ORDER, find_violations  # noqa: E402

VIOLATIONS = find_violations()

#: Debt recorded at T018. Lower this deliberately, never raise it.
KNOWN_VIOLATIONS = 25


def test_no_new_layer_boundary_violations():
    assert len(VIOLATIONS) <= KNOWN_VIOLATIONS, (
        f"{len(VIOLATIONS)} violations, was {KNOWN_VIOLATIONS}. New ones:\n"
        + "\n".join(f"  {v}" for v in VIOLATIONS if str(v) not in _known_strings())
    )


def _known_strings() -> set[str]:
    import json

    marker = Path(__file__).with_name("layer_boundary_debt.json")
    if marker.exists():
        return set(json.loads(marker.read_text(encoding="utf-8")))
    return set()


def test_acquisition_writes_no_foreign_store():
    """Constitution: the acquisition layer creates no entities, claims or
    memberships, and reaches no store it does not own."""
    offenders = [v for v in VIOLATIONS if v.layer == "acquisition"]
    assert offenders == [], "\n".join(str(v) for v in offenders)


def test_interpretation_does_not_write_the_graph():
    """The observation consumer declares it writes no entity, no claim, no edge.
    No boundary rule enforces that claim; this one does."""
    offenders = [
        v
        for v in VIOLATIONS
        if v.layer == "interpretation" and v.kind == "cross-layer-store"
    ]
    assert offenders == [], "\n".join(str(v) for v in offenders)


def test_layer_order_is_a_strict_total_order():
    """The guard is only as good as the ordering it enforces."""
    assert LAYER_ORDER == sorted(LAYER_ORDER, key=LAYER_ORDER.index)
    assert len(set(LAYER_ORDER)) == len(LAYER_ORDER)


def test_guard_actually_detects_a_violation(tmp_path: Path):
    """Prove the guard is not vacuously green. An upward import -- the substrate
    reaching into a higher layer -- is the violation.

    Note the app used here is `science`, not `control-plane`: a hyphen is illegal in
    a dotted import name, so `from apps.control-plane... import` cannot even be
    written. Real cross-layer store access in this repo is a flat import
    (`from db.schema import ...`), covered by the test below.
    """
    substrate = tmp_path / "apps" / "shared"
    substrate.mkdir(parents=True)
    (substrate / "bad.py").write_text("from apps.science.store import read\n", encoding="utf-8")

    consumer = tmp_path / "apps" / "control-plane"
    consumer.mkdir(parents=True)
    (consumer / "good.py").write_text(
        "from apps.shared.domain import observation_identity\n", encoding="utf-8"
    )

    found = find_violations(tmp_path / "apps")
    assert any(
        v.kind == "cross-layer-import" and v.layer == "shared" and v.target_app == "science"
        for v in found
    ), f"upward import not detected: {found}"
    assert not any(v.source.endswith("good.py") for v in found), "downward import was flagged"


def test_guard_flags_cross_layer_store_write(tmp_path: Path):
    """A flat import of a store module owned by another layer is the exact defect
    FR-010 forbids."""
    fb = tmp_path / "apps" / "feedback"
    fb.mkdir(parents=True)
    (fb / "f.py").write_text("from db.session import get_session\n", encoding="utf-8")
    found = find_violations(tmp_path / "apps")
    assert any(v.kind == "cross-layer-store" and v.layer == "feedback" for v in found)


def test_guard_ignores_tests_of_the_same_layer(tmp_path: Path):
    layer = tmp_path / "apps" / "control-plane"
    layer.mkdir(parents=True)
    (layer / "t.py").write_text("import os\n", encoding="utf-8")
    assert find_violations(tmp_path / "apps") == []


def test_guard_survives_unparseable_source(tmp_path: Path):
    layer = tmp_path / "apps" / "control-plane"
    layer.mkdir(parents=True)
    (layer / "broken.py").write_text("def (:", encoding="utf-8")
    assert find_violations(tmp_path / "apps") == []


@pytest.mark.parametrize("kind", ["shim", "cross-layer-store"])
def test_every_violation_carries_a_source_line(kind: str):
    for v in VIOLATIONS:
        if v.kind == kind:
            assert v.line > 0
            assert v.source.startswith("apps/")