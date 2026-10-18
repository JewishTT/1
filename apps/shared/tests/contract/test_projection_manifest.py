"""ProjectionManifest contract tests (spec 030 contract 06, FR-070/FR-071, task T146–T149).

The claim under test is that a projection is rebuildable and therefore safe to destroy. That
claim is worth nothing unless something refuses to record it when it is false, so most of these
are refusal tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from contracts.projection_manifest import (
    BuilderRef,
    ProjectionDeclarationError,
    ProjectionKind,
    ProjectionManifest,
    ProjectionStatus,
    Staleness,
)

pytestmark = pytest.mark.contract

BUILDER = BuilderRef(id="gudhi-persistence", version="3.10.1")


def _manifest(**kw) -> ProjectionManifest:
    base = dict(
        projection_id="proj-1",
        projection_kind=ProjectionKind.TDA,
        tenant_id="t-acme",
        source_event_offset={"topic": "entity.stream", "partition": 3, "offset": 1200},
        input_snapshot_digest="sha256:abc",
        builder=BUILDER,
        parameters={"complex": "flag", "filtration": "distance", "scale_units": "metres"},
        output_digest="sha256:def",
    )
    base.update(kw)
    return ProjectionManifest.declare(**base)


class TestTheHappyPath:
    def test_a_complete_manifest_declares_rebuildable(self):
        assert _manifest(rebuildable=True).rebuildable is True

    def test_the_preconditions_are_visible_not_implied(self):
        assert _manifest().can_rebuild() is True

    def test_fingerprint_is_stable_across_two_identical_builds(self):
        a, b = _manifest(), _manifest()
        assert a.fingerprint() == b.fingerprint()

    def test_parameters_fingerprint_is_derived_not_stored(self):
        """A stored value that disagrees with the parameters is worse than none."""
        assert _manifest().parameters_fingerprint.startswith("sha256:")
        assert _manifest().parameters_fingerprint == _manifest().parameters_fingerprint

    def test_fingerprint_changes_when_the_parameters_change(self):
        a = _manifest()
        b = _manifest(parameters={"complex": "clique", "filtration": "distance"})
        assert a.fingerprint() != b.fingerprint()

    def test_fingerprint_changes_when_the_snapshot_changes(self):
        a = _manifest()
        b = _manifest(input_snapshot_digest="sha256:xyz")
        assert a.fingerprint() != b.fingerprint()

    def test_as_dict_carries_the_derived_fields(self):
        d = _manifest().as_dict()
        assert d["parameters_fingerprint"].startswith("sha256:")
        assert d["fingerprint"].startswith("sha256:")
        assert d["projection_kind"] == "tda"


class TestRebuildableIsRefusedWhenUnfounded:
    def test_no_snapshot_digest(self):
        with pytest.raises(ProjectionDeclarationError) as e:
            _manifest(rebuildable=True, input_snapshot_digest="")
        assert "input_snapshot_digest" in str(e.value)

    def test_no_checkpoint_route(self):
        with pytest.raises(ProjectionDeclarationError) as e:
            _manifest(rebuildable=True, source_event_offset={})
        assert "source_event_offset" in str(e.value)

    def test_a_builder_without_a_version_cannot_be_named(self):
        with pytest.raises(ProjectionDeclarationError):
            BuilderRef(id="something", version="  ")

    def test_the_refusal_names_what_is_missing(self):
        """A refusal nobody can act on is an outage with no trace."""
        with pytest.raises(ProjectionDeclarationError) as e:
            _manifest(rebuildable=True, input_snapshot_digest="", source_event_offset={})
        msg = str(e.value)
        assert "input_snapshot_digest" in msg and "source_event_offset" in msg

    def test_a_manifest_with_no_preconditions_is_not_rebuildable_even_if_asked(self):
        m = _manifest(rebuildable=False)
        assert m.can_rebuild() is True  # the fields happen to be present
        assert m.rebuildable is False  # but nobody claimed it


class TestTheManifestCannotLieAboutOutput:
    def test_a_succeeded_build_needs_an_output_digest(self):
        with pytest.raises(ProjectionDeclarationError) as e:
            _manifest(output_digest="")
        assert "output digest" in str(e.value)

    def test_a_partial_build_also_needs_one(self):
        with pytest.raises(ProjectionDeclarationError):
            _manifest(output_digest="", status=ProjectionStatus.PARTIAL)

    def test_a_failed_build_needs_no_digest(self):
        """Nothing was produced, and saying so is the honest record."""
        m = _manifest(output_digest="", status=ProjectionStatus.FAILED)
        assert m.output_digest == ""
        assert m.is_degraded() is True


class TestTenancy:
    def test_a_projection_without_a_tenant_is_refused(self):
        with pytest.raises(ProjectionDeclarationError) as e:
            _manifest(tenant_id="  ")
        assert "tenant" in str(e.value)


class TestFreshnessIsAQuestionNotADefault:
    """FR-079: a stale projection satisfies a freshness-requiring obligation only by policy."""

    def test_a_current_build_satisfies_a_tight_window(self):
        m = _manifest(staleness=Staleness(status="current", lag_events=0))
        assert m.satisfies_freshness(max_lag_events=5) is True

    def test_a_lagging_build_fails_a_tight_window(self):
        m = _manifest(staleness=Staleness(status="current", lag_events=40))
        assert m.satisfies_freshness(max_lag_events=5) is False
        assert m.satisfies_freshness(max_lag_events=100) is True

    def test_a_failed_build_never_satisfies_freshness_however_loose(self):
        m = _manifest(status=ProjectionStatus.FAILED, output_digest="")
        assert m.satisfies_freshness(max_lag_events=10_000) is False

    def test_an_explicitly_stale_build_fails_even_at_lag_zero(self):
        m = _manifest(staleness=Staleness(status="stale", lag_events=0))
        assert m.satisfies_freshness(max_lag_events=10_000) is False

    def test_unknown_lag_is_treated_as_current_not_as_zero_lag(self):
        m = _manifest(staleness=Staleness(status="current", lag_events=None))
        assert m.satisfies_freshness(max_lag_events=0) is True


class TestDegradationIsVisible:
    def test_partial_is_degraded(self):
        assert _manifest(status=ProjectionStatus.PARTIAL).is_degraded() is True

    def test_stale_is_not_degraded_but_is_not_current(self):
        m = _manifest(staleness=Staleness(status="stale"))
        assert m.is_degraded() is False
        assert m.staleness.is_current is False

    def test_staleness_carries_when_it_began(self):
        since = datetime.now(UTC) - timedelta(hours=3)
        m = _manifest(staleness=Staleness(status="stale", lag_events=9, stale_since=since))
        assert m.staleness.stale_since == since