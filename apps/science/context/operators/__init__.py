"""Reasoning operators: the contract, the registry, and the adapters over existing
discipline code (spec 025 §30, plan.md reserved layout).

An operator is not an algorithm. It is an algorithm plus the declarations that
make it selectable and replayable: which contract it consumes, which determinism
class it answers to, what it costs, and what it can do. ``plan.md`` reserves
``compatibility.py`` / ``gluing.py`` / ``state.py`` / ``abduction.py`` /
``dialectics.py`` / ``information_gain.py`` / ``dynamics.py`` / ``tda.py`` /
``causal.py`` here; only ``base`` and ``registry`` exist so far.
"""

from __future__ import annotations

from context.operators.base import (
    Capability,
    ComplexityClass,
    ComplexityModel,
    ContractRef,
    Determinism,
    ExplanationTrace,
    MemoryClass,
    NumericMode,
    OperatorClass,
    OperatorRegistration,
    OperatorResult,
    ReasoningOperator,
    Tier,
    ValidationResult,
    describe,
    known_classes,
    required_capabilities,
)

__all__ = [
    "Capability",
    "ComplexityClass",
    "ComplexityModel",
    "ContractRef",
    "Determinism",
    "ExplanationTrace",
    "MemoryClass",
    "NumericMode",
    "OperatorClass",
    "OperatorRegistration",
    "OperatorResult",
    "ReasoningOperator",
    "Tier",
    "ValidationResult",
    "describe",
    "known_classes",
    "required_capabilities",
]
