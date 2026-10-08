"""Catalogue bridge: Context Planner to Runtime Dispatcher (Feature 024 D4=a, Phase 6).

FR-067/068/069. The gap this closes is specific: 146 source definitions already exist
as declarative YAML in ``apps/acquisition/sources/estorides/``, already loaded by
``sources/catalogue.py`` and already served by ``GET /api/v1/connectors`` and
``/api/v1/tools``. Meanwhile the Context Engine needs to know what capabilities exist
so it can decide whether an obligation is even actionable.

The tempting fix -- read capabilities from each runtime's ``capabilities()`` method --
is forbidden by ``apps/acquisition/runtime/__init__.py:10-14``, which states that
capabilities are used to *check* compatibility after a runtime is resolved by name and
to *choose* it. This module therefore reads the catalogue, not the runtimes.

Reused, not rewritten: the catalogue loader and the source-definition schema already
exist in ``apps/acquisition``. This module only reads them and flattens them into the
descriptor shape the Context Engine consumes.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from context_engine.engine import CapabilityDescriptor

#: Which runtime executes a source of each declared kind. Keyed on the exact kind value,
#: not a substring: ``system_app`` and ``http`` are execution surfaces the platform already
#: has, and a source naming a kind not listed here has no runtime and is left unrouted
#: rather than guessed at.
_KIND_RUNTIMES: dict[str, str] = {
    "http": "http",
    "system_app": "external_tool",
}


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """What the bridge decided, and why.

    Recorded rather than returned bare: a routing decision that cannot name its own
    inputs is not auditable, and an unauditable acquisition is the platform's core
    risk.
    """

    runtime_ref: str
    source_id: str
    capability_match: bool
    required: tuple[str, ...]
    available: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_ref": self.runtime_ref,
            "source_id": self.source_id,
            "capability_match": self.capability_match,
            "required": list(self.required),
            "available": list(self.available),
            "reason": self.reason,
        }


def _runtime_ref_of(definition: Any) -> str:
    """The routing identity for a catalogue source.

    Taken from the definition's own ``runtime_ref`` when it declares one, and otherwise
    derived from its ``kind``. The derivation is what makes this bridge usable at all:
    145 of the catalogue's sources are HTTP or system tools with no declared runtime, and
    filtering them out left the bridge permanently empty -- so ``check()`` answered
    "not in the catalogue" for every capability and no obligation could ever be routed.

    The mapping is explicit rather than inferred from the kind string, because a substring
    match would silently route ``system_app`` sources to the wrong executor the first time
    a new kind appeared.
    """
    declared = str(getattr(definition, "runtime_ref", "") or "").strip()
    if declared:
        return declared
    kind = str(getattr(definition, "kind", "") or "").strip().lower()
    return _KIND_RUNTIMES.get(kind, "")


class SourceCatalogueBridge:
    """Reads declarative capabilities and gates routing on them.

    ``runtime_ref`` stays the routing identity. Capabilities gate; they never select
    (FR-067). ``route`` therefore takes the runtime first and reports whether its
    declared capabilities satisfy the obligation's requirements -- it does not search
    the catalogue for a runtime that does.
    """

    def __init__(self, descriptors: Iterable[CapabilityDescriptor] = ()) -> None:
        self._by_runtime: dict[str, CapabilityDescriptor] = {}
        for descriptor in descriptors:
            self._by_runtime.setdefault(descriptor.runtime_ref, descriptor)

    # -- construction --------------------------------------------------------

    @classmethod
    def from_source_definitions(
        cls, definitions: Iterable[Any]
    ) -> SourceCatalogueBridge:
        """Build from ``catalogue.SourceDefinition`` objects.

        Takes the catalogue's own records rather than re-parsing YAML, so the bridge
        cannot drift from what the platform actually serves over HTTP.
        """
        descriptors: list[CapabilityDescriptor] = []
        for definition in definitions:
            capabilities = tuple(sorted(_capabilities_of(definition)))
            if not capabilities:
                continue
            descriptors.append(
                CapabilityDescriptor(
                    runtime_ref=_runtime_ref_of(definition),
                    capabilities=capabilities,
                    source_id=str(getattr(definition, "source_id", "") or ""),
                    cost_class=str(
                        getattr(definition, "cost_class", "") or "cheap"
                    ),
                    active=bool(getattr(definition, "active", True)),
                )
            )
        return cls(d for d in descriptors if d.runtime_ref)

    # -- queries -------------------------------------------------------------

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(
            sorted(self._by_runtime.values(), key=lambda d: (d.runtime_ref, d.source_id))
        )

    def capability_index(self) -> dict[str, tuple[str, ...]]:
        """capability -> runtime_refs that declare it.

        For discovery and for reporting what a missing capability would need -- never
        for choosing a runtime.
        """
        index: dict[str, set[str]] = {}
        for descriptor in self._by_runtime.values():
            for capability in descriptor.capabilities:
                index.setdefault(capability, set()).add(descriptor.runtime_ref)
        return {capability: tuple(sorted(refs)) for capability, refs in sorted(index.items())}

    def check(
        self, runtime_ref: str, required: Iterable[str]
    ) -> RoutingDecision:
        """Compatibility check for an already-chosen runtime."""
        wanted = tuple(sorted(set(required)))
        descriptor = self._by_runtime.get(runtime_ref)
        if descriptor is None:
            return RoutingDecision(
                runtime_ref=runtime_ref,
                source_id="",
                capability_match=False,
                required=wanted,
                available=(),
                reason=f"{runtime_ref} is not in the catalogue",
            )
        missing = sorted(set(wanted) - set(descriptor.capabilities))
        return RoutingDecision(
            runtime_ref=runtime_ref,
            source_id=descriptor.source_id,
            capability_match=not missing,
            required=wanted,
            available=descriptor.capabilities,
            reason=(
                "capabilities satisfy the requirement"
                if not missing
                else f"missing capabilities: {missing}"
            ),
        )

    def missing_capability_report(self, required: Iterable[str]) -> dict[str, tuple[str, ...]]:
        """FR-040. What an obligation needs and nothing currently offers.

        Reported so the gap becomes a stated capability requirement rather than an
        engine that quietly implements what it was never asked to implement.
        """
        index = self.capability_index()
        return {
            capability: index.get(capability, ())
            for capability in sorted(set(required))
        }

    def iter_runtime_refs(self) -> Iterator[str]:
        return iter(sorted(self._by_runtime))


def _capabilities_of(definition: Any) -> set[str]:
    """Pull declared capabilities off a catalogue record, tolerating shape drift.

    The catalogue is data, so this reads defensively: an unknown shape yields no
    capabilities, which fails the compatibility check rather than routing wrongly.
    """
    found: set[str] = set()

    for attribute in ("capabilities", "tags", "kind"):
        value = getattr(definition, attribute, None)
        if isinstance(value, str) and value:
            found.add(value)
        elif isinstance(value, (list, tuple, set, frozenset)):
            found.update(str(v) for v in value if str(v))

    applies_to = getattr(definition, "applies_to", None)
    if isinstance(applies_to, (list, tuple, set, frozenset)):
        found.update(f"applies:{v!s}" for v in applies_to if str(v))

    contact = getattr(definition, "contact", None)
    if isinstance(contact, str) and contact:
        found.add(f"contact:{contact}")

    return {c for c in found if c}


__all__ = ["RoutingDecision", "SourceCatalogueBridge"]