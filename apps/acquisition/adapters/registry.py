"""Source capability registry for the Global Collection Fabric (T090, R-03).

Replaces hard-coded source routing: a source is registered with its execution
class + capabilities, and the dispatcher selects by capability intersection.
No capable engine -> explicit :class:`CapabilityGap` (never a silent misroute).

Registration flows through the ONLY onboarding path:
    register source -> declare capabilities -> declare execution class
    -> declare policy requirements -> scheduler automatically becomes aware.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

AdapterCallable = Callable[[dict], Awaitable[dict]]

# Canonical capability surface; free-form additions are allowed.
KNOWN_CAPABILITIES = frozenset(
    {
        "http",
        "get",
        "headers",
        "etag",
        "last-modified",
        "javascript",
        "dom",
        "screenshot",
        "archive",
        "parquet",
        "warc",
        "bulk",
        "range-read",
        "content-addressed",
    }
)

EXECUTION_CLASSES = frozenset(
    {"http", "browser", "dataset", "archival", "feed", "api", "custom", "bulk"}
)


@dataclass(frozen=True)
class SourceRegistration:
    source_type: str
    execution_class: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    adapter: AdapterCallable | None = None

    def covers(self, required: frozenset[str]) -> bool:
        return required <= self.capabilities


@dataclass(frozen=True)
class CapabilityGap:
    task_id: str
    missing: frozenset[str]


class SourceNotFoundError(KeyError):
    """Raised when a source has not been registered (not a capability gap)."""


class _Registry:
    def __init__(self) -> None:
        self._sources: dict[str, SourceRegistration] = {}

    def register(self, registration: SourceRegistration) -> None:
        if registration.execution_class not in EXECUTION_CLASSES:
            raise ValueError(f"unknown execution class: {registration.execution_class}")
        unknown = registration.capabilities - KNOWN_CAPABILITIES
        if unknown:
            raise ValueError(f"unknown capabilities: {sorted(unknown)}")
        self._sources[registration.source_type] = registration

    def select(
        self, *, required: frozenset[str] | set[str] | None = None
    ) -> SourceRegistration | CapabilityGap:
        """Select the first registration covering the required capabilities.

        No required capabilities is treated as the conservative ``http``
        baseline. Returns a :class:`CapabilityGap` listing missing capabilities
        when nothing matches.
        """
        base = frozenset(required) if required else frozenset({"http"})
        missing = set(base)
        for registration in self._sources.values():
            if registration.covers(base):
                return registration
            missing -= registration.capabilities
        return CapabilityGap(task_id="", missing=frozenset(missing))

    def resolve_task(self, task: dict) -> SourceRegistration | CapabilityGap:
        """Registry entry point for the dispatcher: match a task dict.

        ``task`` carries ``task_id`` and ``required_capabilities`` (defaults to
        the ``http`` baseline). Returns a registration or an explicit gap.
        """
        task_id = str(task.get("task_id", ""))
        required = frozenset(task.get("required_capabilities") or {"http"})
        selection = self.select(required=required)
        if isinstance(selection, CapabilityGap):
            return CapabilityGap(task_id=task_id, missing=selection.missing)
        return selection

    def __iter__(self):
        return iter(self._sources.values())


# Single process-wide registry: adapters register at import time.
REGISTRY = _Registry()


def register(
    source_type: str,
    *,
    execution_class: str,
    capabilities: set[str] | frozenset[str],
    adapter: AdapterCallable | None = None,
) -> SourceRegistration:
    """Register a source with its capability surface (the only onboarding path)."""
    registration = SourceRegistration(
        source_type=source_type,
        execution_class=execution_class,
        capabilities=frozenset(capabilities),
        adapter=adapter,
    )
    REGISTRY.register(registration)
    return registration