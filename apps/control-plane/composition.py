"""The composition root: every live component, constructed once and wired together.

Named ``composition`` rather than ``platform`` on purpose. A module called ``platform`` at
the root of a package on the default ``sys.path`` shadows the standard library's
``platform`` module for every import in the process -- ``make_session_factory`` failed with
``module 'platform' has no attribute 'python_implementation'`` and the durable authority
silently failed to come up. A composition root that breaks the standard library is not a
composition root.

Until this module existed the platform had no assembly. Each component was correct in
isolation and reachable only from tests: ``PostgresContextStore`` was built per request by
six different routes, ``FabricStore`` and ``DurableFabricRunner`` had exactly one reference
-- their own definition -- and ``CognitiveLoop.tick`` had no production caller at all. The
API's ``lifespan`` was an empty generator with a comment that telemetry *would* go there.

An investigation created through the API therefore produced a durable context row and
nothing else: no loop to iterate it, no fabric to grow it, no query cycle to plan
acquisition, no workflow to run the batches.

So this module is deliberately boring. It constructs, it does not decide. Which database,
which catalogue, whether Temporal is reachable -- those are inputs from settings, and the
policy lives in the components. What it does own is the thing that was missing: a single
place where the pieces meet, so that starting the platform actually starts the platform.

Degradation is a first-class concern, not a fallback afterthought. ``start()`` never
raises. A deployment without PostgreSQL, or without Temporal, or without the acquisition
wheel, boots with the components it has and records the ones it does not in
:attr:`Platform.health`. A composition root that refuses to boot turns every missing
optional subsystem into a total outage, and the resulting failure is at startup where it
is hardest to attribute -- rather than at the one call that needed the missing piece.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: Where the declarative source catalogue lives, relative to this package.
_CATALOGUE_ROOT = Path(__file__).resolve().parents[1] / "acquisition" / "sources" / "estorides"


@dataclass(slots=True)
class Health:
    """Which components came up, and what each one says.

    Reported rather than raised. A platform that boots with three of five subsystems has
    something useful to offer, and an operator needs to know *which three* -- an exception
    at startup would tell them nothing except that something is wrong.
    """

    durable: str = "absent"
    fabric: str = "absent"
    catalogue: str = "absent"
    return_path: str = "absent"
    temporal: str = "absent"
    queries: str = "absent"
    notes: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """Whether the durable authority came up.

        Everything else degrades; this does not. Without PostgreSQL there is no authority,
        and a platform that reports itself healthy while holding its context in memory is
        the exact failure this whole layer exists to prevent.
        """
        return self.durable == "ready"

    @property
    def cycles(self) -> bool:
        """Whether a tick can actually run: durable context plus a fabric pass."""
        return self.ready and self.fabric == "ready"

    def as_dict(self) -> dict[str, Any]:
        return {
            "durable": self.durable,
            "fabric": self.fabric,
            "catalogue": self.catalogue,
            "return_path": self.return_path,
            "temporal": self.temporal,
            "queries": self.queries,
            "ready": self.ready,
            "cycles": self.cycles,
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class Platform:
    """The assembled platform. Construct with :meth:`build`, not directly.

    Fields are Optional rather than defaulted because "component absent" and "component
    present but empty" are different states: the first is a degradation to report, the
    second is a bug in whatever populated it.
    """

    health: Health
    store: Any = None
    fabric_store: Any = None
    fabric_runner: Any = None
    loop: Any = None
    cycle: Any = None
    ledger: Any = None
    bridge: Any = None
    session_factory: Any = None
    frontier: Any = None
    concept_registry: Any = None
    sources: int = 0
    #: Reader class for the return path. Held as a class rather than an instance because the
    #: instance is per-call (one session per read), and ``slots=True`` rejects attributes
    #: that were not declared as fields.
    membership_reader_factory: Any = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    # -- construction --------------------------------------------------------

    @classmethod
    async def build(
        cls,
        *,
        dsn: str | None = None,
        tenant_id: str = "default-tenant",
        catalogue_root: Path | None = None,
        enable_temporal_probe: bool = False,
    ) -> Platform:
        """Construct every component that can be constructed, and record the rest.

        Never raises for a missing subsystem. Each step is attempted independently so one
        absent wheel cannot prevent the others from coming up.
        """
        health = Health()
        platform = cls(health=health)

        await platform._build_durable(dsn, tenant_id)
        await platform._build_fabric(tenant_id)
        await platform._build_catalogue(catalogue_root or _CATALOGUE_ROOT)
        await platform._build_return_path()
        if enable_temporal_probe:
            await platform._probe_temporal(tenant_id)

        if platform.loop is not None:
            from context_engine.query_cycle import CycleLedger, QueryCycle

            platform.cycle = QueryCycle(
                registry=platform.concept_registry,
                reader=platform._membership_reader(),
            )
            platform.ledger = CycleLedger()
            health.queries = "ready" if platform.cycle is not None else "degraded"

        return platform

    async def _build_durable(self, dsn: str | None, tenant_id: str) -> None:
        """The durable authority: context store plus an entity-stream session factory.

        One connection factory serves both, so the context and the membership lookups read
        the same database. Two factories would allow the platform to read membership from a
        different database than the context it is grounding -- a failure that only appears
        when the context is empty and nothing ever deepens.
        """
        try:
            from context_engine.postgres_store import PostgresContextStore
            from db.session import make_session_factory

            factory = make_session_factory(dsn) if dsn else make_session_factory()
            self.session_factory = factory
            self.store = PostgresContextStore(
                tenant_id=tenant_id, connection_factory=factory
            )
            await self.store.ensure_schema()
            self.health.durable = "ready"
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            self.health.durable = "absent"
            self.health.notes.append(f"durable authority unavailable: {exc}")
            log.warning("durable authority unavailable: %s", exc)

    async def _build_fabric(self, tenant_id: str) -> None:
        """Fabric persistence plus the loop that grows the context.

        Without the store there is no authority and therefore no fabric: a fabric pass over
        cells held in memory would produce a report nobody else can read, and the context
        would appear to deepen in exactly the process that should not be trusted with it.
        """
        if self.store is None:
            self.health.fabric = "absent"
            self.health.notes.append("fabric skipped: no durable store")
            return
        try:
            from context_engine.engine import ContextEngine
            from context_engine.fabric_runner import DurableFabricRunner
            from context_engine.fabric_store import FabricStore
            from context_engine.loop import CognitiveLoop

            self.fabric_store = FabricStore(self.store, tenant_id=tenant_id)
            await self.fabric_store.ensure_schema()
            self.fabric_runner = DurableFabricRunner(self.fabric_store, tenant_id=tenant_id)
            self.loop = CognitiveLoop(ContextEngine(self.store), fabric=self.fabric_runner)
            self.health.fabric = "ready"
        except Exception as exc:  # noqa: BLE001
            self.health.fabric = "absent"
            self.health.notes.append(f"fabric unavailable: {exc}")
            log.warning("fabric unavailable: %s", exc)

    async def _build_catalogue(self, root: Path) -> None:
        """The declarative source catalogue and the routing bridge over it.

        Read from YAML rather than from each runtime's ``capabilities()``, because
        capabilities *check* compatibility after a runtime is chosen and never choose one.
        """
        try:
            from sources.catalogue import load_catalogue

            from context_engine.catalogue_bridge import SourceCatalogueBridge

            definitions, rejects = load_catalogue(root)
            self.sources = len(definitions)
            self.bridge = SourceCatalogueBridge.from_source_definitions(definitions)
            self.concept_registry = _catalogue_concepts(definitions)
            self.health.catalogue = "ready"
            if rejects:
                self.health.notes.append(
                    f"{len(rejects)} source definitions rejected by the loader"
                )
        except Exception as exc:  # noqa: BLE001
            self.health.catalogue = "absent"
            self.health.notes.append(f"catalogue unavailable: {exc}")
            log.warning("catalogue unavailable: %s", exc)

    async def _build_return_path(self) -> None:
        """The observation -> entities reader the return path needs.

        Built as a thin adapter rather than handing the session factory straight to the
        cycle: the cycle's reader is a one-method Protocol, and this is where the SQLAlchemy
        session actually gets opened and closed.
        """
        if self.session_factory is None:
            self.health.return_path = "absent"
            self.health.notes.append("return path skipped: no session factory")
            return

        class _SessionMembershipReader:
            """Opens one session per read, scoped to a tenant."""

            def __init__(self, factory: Any) -> None:
                self._factory = factory

            async def entities_for_observations(
                self, *, tenant_id: str, observation_ids: Sequence[str]
            ) -> dict[str, tuple[str, ...]]:
                from db.entity_stream import SqlEntityStreamRepository

                if not tenant_id:
                    raise ValueError("tenant_id is required to resolve membership")
                session = self._factory()
                try:
                    repository = SqlEntityStreamRepository(session)
                    return await repository.entities_for_observations(
                        tenant_id=tenant_id, observation_ids=observation_ids
                    )
                finally:
                    await session.close()

        self.membership_reader_factory = _SessionMembershipReader
        self.health.return_path = "ready"

    def _membership_reader(self) -> Any:
        if self.session_factory is None:
            return None
        return self.membership_reader_factory(self.session_factory)

    async def _probe_temporal(self, tenant_id: str) -> None:
        """Report whether the workflow server is reachable. Never starts work."""
        try:
            from workflow.client import connect_temporal

            await connect_temporal()
            self.health.temporal = "ready"
        except Exception as exc:  # noqa: BLE001
            self.health.temporal = "absent"
            self.health.notes.append(f"temporal unavailable: {exc}")

    # -- use -----------------------------------------------------------------

    @property
    def durable(self) -> bool:
        return self.store is not None

    @property
    def can_cycle(self) -> bool:
        return self.store is not None and self.loop is not None and self.cycle is not None

    def tick_service(self) -> Any:
        """Build a tick service over this assembly, or ``None`` when a cycle cannot run."""
        if not self.can_cycle:
            return None
        from services.cycle_service import CycleService

        return CycleService(
            store=self.store,
            fabric_store=self.fabric_store,
            loop=self.loop,
            cycle=self.cycle,
            ledger=self.ledger,
            bridge=self.bridge,
            session_factory=self.session_factory,
            frontier_factory=self._frontier,
        )

    def _frontier(self) -> Any:
        """A frontier bound to the same session factory, or ``None``.

        Constructed per use rather than held: ``PgFrontier`` leases rows, and a single
        long-lived instance would hold a session across ticks and accumulate uncommitted
        leases.
        """
        if self.session_factory is None:
            return None
        try:
            from services.frontier import PgFrontier

            return PgFrontier(self.session_factory)
        except Exception as exc:  # noqa: BLE001
            self.health.notes.append(f"frontier unavailable: {exc}")
            return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sources": self.sources,
            "has_store": self.store is not None,
            "has_loop": self.loop is not None,
            "has_cycle": self.cycle is not None,
            "has_bridge": self.bridge is not None,
            **self.health.as_dict(),
        }


def _catalogue_concepts(definitions: Sequence[Any]) -> Any:
    """A concept registry seeded from the catalogue.

    Built from ``applies_to`` and ``entity_hints`` rather than inventing a vocabulary: a
    term the catalogue already indexes is a term a query can be bound to, and using the
    catalogue's own terms is what keeps the two from drifting.
    """
    from context.query_binding import StaticConceptRegistry

    entries: dict[str, str] = {}
    for definition in definitions:
        name = str(getattr(definition, "name", "") or "")
        source_id = str(getattr(definition, "source_id", "") or "")
        if not name or not source_id:
            continue
        entries[name] = source_id
        entries[name.replace("-", "_")] = source_id
        for hint in getattr(definition, "entity_hints", ()) or ():
            key = str(hint).replace("-", "_")
            if key and key not in entries:
                entries[key] = source_id
    return StaticConceptRegistry(entries)


# -- process-wide access ------------------------------------------------------

_PLATFORM: Platform | None = None
_PLATFORM_LOCK = asyncio.Lock()


async def get_platform(*, dsn: str | None = None, tenant_id: str = "default-tenant") -> Platform:
    """The process-wide platform, built on first use.

    Cached rather than rebuilt per request: the fabric's cells and the cycle's ledger are
    per-context state that would be lost between two calls, and rebuilding would also open a
    new connection pool per request.
    """
    global _PLATFORM
    if _PLATFORM is not None:
        return _PLATFORM
    async with _PLATFORM_LOCK:
        if _PLATFORM is None:
            _PLATFORM = await Platform.build(dsn=dsn, tenant_id=tenant_id)
    return _PLATFORM


def set_platform(platform: Platform | None) -> None:
    """Install or clear the process-wide platform. For tests and for shutdown."""
    global _PLATFORM
    _PLATFORM = platform


async def close_platform() -> None:
    """Drop the cached platform so the next use rebuilds it."""
    global _PLATFORM
    _PLATFORM = None
