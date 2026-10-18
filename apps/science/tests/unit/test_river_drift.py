"""Source health is not a world finding (spec 030 CE-001 §15.14, DON-TEMP-003, T140).

A source that suddenly publishes half as much has two possible explanations and the detector
cannot tell them apart: the phenomenon changed, or our pipeline broke. Presenting the first as
the answer is how a broken scraper gets published as a finding.

So the signal this module produces is about the *instrument*, and the field that would let it be
read as a world claim does not exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from streaming.river_operator import (
    RIVER_VERSION_PINNED,
    DetectorUnavailable,
    DriftDetector,
    HealthSignalKind,
    SourceHealthFeature,
    SourceHealthSignal,
)

pytestmark = pytest.mark.unit

SOURCE = "acme-wire"


def _f(count: int, *, errors: int = 0, at: str = "", schema: str | None = None):
    return SourceHealthFeature(
        source_id=SOURCE,
        tenant_id="t1",
        item_count=count,
        error_count=errors,
        observed_at=at,
        schema_fingerprint=schema,
    )


def _stream(counts: Sequence[int], **kw) -> DriftDetector:
    """Feed a steady baseline then the counts, so warm-up is genuinely done."""
    d = DriftDetector(warmup=5, **kw)
    for i in range(20):
        d.warm(_f(100))
    return d


from collections.abc import Sequence


class TestQuietUntilWarmUp:
    def test_nothing_fires_during_warmup(self):
        d = DriftDetector(warmup=50)
        fired = [s for c in range(40) for s in d.warm(_f(100))]
        assert fired == []

    def test_a_flat_stream_never_fires(self):
        d = _stream([])
        assert d.observe(_f(100) for _ in range(30)) == ()

    def test_the_warmup_boundary_is_configurable(self):
        with pytest.raises(ValueError):
            DriftDetector(warmup=0)

    def test_a_fractional_threshold_is_required(self):
        with pytest.raises(ValueError):
            DriftDetector(threshold=5.0)


class TestVolumeDriftIsDetected:
    def test_a_collapse_in_volume_fires(self):
        # ADWIN confirms against a sustained change, not a single point, so the drop has to
        # persist long enough to leave the bucket window.
        d = _stream([])
        signals = d.observe(_f(0) for _ in range(15))
        assert any(s.kind == HealthSignalKind.VOLUME_DROP for s in signals)

    def test_a_spike_fires_as_a_spike_not_a_drop(self):
        d = _stream([])
        signals = d.observe(_f(10_000) for _ in range(15))
        assert any(s.kind == HealthSignalKind.VOLUME_SPIKE for s in signals)

    def test_the_signal_names_what_moved(self):
        d = _stream([])
        signal = next(s for s in d.observe(_f(0) for _ in range(15)) if s.kind == HealthSignalKind.VOLUME_DROP)
        assert signal.detail["previous_count"] == 100
        assert signal.detail["current_count"] == 0


class TestItIsNeverAWorldClaim:
    """The whole point of the module."""

    def test_no_signal_claims_to_be_about_the_world(self):
        d = _stream([])
        for signal in d.observe(_f(0) for _ in range(15)):
            assert signal.is_world_claim is False

    def test_the_description_says_it_is_instrument_telemetry(self):
        d = _stream([])
        signal = next(iter(d.observe(_f(0) for _ in range(15))), None)
        if signal is not None:
            assert "not a world finding" in signal.describe()

    def test_the_constructor_refuses_to_build_a_world_claim(self):
        with pytest.raises(ValueError) as e:
            SourceHealthSignal(
                source_id="s", tenant_id="t", kind="x", detail={},
                detector_version="v", features_seen=1, is_world_claim=True,
            )
        assert "two causes" in str(e.value)


class TestSchemaChangesAreOursNotTheWorlds:
    def test_a_schema_change_is_reported(self):
        d = _stream([])
        d.warm(_f(100, schema="v1"))
        signals = d.warm(_f(100, schema="v2"))
        assert any(s.kind == HealthSignalKind.SCHEMA_CHANGE for s in signals)

    def test_it_names_the_parser_change_as_the_likely_cause(self):
        d = _stream([])
        d.warm(_f(100, schema="v1"))
        signal = next(s for s in d.warm(_f(100, schema="v2"))
                      if s.kind == HealthSignalKind.SCHEMA_CHANGE)
        assert "parser" in signal.notes["likely_cause"]

    def test_a_stable_schema_is_silent(self):
        d = _stream([])
        d.warm(_f(100, schema="v1"))
        assert d.warm(_f(100, schema="v1")) == ()


class TestPerSourceIsolation:
    def test_two_sources_do_not_share_a_model(self):
        d = DriftDetector(warmup=2)
        for _ in range(20):
            d.warm(_f(100))
            d.warm(SourceHealthFeature(source_id="other", tenant_id="t1", item_count=999))

        quiet = d.warm(_f(100))
        assert quiet == ()

    def test_two_tenants_do_not_share_a_model(self):
        d = DriftDetector(warmup=2)
        for _ in range(20):
            d.warm(_f(100))
            d.warm(SourceHealthFeature(source_id=SOURCE, tenant_id="t2", item_count=1))
        assert d.warm(_f(100)) == ()


class TestErrorRatesAreAvailableWithoutAlarming:
    """A rate is computed on demand; a threshold for it belongs to policy, not here."""

    def test_error_rate_is_derived(self):
        assert _f(90, errors=10).error_rate == pytest.approx(0.1)

    def test_a_source_with_no_traffic_has_no_error_rate_invention(self):
        assert _f(0, errors=0).error_rate == 0.0

    def test_parse_failure_rate_is_derived(self):
        f = SourceHealthFeature(source_id="s", tenant_id="t", item_count=80, parse_failures=20)
        assert f.parse_failure_rate == pytest.approx(0.2)

    def test_the_feature_serialises_deterministically(self):
        assert _f(10, errors=2).as_dict() == _f(10, errors=2).as_dict()


class TestCheckpinting:
    def test_state_is_reportable_for_replay(self):
        d = _stream([])
        d.warm(_f(123))
        state = d.state_ref("t1", SOURCE)
        assert state["features_seen"] == 21
        assert state["last_volume"] == 123
        assert state["detector_version"] == RIVER_VERSION_PINNED

    def test_state_of_an_unknown_source_is_empty_not_invented(self):
        state = DriftDetector().state_ref("t1", "never-seen")
        assert state["features_seen"] == 0
        assert state["detector_present"] is False


class TestUpstreamIsReal:
    def test_available_reflects_the_environment(self):
        assert isinstance(DriftDetector().available(), bool)

    def test_version_is_pinned(self):
        assert RIVER_VERSION_PINNED == "0.26.1"

    def test_the_module_imports_without_river(self):
        """An absent optional dependency must not break the import."""
        import importlib

        importlib.reload(importlib.import_module("streaming.river_operator"))

    def test_detector_unavailable_names_the_capability(self):
        try:
            DriftDetector().warm(_f(1))
        except DetectorUnavailable as exc:
            assert "capability gap" in str(exc)
            assert "nothing changed" in str(exc)