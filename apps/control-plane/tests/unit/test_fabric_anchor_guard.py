"""Unanchored science findings must not become research obligations (spec 030 FR-066, T139).

``fabric_bridge.to_signal`` is the one place a ``Finding`` stops being a scientific note and
becomes a ``ResearchObligation`` -- the object the investigation treats as knowledge it still
owes. Before this, a finding carrying ``refs=()`` crossed that boundary unchallenged and
produced an obligation that no observation, no snapshot and no operator could ever satisfy,
while reading like a grounded demand.

These pin that the boundary refuses, and that it refuses loudly enough to be noticed.
"""

from __future__ import annotations

import pytest
from context.fabric import Finding, FindingKind

from context_engine.fabric_bridge import UnanchoredFinding, to_signal

pytestmark = pytest.mark.unit


def _finding(**kw):
    base = {
        "kind": FindingKind.COVERAGE_GAP,
        "question": "Which suppliers served region X in 2020?",
        "rationale": "no observation covers the region",
        "refs": ("obs-1", "obs-2"),
        "rule_id": "coverage/3",
    }
    base.update(kw)
    return Finding(**base)


class TestAnchoredFindingsPass:
    def test_a_ref_anchored_finding_becomes_a_signal(self):
        signal = to_signal(_finding())
        assert signal.evidence_refs == ("obs-1", "obs-2")

    def test_a_single_ref_is_enough(self):
        signal = to_signal(_finding(refs=("obs-1",)))
        assert signal.evidence_refs == ("obs-1",)

    def test_the_rule_id_travels_into_the_rationale(self):
        assert "rule=coverage/3" in to_signal(_finding()).rationale


class TestUnanchoredFindingsAreRefused:
    def test_no_refs_is_refused(self):
        with pytest.raises(UnanchoredFinding) as e:
            to_signal(_finding(refs=()))
        assert "cannot become a research obligation" in str(e.value)
        assert "FR-066" in str(e.value)

    def test_the_refusal_names_the_finding(self):
        """A refusal nobody can locate is an outage with no trace."""
        with pytest.raises(UnanchoredFinding) as e:
            to_signal(_finding(refs=(), rule_id="coverage/9", question="Q" * 3))
        msg = str(e.value)
        assert "coverage/9" in msg
        assert "QQQ" in msg

    def test_every_kind_is_guarded_not_just_one(self):
        """The anchor rule is not per-kind; a low-priority trivia finding must not slip."""
        for kind in FindingKind:
            with pytest.raises(UnanchoredFinding):
                to_signal(_finding(kind=kind, refs=()))


class TestAnUnmappedKindStillRaisesKeyError:
    """The pre-existing mapping guard must not be shadowed by the new one."""

    def test_anchor_is_checked_after_the_mapping(self):
        # An unmapped kind must still surface as KeyError, not as UnanchoredFinding,
        # otherwise the two failure modes become indistinguishable in a log.
        from context_engine import fabric_bridge

        original = dict(fabric_bridge._TRIGGER_BY_KIND)
        try:
            fabric_bridge._TRIGGER_BY_KIND.pop(FindingKind.COVERAGE_GAP, None)
            with pytest.raises(KeyError):
                to_signal(_finding(refs=("obs-1",)))
        finally:
            fabric_bridge._TRIGGER_BY_KIND.clear()
            fabric_bridge._TRIGGER_BY_KIND.update(original)