"""Splink proposes; it does not decide (spec 030 CE-001 §15.5, DON-ER-003, T105).

These pin the adapter's whole reason for existing. A linkage backend that can commit a merge is
not a better matcher, it is a second way to be wrong — which is the finding from the 029 audit
about the existing matcher, where a threshold whose own profile declared itself uncalibrated was
able to decide.

Run with splink absent too: the adapter must report a capability gap rather than pretending the
data contains no matches.
"""

from __future__ import annotations

import pytest

from resolution.splink_adapter import (
    SPLINK_VERSION_PINNED,
    ComparisonVectorEntry,
    ScoreSemantics,
    SplinkAdapter,
    SplinkResult,
)

pytestmark = pytest.mark.unit


def _vec(field: str = "name", level: str = "exact", l="a", r="a"):
    return ComparisonVectorEntry(field=field, comparison_level=level, value_l=l, value_r=r)


def _pinned_splink_version() -> str:
    """The splink version the admission workspace pins, read from the manifest."""
    import tomllib
    from pathlib import Path

    manifest = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    for spec in data["project"]["dependencies"]:
        if spec.startswith("splink"):
            return spec.split("==", 1)[1].strip()
    raise AssertionError("the admission workspace does not pin splink")


def _cand(adapter: SplinkAdapter, *, l="1", r="2", score=0.9, semantics=ScoreSemantics.MATCH_PROBABILITY):
    return adapter.to_candidate(
        left_id=l,
        right_id=r,
        score=score,
        score_semantics=semantics,
        comparison_vector=(_vec(),),
        model_fingerprint="m-1",
    )


class TestItProposesAndNeverDecides:
    def test_a_candidate_always_requires_a_decision(self):
        assert _cand(SplinkAdapter()).requires_human_or_policy_decision() is True

    def test_it_lands_in_the_candidate_store_as_open(self):
        from resolution.candidate import CandidateState

        assert _cand(SplinkAdapter()).to_candidate().state is CandidateState.OPEN

    def test_a_high_score_does_not_change_that(self):
        from resolution.candidate import CandidateState

        hot = _cand(SplinkAdapter(), score=0.999)
        assert hot.to_candidate().state is CandidateState.OPEN

    def test_the_reviewer_sees_why_it_was_proposed(self):
        reasons = _cand(SplinkAdapter()).to_candidate().reasons
        assert any("score=0.9" in r for r in reasons)
        assert any("name:exact" in r for r in reasons)


class TestTheScoreCarriesItsMeaning:
    def test_a_calibrated_probability_is_labelled_as_one(self):
        c = _cand(SplinkAdapter(), semantics=ScoreSemantics.MATCH_PROBABILITY)
        assert c.score_semantics is ScoreSemantics.MATCH_PROBABILITY

    def test_an_uncalibrated_weight_is_not_a_probability(self):
        """A match weight and a probability are different claims about the same number."""
        c = _cand(SplinkAdapter(), semantics=ScoreSemantics.UNCALIBRATED_WEIGHT)
        assert c.score_semantics is ScoreSemantics.UNCALIBRATED_WEIGHT
        assert c.score_semantics is not ScoreSemantics.MATCH_PROBABILITY

    def test_a_blocking_only_pair_has_no_weight(self):
        c = _cand(SplinkAdapter(), score=None, semantics=ScoreSemantics.BLOCKING_ONLY)
        assert c.decision_weight == 0.0
        assert c.score is None

    def test_an_uncalibrated_run_is_not_comparable_to_another(self):
        r = SplinkResult(
            candidates=(), model_fingerprint="m", calibrated=False
        )
        assert r.is_comparable_to_another_run is False

    def test_a_calibrated_run_is(self):
        assert SplinkResult(candidates=(), model_fingerprint="m", calibrated=True).is_comparable_to_another_run


class TestTheModelIsNamed:
    """A score without a model is a number with no provenance."""

    def test_the_model_fingerprint_travels_on_every_candidate(self):
        assert _cand(SplinkAdapter()).model_fingerprint == "m-1"

    def test_the_version_travels_on_every_candidate(self):
        assert _cand(SplinkAdapter()).splink_version == SPLINK_VERSION_PINNED

    def test_two_models_produce_distinguishable_candidates(self):
        a = SplinkAdapter().to_candidate(
            left_id="1", right_id="2", score=0.9,
            score_semantics=ScoreSemantics.MATCH_PROBABILITY,
            comparison_vector=(), model_fingerprint="m-A",
        )
        b = SplinkAdapter().to_candidate(
            left_id="1", right_id="2", score=0.9,
            score_semantics=ScoreSemantics.MATCH_PROBABILITY,
            comparison_vector=(), model_fingerprint="m-B",
        )
        assert a.model_fingerprint != b.model_fingerprint


class TestPairIdentity:
    def test_pair_key_is_order_independent(self):
        a = SplinkAdapter().pair_key("x", "y")
        b = SplinkAdapter().pair_key("y", "x")
        assert a == b

    def test_the_candidate_carries_the_order_independent_key(self):
        fwd = SplinkAdapter().to_candidate(
            left_id="x", right_id="y", score=1.0,
            score_semantics=ScoreSemantics.MATCH_PROBABILITY,
            comparison_vector=(), model_fingerprint="m",
        )
        rev = SplinkAdapter().to_candidate(
            left_id="y", right_id="x", score=1.0,
            score_semantics=ScoreSemantics.MATCH_PROBABILITY,
            comparison_vector=(), model_fingerprint="m",
        )
        assert fwd.pair_key == rev.pair_key

    def test_different_pairs_stay_different(self):
        assert SplinkAdapter().pair_key("a", "b") != SplinkAdapter().pair_key("a", "c")


class TestReviewOrdering:
    def test_candidates_are_ordered_by_descending_score(self):
        adapter = SplinkAdapter()
        result = adapter.to_result(
            (_cand(adapter, l="1", r="2", score=0.2),
             _cand(adapter, l="3", r="4", score=0.95),
             _cand(adapter, l="5", r="6", score=0.6)),
            model_fingerprint="m",
        )
        assert [c.decision_weight for c in result.candidates] == [0.95, 0.6, 0.2]

    def test_ties_break_deterministically(self):
        adapter = SplinkAdapter()
        one = adapter.to_result(
            (_cand(adapter, l="9", r="8", score=0.5), _cand(adapter, l="1", r="2", score=0.5)),
            model_fingerprint="m",
        )
        two = adapter.to_result(
            (_cand(adapter, l="1", r="2", score=0.5), _cand(adapter, l="9", r="8", score=0.5)),
            model_fingerprint="m",
        )
        assert [c.pair_key for c in one.candidates] == [c.pair_key for c in two.candidates]


class TestUpstreamIsReal:
    """If splink is not installed the adapter must say so, not find nothing."""

    def test_available_reflects_the_environment(self):
        adapter = SplinkAdapter()
        assert isinstance(adapter.available(), bool)

    def test_version_is_the_pinned_one_when_installed(self):
        adapter = SplinkAdapter()
        if not adapter.available():
            pytest.skip("splink not installed")
        from importlib.metadata import version as installed_version

        reported = adapter.version()
        actually_installed = installed_version("splink")
        # The adapter must report what it actually imported. If it ever falls back to its
        # own constant, this fails and that fallback is a bug: it would pin a provenance
        # record to a version nobody is running.
        assert reported == actually_installed, (
            f"adapter reports {reported} but splink {actually_installed} is installed"
        )
        # The pin lives in the manifest, so the expectation cannot rot: a pin that moves
        # to 6 makes this test demand 6, and a pin that is not installed at all makes it
        # fail here rather than in a run nobody read.
        pinned = _pinned_splink_version()
        assert actually_installed == pinned, (
            f"splink {actually_installed} is installed but the workspace pins {pinned}"
        )
        assert reported == pinned, f"adapter reports {reported}, the workspace pins {pinned}"
        major = int(reported.split(".")[0])
        assert major == int(pinned.split(".")[0]), f"unsupported splink major {reported}"

    def test_the_adapter_imports_without_splink_present(self):
        """Import must not explode on a machine that lacks the optional backend."""
        import importlib

        importlib.reload(importlib.import_module("resolution.splink_adapter"))