"""Contract: the operator registry (spec 025 §30, Phase J).

The registry is what makes a discipline *selectable* rather than merely
importable. Its behaviour is copied from ``acquisition/adapters/registry.py`` on
purpose -- validate on register, select by capability intersection, return an
explicit gap rather than substituting something close enough -- with one
addition the acquisition registry never needed: tier discipline, because §31
binds the deterministic core to Tier 0.

These tests pin the failure modes separately. Collapsing them is the failure this
file exists to prevent: a caller told "no operator provides X" when in fact X
exists but no single operator combines X and Y will go looking for X forever.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.operators.base import (
    ComplexityModel,
    ContractRef,
    Determinism,
    ExplanationTrace,
    MemoryClass,
    NumericMode,
    OperatorClass,
    OperatorRegistration,
    OperatorResult,
    Tier,
    ValidationResult,
    describe,
    known_classes,
)
from context.operators.registry import (
    GapReason,
    OperatorNotFoundError,
    OperatorRegistrationError,
    _Registry,
    reset,
)

pytestmark = pytest.mark.contract


class FakeOperator:
    def __init__(
        self,
        operator_id: str,
        operator_class: OperatorClass = OperatorClass.NORMALIZATION,
        *,
        determinism: Determinism = Determinism.EXACT,
        version: str = "1.0",
    ) -> None:
        self.id = operator_id
        self.version = version
        self.operator_class = operator_class
        self.input_contract = ContractRef("cell")
        self.output_contract = ContractRef("verdict")
        self.determinism = determinism
        self.numeric_mode = NumericMode.EXACT
        self.complexity = ComplexityModel(memory=MemoryClass.LINEAR)

    def validate_input(self, input_view: Any) -> ValidationResult:
        return ValidationResult.accept()

    def run(self, input_view: Any, parameters: Any, seed: int) -> OperatorResult:
        return OperatorResult(self.id, self.version, self.determinism, {"ok": True})

    def explain(self, result: OperatorResult) -> ExplanationTrace:
        return ExplanationTrace(self.id, "fake")


def _registry() -> _Registry:
    registry = _Registry()
    registry.register(
        OperatorRegistration(
            FakeOperator("tda", OperatorClass.TDA),
            frozenset({"persistence", "clustering"}),
        )
    )
    registry.register(
        OperatorRegistration(
            FakeOperator("causal", OperatorClass.CAUSAL, determinism=Determinism.FLOAT_QUANTIZED),
            frozenset({"causal", "attribution"}),
            tier=Tier.STATISTICAL,
        )
    )
    registry.register(
        OperatorRegistration(
            FakeOperator("synth", OperatorClass.NORMALIZATION,
                         determinism=Determinism.NON_DETERMINISTIC),
            frozenset({"nlp", "semantic"}),
            tier=Tier.ADAPTIVE,
            nondeterminism_reason="model sampling",
        )
    )
    return registry


class TestCatalog:
    def test_there_are_exactly_twentyone_classes(self) -> None:
        assert len(known_classes()) == 21

    def test_the_v2_addition_is_present(self) -> None:
        assert OperatorClass.INDEPENDENCE.value == "independence"

    def test_determinism_classes_match_section_4_1(self) -> None:
        assert {d.value for d in Determinism} == {
            "exact",
            "fixed_point",
            "float_quantized",
            "non_deterministic",
        }


class TestRegistration:
    def test_registers_and_indexes(self) -> None:
        registry = _registry()
        assert len(registry) == 3
        assert "tda@1.0" in tuple(registry.keys())
        assert registry.capabilities() >= {"persistence", "causal", "nlp"}
        assert OperatorClass.TDA in registry.classes()

    def test_identical_reregistration_is_idempotent(self) -> None:
        registry = _registry()
        before = len(registry)
        registry.register(
            OperatorRegistration(
                FakeOperator("tda", OperatorClass.TDA), frozenset({"persistence", "clustering"})
            )
        )
        assert len(registry) == before

    def test_conflicting_reregistration_is_refused(self) -> None:
        registry = _registry()
        with pytest.raises(OperatorRegistrationError):
            registry.register(
                OperatorRegistration(
                    FakeOperator("tda", OperatorClass.TDA), frozenset({"something-else"})
                )
            )

    def test_non_deterministic_without_a_reason_is_refused(self) -> None:
        with pytest.raises(OperatorRegistrationError) as excinfo:
            _Registry().register(
                OperatorRegistration(
                    FakeOperator("ghost", determinism=Determinism.NON_DETERMINISTIC),
                    frozenset({"x"}),
                )
            )
        assert "§4.1" in str(excinfo.value)

    def test_unknown_operator_class_is_refused(self) -> None:
        operator = FakeOperator("bad")
        operator.operator_class = "not_a_class"
        with pytest.raises(OperatorRegistrationError):
            _Registry().register(OperatorRegistration(operator, frozenset({"x"})))

    def test_incomplete_operator_is_refused(self) -> None:
        class Incomplete:
            id = "incomplete"
            version = "1.0"
            operator_class = OperatorClass.ANOMALY
            input_contract = ContractRef("a")
            output_contract = ContractRef("b")
            determinism = Determinism.EXACT
            numeric_mode = NumericMode.EXACT
            complexity = ComplexityModel()

        with pytest.raises(OperatorRegistrationError) as excinfo:
            _Registry().register(OperatorRegistration(Incomplete(), frozenset({"x"})))
        assert "validate_input" in str(excinfo.value)


class TestSelection:
    def test_selects_by_capability(self) -> None:
        selection = _registry().select(required=frozenset({"persistence"}))
        assert selection.ok
        assert selection.registration.key == "tda@1.0"

    def test_selection_is_deterministic(self) -> None:
        registry = _registry()
        picks = {registry.select(required=frozenset({"attribution"})).registration.key for _ in range(5)}
        assert len(picks) == 1

    def test_unwrap_raises_on_a_gap(self) -> None:
        with pytest.raises(OperatorNotFoundError):
            _registry().select(required=frozenset({"time-travel"})).unwrap()

    def test_select_all_returns_key_ordered(self) -> None:
        registry = _registry()
        found = registry.select_all(max_tier=Tier.STATISTICAL)
        assert [item.key for item in found] == sorted(item.key for item in found)
        assert len(found) == 2


class TestGapIsHonest:
    def test_nothing_provides_a_capability(self) -> None:
        gap = _registry().select(required=frozenset({"persistence", "time-travel"})).gap
        assert gap.reason is GapReason.NO_PROVIDER
        assert gap.uncovered == frozenset({"time-travel"})

    def test_no_single_operator_covers_the_combination(self) -> None:
        """Both capabilities exist; no one operator holds both. Not a missing provider."""
        gap = _registry().select(required=frozenset({"persistence", "causal"})).gap
        assert gap.reason is GapReason.NO_SINGLE_PROVIDER
        assert gap.uncovered == frozenset()
        assert gap.missing == frozenset({"persistence", "causal"})

    def test_everything_excluded_by_tier(self) -> None:
        selection = _registry().select(required=frozenset({"nlp"}), max_tier=Tier.DETERMINISTIC)
        gap = selection.gap
        assert gap.reason is GapReason.EXCLUDED
        assert gap.uncovered == frozenset()
        assert gap.excluded and gap.excluded[0][0] == "synth@1.0"

    def test_tier_ceiling_admits_the_same_operator_when_raised(self) -> None:
        registry = _registry()
        assert registry.select(required=frozenset({"nlp"}), max_tier=Tier.ADAPTIVE).ok

    def test_a_gap_is_never_ok(self) -> None:
        """Consistency: ok=False must never coexist with nothing missing and no cause."""
        gap = _registry().select(required=frozenset({"nlp"}), max_tier=Tier.DETERMINISTIC).gap
        assert gap.ok is False
        assert gap.reason is not None

    def test_gap_serialises_with_its_reason(self) -> None:
        payload = _registry().select(required=frozenset({"time-travel"})).gap.as_dict()
        assert payload["reason"] == "no_provider"
        assert payload["uncovered"] == ["time-travel"]


class TestLookup:
    def test_get_by_id_only(self) -> None:
        assert _registry().get("tda").key == "tda@1.0"

    def test_get_unknown_raises(self) -> None:
        with pytest.raises(OperatorNotFoundError):
            _registry().get("nonexistent")

    def test_has_reports_without_raising(self) -> None:
        registry = _registry()
        assert registry.has("tda") is True
        assert registry.has("nonexistent") is False

    def test_ambiguous_version_must_be_named(self) -> None:
        registry = _Registry()
        registry.register(
            OperatorRegistration(
                FakeOperator("dup", version="1.0"), frozenset({"a"})
            )
        )
        registry.register(
            OperatorRegistration(
                FakeOperator("dup", version="2.0"), frozenset({"b"})
            )
        )
        with pytest.raises(OperatorNotFoundError) as excinfo:
            registry.get("dup")
        assert "ambiguous" in str(excinfo.value)
        assert registry.get("dup", "2.0").key == "dup@2.0"


class TestMetadata:
    def test_describe_exposes_the_section_30_2_block(self) -> None:
        payload = describe(_registry().get("tda"))
        for field in (
            "id",
            "version",
            "operator_class",
            "input_contract",
            "output_contract",
            "tier",
            "determinism_mode",
            "numeric_mode",
            "complexity_class",
            "memory_class",
            "capabilities",
        ):
            assert field in payload
        assert payload["determinism_mode"] == "exact"

    def test_registry_module_singleton_can_be_reset(self) -> None:
        first = reset()
        assert len(first) == 0
        second = reset()
        assert second is not first


class TestDeterministicCoreDiscipline:
    def test_tier_three_operator_declares_its_reason(self) -> None:
        registration = _registry().get("synth")
        assert registration.tier is Tier.ADAPTIVE
        assert registration.nondeterminism_reason

    def test_low_tier_operators_satisfy_the_core_without_a_reason(self) -> None:
        assert _registry().get("tda").satisfies_deterministic_core()
