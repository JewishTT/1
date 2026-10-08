"""The operator registry (spec 025 §30.4, Phase J / T025-087).

    Donor implementation -> Adapter -> ReasoningOperator -> Registry -> Planner

The contract precedent is not invented here. ``acquisition/adapters/registry.py``
already solved the same problem for source selection and its shape was copied
deliberately: validate on register, select by capability intersection, and return
an explicit gap object instead of substituting something close enough. That last
property is the one that matters most for this platform -- a capability silently
replaced by a weaker operator produces an analysis that looks complete and is not.

The one addition the acquisition registry does not need is tier discipline. §31
binds the deterministic core to Tier 0, so ``select`` takes a ceiling and the
registry refuses to hand back a Tier 3 operator when the caller is building the
core.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from context.operators.base import (
    ComplexityModel,
    Determinism,
    NumericMode,
    OperatorClass,
    OperatorRegistration,
    Tier,
)


class OperatorRegistrationError(ValueError):
    """Raised when an operator cannot honestly be registered."""


class OperatorNotFoundError(KeyError):
    """Raised on an exact lookup miss. Never swallowed."""


class GapReason(enum.StrEnum):
    """Why a selection failed. The three cases need different responses."""

    #: Some required capability has no registered provider at all.
    NO_PROVIDER = "no_provider"
    #: Every capability exists, but no single operator covers the combination.
    #: This is a composition problem, not a missing capability.
    NO_SINGLE_PROVIDER = "no_single_provider"
    #: Suitable operators exist but were filtered out by tier or replay policy.
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class CapabilityGap:
    """What a selection asked for and could not have.

    Returning this instead of an empty list is what makes "no operator can do
    this" legible to a caller instead of looking like an operator that happened
    to return nothing.

    Three failure modes are kept apart, because conflating them produces the
    worst outcome: a caller that asked for two capabilities no single operator
    holds, and is told "nothing provides capability X", writes code to go looking
    for X forever.
    """

    required: frozenset[str]
    #: Union of capabilities across candidates that matched on shape, before any
    #: tier or replay filter.
    available: frozenset[str] = frozenset()
    #: Capabilities no registered operator provides at all.
    uncovered: frozenset[str] = frozenset()
    excluded: tuple[tuple[str, str], ...] = ()
    reason: GapReason = GapReason.NO_SINGLE_PROVIDER

    @property
    def missing(self) -> frozenset[str]:
        """Capabilities not satisfiable by any single viable candidate."""
        return self.required - self.available

    @property
    def ok(self) -> bool:
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason.value,
            "required": sorted(self.required),
            "missing": sorted(self.missing),
            "uncovered": sorted(self.uncovered),
            "available": sorted(self.available),
            "excluded": [
                {"operator": operator_id, "reason": reason}
                for operator_id, reason in self.excluded
            ],
        }

    def __str__(self) -> str:
        if self.reason is GapReason.NO_PROVIDER:
            return f"no operator provides: {sorted(self.uncovered)}"
        if self.reason is GapReason.EXCLUDED:
            return f"all candidates excluded by policy: {sorted(self.required)}"
        return f"no single operator covers: {sorted(self.missing)}"


@dataclass(frozen=True, slots=True)
class Selection:
    """A resolved selection, or a gap. Exactly one of the two is populated."""

    registration: OperatorRegistration | None = None
    gap: CapabilityGap | None = None

    @property
    def ok(self) -> bool:
        return self.registration is not None

    def unwrap(self) -> OperatorRegistration:
        if self.registration is None:
            raise OperatorNotFoundError(str(self.gap))
        return self.registration


@dataclass
class _Registry:
    """Mutable registry state, exposed only through the methods below."""

    _by_key: dict[str, OperatorRegistration] = field(default_factory=dict)
    _by_class: dict[OperatorClass, list[str]] = field(default_factory=dict)
    _capability_index: dict[str, list[str]] = field(default_factory=dict)

    # -- registration -------------------------------------------------------

    def register(self, registration: OperatorRegistration) -> OperatorRegistration:
        """Register an operator, refusing anything it cannot honestly declare.

        Validation happens here rather than at run time so that an operator
        which cannot state its determinism class never becomes selectable.
        """
        _validate(registration)

        key = registration.key
        existing = self._by_key.get(key)
        if existing is not None:
            if existing.capabilities == registration.capabilities and (
                existing.operator.operator_class is registration.operator_class
            ):
                # Idempotent re-registration of an identical operator.
                return existing
            raise OperatorRegistrationError(
                f"{key} is already registered with a different shape"
            )

        self._by_key[key] = registration
        self._by_class.setdefault(registration.operator_class, []).append(key)
        for capability in registration.capabilities:
            self._capability_index.setdefault(capability, []).append(key)
        return registration

    def register_operator(self, operator: Any, **kwargs: Any) -> OperatorRegistration:
        """Convenience wrapper for the common case."""
        capabilities = kwargs.pop("capabilities", frozenset())
        return self.register(
            OperatorRegistration(operator=operator, capabilities=capabilities, **kwargs)
        )

    # -- lookup -------------------------------------------------------------

    def get(self, operator_id: str, version: str | None = None) -> OperatorRegistration:
        if version is None:
            matches = [
                registration
                for registration in self._by_key.values()
                if registration.operator.id == operator_id
            ]
            if not matches:
                raise OperatorNotFoundError(operator_id)
            if len(matches) > 1:
                versions = sorted(m.operator.version for m in matches)
                raise OperatorNotFoundError(
                    f"{operator_id} is ambiguous across versions {versions}; "
                    "name the version explicitly"
                )
            return matches[0]
        key = f"{operator_id}@{version}"
        registration = self._by_key.get(key)
        if registration is None:
            raise OperatorNotFoundError(key)
        return registration

    def has(self, operator_id: str, version: str | None = None) -> bool:
        try:
            self.get(operator_id, version)
        except OperatorNotFoundError:
            return False
        return True

    def select(
        self,
        *,
        required: frozenset[str] | None = None,
        operator_class: OperatorClass | None = None,
        max_tier: Tier | None = None,
        supports_replay: bool | None = None,
    ) -> Selection:
        """Resolve one operator, or explain why none fits.

        Deterministic: candidates are ordered by key, so the same registry and
        the same requirement always yield the same operator.
        """
        requirement = required or frozenset()

        pool: Iterable[OperatorRegistration]
        if operator_class is not None:
            keys = self._by_class.get(operator_class, [])
            pool = [self._by_key[key] for key in sorted(keys)]
        else:
            pool = sorted(self._by_key.values(), key=lambda item: item.key)

        # Shape first: which candidates hold every required capability, before
        # any policy filter. This is what separates "nobody can" from
        # "nobody is allowed to".
        shape_ok = [item for item in pool if not requirement or item.covers(requirement)]
        available = (
            frozenset().union(*(item.capabilities for item in shape_ok))
            if shape_ok
            else frozenset()
        )

        excluded: list[tuple[str, str]] = []
        viable: list[OperatorRegistration] = []
        for registration in shape_ok:
            if max_tier is not None and registration.tier > max_tier:
                excluded.append(
                    (registration.key, f"tier {int(registration.tier)} > {int(max_tier)}")
                )
                continue
            if supports_replay is not None and registration.supports_replay != supports_replay:
                excluded.append((registration.key, "replay support mismatch"))
                continue
            viable.append(registration)

        if viable:
            return Selection(registration=viable[0])

        if not requirement:
            return Selection(
                gap=CapabilityGap(
                    required=requirement,
                    available=available,
                    excluded=tuple(excluded),
                    reason=GapReason.NO_PROVIDER,
                )
            )

        nothing_provides = requirement - frozenset(self._capability_index)
        if nothing_provides:
            reason = GapReason.NO_PROVIDER
        elif shape_ok:
            reason = GapReason.EXCLUDED
        else:
            reason = GapReason.NO_SINGLE_PROVIDER

        return Selection(
            gap=CapabilityGap(
                required=requirement,
                available=available,
                uncovered=nothing_provides,
                excluded=tuple(excluded),
                reason=reason,
            )
        )

    def select_all(
        self,
        *,
        required: frozenset[str] | None = None,
        max_tier: Tier | None = None,
    ) -> tuple[OperatorRegistration, ...]:
        """Every viable operator, key-ordered. For planners that combine several."""
        requirement = required or frozenset()
        found = [
            registration
            for registration in sorted(self._by_key.values(), key=lambda item: item.key)
            if (not requirement or registration.covers(requirement))
            and (max_tier is None or registration.tier <= max_tier)
        ]
        return tuple(found)

    def capabilities(self) -> frozenset[str]:
        return frozenset(self._capability_index)

    def classes(self) -> frozenset[OperatorClass]:
        return frozenset(self._by_class)

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_key))

    def __iter__(self) -> Iterator[OperatorRegistration]:
        for key in sorted(self._by_key):
            yield self._by_key[key]

    def __len__(self) -> int:
        return len(self._by_key)


def _validate(registration: OperatorRegistration) -> None:
    """Refuse registrations that cannot be replayed or cannot be explained."""
    operator = registration.operator
    if not operator.id:
        raise OperatorRegistrationError("an operator must declare an id")
    if not operator.version:
        raise OperatorRegistrationError(f"{operator.id} must declare a version")
    if not isinstance(operator.operator_class, OperatorClass):
        raise OperatorRegistrationError(
            f"{operator.id} declares an unknown operator class "
            f"{operator.operator_class!r}"
        )
    if not isinstance(operator.determinism, Determinism):
        raise OperatorRegistrationError(
            f"{operator.id} must declare a determinism mode (§4.1)"
        )
    if not isinstance(operator.numeric_mode, NumericMode):
        raise OperatorRegistrationError(f"{operator.id} must declare a numeric mode")
    if operator.determinism is Determinism.NON_DETERMINISTIC and not (
        registration.nondeterminism_reason
    ):
        raise OperatorRegistrationError(
            f"{operator.id} is non-deterministic and must state why (§4.1)"
        )
    if not isinstance(registration.tier, Tier):
        raise OperatorRegistrationError(f"{operator.id} must declare an execution tier (§31)")
    for name in ("validate_input", "run", "explain"):
        if not callable(getattr(operator, name, None)):
            raise OperatorRegistrationError(f"{operator.id} does not implement {name}()")
    if not isinstance(operator.complexity, ComplexityModel):
        raise OperatorRegistrationError(f"{operator.id} must declare a complexity model")


#: Module-level singleton, mirroring ``acquisition.adapters.registry.REGISTRY``.
REGISTRY = _Registry()


def registry() -> _Registry:
    """The process-wide registry."""
    return REGISTRY


def reset(registry_: _Registry | None = None) -> _Registry:
    """Install a fresh registry. The seam for an isolated test fixture."""
    global REGISTRY
    REGISTRY = registry_ if registry_ is not None else _Registry()
    return REGISTRY
