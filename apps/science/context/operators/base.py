"""The reasoning-operator contract (spec 025 §30.1–§30.3, §31).

Why this exists: the platform already contained fourteen discipline packages
(``scitda``, ``causal``, ``structure``, ``temporal``, ``robustness``,
``claims/calibration``, ``hypotheses/gain``, ``operators/phase`` …), all tested,
and none reachable from the context engine. They were reachable only as eight
synchronous HTTP handlers. An operator contract is what turns "a function someone
imported" into "a capability the planner can select", which is the difference
between a library and an engine.

Three properties are load-bearing, and each one closes a specific way the
existing code was unsafe to compose:

1. **``determinism`` is declared, not assumed.** Spec §4.1: byte-identity is
   unachievable for float-backed artifacts, so every operator declares which of
   ``EXACT`` / ``FIXED_POINT`` / ``FLOAT_QUANTIZED`` it answers to, and replay
   compares at that class. An operator that cannot state its class does not
   register.
2. **``tier`` is declared, and Tier 3 is optional.** §31 is binding: "Tier 3 must
   never be required for correctness of the deterministic core." That is enforced
   here as a property of the registry, not a comment.
3. **Missing capability returns a gap.** The acquisition registry already sets
   this precedent (``SourceRegistration.covers`` / ``CapabilityGap`` / a
   ``SourceNotFoundError`` that is raised rather than swallowed). Silent
   substitution is how a partial analysis gets reported as a complete one.

This module holds the contract and nothing else: no mathematics, no I/O.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# -- §30.3 operator classes --------------------------------------------------


class OperatorClass(enum.StrEnum):
    """The 21 reasoning-operator classes (§30.3)."""

    NORMALIZATION = "normalization"
    COMPATIBILITY = "compatibility"
    GLUING = "gluing"
    STATE_ESTIMATION = "state_estimation"
    ABDUCTION = "abduction"
    DEDUCTION = "deduction"
    DIALECTICS = "dialectics"
    BAYESIAN_UPDATE = "bayesian_update"
    ARGUMENTATION = "argumentation"
    TEMPORAL = "temporal"
    CHANGE_POINT = "change_point"
    REGIME = "regime"
    TDA = "tda"
    CAUSAL = "causal"
    GRAPH_ANALYSIS = "graph_analysis"
    INFORMATION_GAIN = "information_gain"
    SATURATION = "saturation"
    CALIBRATION = "calibration"
    ANOMALY = "anomaly"
    SCENARIO = "scenario"
    INDEPENDENCE = "independence"


# -- §4.1 determinism --------------------------------------------------------


class Determinism(enum.StrEnum):
    """Replay-identity class (§4.1)."""

    EXACT = "exact"
    FIXED_POINT = "fixed_point"
    FLOAT_QUANTIZED = "float_quantized"
    #: Admitted only with a written reason, and never inside a deterministic core.
    NON_DETERMINISTIC = "non_deterministic"


class NumericMode(enum.StrEnum):
    EXACT = "exact"
    FIXED_POINT = "fixed_point"
    FLOAT_QUANTIZED = "float_quantized"


# -- §31 execution tiers -----------------------------------------------------


class Tier(enum.IntEnum):
    """Execution tiers (§31). Lower is cheaper and more fundamental."""

    DETERMINISTIC = 0
    SYMBOLIC = 1
    STATISTICAL = 2
    ADAPTIVE = 3


#: §31: "Tier 3 must never be required for correctness of the deterministic core."
DETERMINISTIC_CORE_MAX_TIER = Tier.DETERMINISTIC


# -- complexity / resource ---------------------------------------------------


class ComplexityClass(enum.StrEnum):
    O1 = "o1"
    ON = "on"
    ON_LOG_N = "on_log_n"
    ON_SQUARED = "on_squared"
    ON_CUBED = "on_cubed"
    EXPONENTIAL = "exponential"


class MemoryClass(enum.StrEnum):
    CONSTANT = "constant"
    LINEAR = "linear"
    QUADRATIC = "quadratic"


# -- contracts and results ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContractRef:
    """A named, versioned data contract (``input_contract`` / ``output_contract``)."""

    name: str
    version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a contract reference must be named")

    def __str__(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of ``validate_input``."""

    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @classmethod
    def accept(cls, *warnings: str) -> ValidationResult:
        return cls(ok=True, warnings=tuple(warnings))

    @classmethod
    def reject(cls, *errors: str) -> ValidationResult:
        return cls(ok=False, errors=tuple(errors))


@dataclass(frozen=True, slots=True)
class ExplanationTrace:
    """``explain(result)``: why this operator returned what it returned."""

    operator_id: str
    summary: str
    inputs_used: tuple[str, ...] = ()
    parameters_used: Mapping[str, Any] = field(default_factory=dict)
    seed: int | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OperatorResult:
    """One operator invocation, with everything needed to replay and audit it."""

    operator_id: str
    operator_version: str
    determinism: Determinism
    value: Any
    #: Declared dependency versions. §48.3/R7: must resolve from the first
    #: registration, never retrofitted, or replay cannot be trusted.
    dependency_fingerprint: str = ""
    method_fingerprint: str = ""
    explanation: ExplanationTrace | None = None
    deferred: bool = False
    deferral_reason: str = ""

    def __post_init__(self) -> None:
        if self.deferred and not self.deferral_reason:
            raise ValueError("a deferred result must say why it was deferred")

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "operator_id": self.operator_id,
            "operator_version": self.operator_version,
            "determinism": self.determinism.value,
            "value": self.value,
            "dependency_fingerprint": self.dependency_fingerprint,
            "method_fingerprint": self.method_fingerprint,
            "deferred": self.deferred,
        }
        if self.deferred:
            payload["deferral_reason"] = self.deferral_reason
        return payload


@runtime_checkable
class ReasoningOperator(Protocol):
    """The §30.1 contract. Implementations are adapters over existing code."""

    id: str
    version: str
    operator_class: OperatorClass
    input_contract: ContractRef
    output_contract: ContractRef
    determinism: Determinism
    numeric_mode: NumericMode
    complexity: ComplexityModel

    def validate_input(self, input_view: Any) -> ValidationResult: ...

    def run(self, input_view: Any, parameters: Any, seed: int) -> OperatorResult: ...

    def explain(self, result: OperatorResult) -> ExplanationTrace: ...


@dataclass(frozen=True, slots=True)
class ComplexityModel:
    """Declared cost, so a planner can refuse work rather than discover it."""

    time: ComplexityClass = ComplexityClass.ON
    memory: MemoryClass = MemoryClass.LINEAR
    #: Rough wall-clock budget in milliseconds; advisory, not a deadline.
    budget_ms: int = 0
    notes: str = ""


@dataclass(frozen=True, slots=True)
class Capability:
    """One declared capability an operator provides.

    Kept as an explicit object rather than a bare string so the registry can
    report *why* a selection failed instead of returning an empty list.
    """

    name: str
    description: str = ""

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class OperatorRegistration:
    """A registered operator and everything a selection needs to judge it."""

    operator: ReasoningOperator
    capabilities: frozenset[str]
    parameter_schema: Mapping[str, Any] = field(default_factory=dict)
    supports_incremental: bool = False
    supports_replay: bool = True
    license: str = ""
    isolation_requirements: tuple[str, ...] = ()
    safety_policy: Mapping[str, Any] = field(default_factory=dict)
    cache_policy: Mapping[str, Any] = field(default_factory=dict)
    #: Declared tier. Defaults to Tier 0 so an undeclared operator is treated as
    #: cheap and deterministic rather than accidentally allowed into the core.
    tier: Tier = Tier.DETERMINISTIC
    #: A reason is mandatory for a non-deterministic operator; §4.1 requires one.
    nondeterminism_reason: str = ""

    @property
    def key(self) -> str:
        return f"{self.operator.id}@{self.operator.version}"

    @property
    def operator_class(self) -> OperatorClass:
        return self.operator.operator_class

    @property
    def determinism(self) -> Determinism:
        return self.operator.determinism

    def covers(self, required: frozenset[str]) -> bool:
        return required.issubset(self.capabilities)

    def satisfies_deterministic_core(self) -> bool:
        """§31: the deterministic core may not depend on Tier 3."""
        if self.tier <= DETERMINISTIC_CORE_MAX_TIER:
            return True
        return self.determinism is not Determinism.NON_DETERMINISTIC and bool(
            self.nondeterminism_reason
        )


def required_capabilities(*names: str) -> frozenset[str]:
    """Convenience for building a requirement set."""
    return frozenset(names)


def describe(registration: OperatorRegistration) -> dict[str, Any]:
    """Serialisable metadata block (§30.2)."""
    operator = registration.operator
    return {
        "id": operator.id,
        "version": operator.version,
        "operator_class": operator.operator_class.value,
        "input_contract": str(operator.input_contract),
        "output_contract": str(operator.output_contract),
        "tier": int(registration.tier),
        "determinism_mode": operator.determinism.value,
        "numeric_mode": operator.numeric_mode.value,
        "complexity_class": operator.complexity.time.value,
        "memory_class": operator.complexity.memory.value,
        "capabilities": sorted(registration.capabilities),
        "parameter_schema": dict(registration.parameter_schema),
        "supports_incremental": registration.supports_incremental,
        "supports_replay": registration.supports_replay,
        "license": registration.license,
        "isolation_requirements": list(registration.isolation_requirements),
        "safety_policy": dict(registration.safety_policy),
        "cache_policy": dict(registration.cache_policy),
    }


def known_classes() -> Sequence[OperatorClass]:
    """All 21 classes, for validation and for UI filters."""
    return tuple(OperatorClass)
