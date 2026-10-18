"""A missing measurement must never render as zero (spec 030 FR-100/FR-101, SC-015, T167).

The failure this pins is not a crash. It is a dashboard showing ``0`` for something nobody
measured, which a reader accepts as a measurement. Every test below pairs a refusal with the
honest alternative, so a fix cannot be written that loses the reading instead of correcting it.
"""

from __future__ import annotations

import json

import pytest

from observability.measured import (
    Measured,
    Unmeasured,
    metric_or_none,
    render,
    serialise,
    to_json,
)

pytestmark = pytest.mark.unit


class TestMeasuredCarriesItsSource:
    def test_a_measured_value_names_its_instrument(self):
        m = metric_or_none(0.42, instrument="prometheus/counter")
        assert isinstance(m, Measured)
        assert m.instrument == "prometheus/counter"
        assert m.value == 0.42

    def test_a_measured_value_without_an_instrument_is_refused(self):
        with pytest.raises(ValueError) as e:
            Measured(value=1.0, instrument="  ")
        assert "instrument" in str(e.value)

    def test_a_genuine_zero_is_preserved_as_zero(self):
        """The whole point: a real zero must survive the correction."""
        m = metric_or_none(0, instrument="probe")
        assert isinstance(m, Measured)
        assert m.value == 0.0
        assert render(m) == "0"


class TestMissingBecomesUnmeasured:
    def test_none_is_unmeasured_not_zero(self):
        m = metric_or_none(None, instrument="probe")
        assert isinstance(m, Unmeasured)
        assert m.value if hasattr(m, "value") else None is None

    def test_nan_is_unmeasured_not_zero(self):
        assert isinstance(metric_or_none(float("nan"), instrument="probe"), Unmeasured)

    def test_zero_is_never_converted_to_unmeasured(self):
        """The other direction. Fixing the first bug must not break the real reading."""
        assert isinstance(metric_or_none(0.0, instrument="probe"), Measured)


class TestAnUnmeasuredValueExplainsItself:
    def test_a_reason_is_required(self):
        with pytest.raises(ValueError) as e:
            Unmeasured(reason="  ")
        assert "why" in str(e.value).lower() or "reason" in str(e.value).lower()

    def test_it_names_the_missing_instrumentation(self):
        m = metric_or_none(None, instrument="cost-per-finding")
        assert m.missing_instrumentation == "cost-per-finding"


class TestRendering:
    def test_unmeasured_never_renders_as_a_number(self):
        text = render(metric_or_none(None, instrument="probe"))
        assert text.startswith("unmeasured")
        assert not text.startswith("0")

    def test_unmeasured_never_renders_as_a_bare_zero_with_a_percent(self):
        text = render(metric_or_none(None, instrument="probe"))
        for forbidden in ("0%", "0.0%", "0.0", "n/a%", "-"):
            assert forbidden not in text

    def test_a_measured_value_renders_with_its_unit(self):
        m = Measured(value=12.5, instrument="probe", unit="ms")
        assert render(m) == "12.5 ms"

    def test_the_reason_survives_into_the_render(self):
        assert "no reading produced" in render(metric_or_none(None, instrument="probe"))


class TestSerialisation:
    def test_measured_serialises_to_a_number_with_provenance(self):
        d = serialise(metric_or_none(3, instrument="probe"))
        assert d["value"] == 3.0
        assert d["instrument"] == "probe"

    def test_unmeasured_serialises_to_null_with_a_reason(self):
        d = serialise(metric_or_none(None, instrument="probe"))
        assert d["value"] is None
        assert d["reason"]
        assert d["missing_instrumentation"] == "probe"

    def test_null_survives_a_json_round_trip(self):
        """A JSON encoder must not turn the null back into a number."""
        parsed = json.loads(to_json(metric_or_none(None, instrument="probe")))
        assert parsed["value"] is None

    def test_the_json_is_deterministic(self):
        a = to_json(metric_or_none(1.5, instrument="probe", ))
        b = to_json(metric_or_none(1.5, instrument="probe"))
        assert a == b


class TestTypesAreRefused:
    def test_a_string_is_not_a_metric(self):
        with pytest.raises(TypeError):
            metric_or_none("42", instrument="probe")  # type: ignore[arg-type]

    def test_a_bool_is_not_a_metric(self):
        """True is not 1.0. Accepting it would put a flag into a numeric series."""
        with pytest.raises(TypeError):
            metric_or_none(True, instrument="probe")  # type: ignore[arg-type]


class TestThePairHolds:
    def test_both_states_are_constructible_and_distinguishable(self):
        """CD-7: the honest reading must survive alongside the refusal."""
        measured = metric_or_none(0.0, instrument="probe")
        unmeasured = metric_or_none(None, instrument="probe")
        assert isinstance(measured, Measured)
        assert isinstance(unmeasured, Unmeasured)
        assert render(measured) != render(unmeasured)