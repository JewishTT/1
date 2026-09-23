"""Capability-annotated engine façade (T095): ``badge.match-by-badges``.

A *badge* is a durable capability token an engine exposes. The façade annotates
registered engines (the acquisition fabric's execution classes) with their badge
surfaces and answers "which engine covers these badges" without special-case
routing. It mirrors the acquisition adapter registry selection semantics
(capability intersection) but lives control-plane side so policy, modifier and
search layers can reason in badge space.

Badge surfaces derive from the canonical acquisition capability vocabulary
(``adapters.registry.KNOWN_CAPABILITIES``); every engine badge carries aliases
so free-text queries (T109) can resolve to a badge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Canonical badge vocabulary = capability tokens + engine-level badges.
BADGE_CATALOG: frozenset[str] = frozenset(
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

# Engine -> badge surface (execution class level, collection-fabric default).
ENGINE_BADGES: dict[str, frozenset[str]] = {
    "http": frozenset({"http", "get", "headers", "etag", "last-modified", "content-addressed"}),
    "browser": frozenset({"javascript", "dom", "screenshot", "http", "content-addressed"}),
    "dataset": frozenset({"parquet", "content-addressed"}),
    "archival": frozenset({"warc", "archive", "range-read", "content-addressed"}),
    "feed": frozenset({"http", "get", "headers"}),
    "api": frozenset({"http", "get", "headers"}),
    "custom": frozenset(),
    "bulk": frozenset({"bulk", "content-addressed"}),
}

# Engine -> human aliases (used by fuzzy resolution, T109).
ENGINE_ALIASES: dict[str, tuple[str, ...]] = {
    "http": ("http-fetch", "static-fetch", "http-adapter", "plain-http"),
    "browser": ("browser-render", "browsertrix", "js-render", "headless", "playwright"),
    "dataset": ("dataset-read", "parquet-read", "datasets", "warehouse"),
    "archival": ("archive-read", "warc-read", "wayback", "heritrix", "archive"),
    "feed": ("feed-poll", "rss", "atom", "feeds", "syndication"),
    "api": ("api-adapter", "rest", "graphql", "json-api"),
    "custom": ("custom-engine", "plugin"),
    "bulk": ("bulk-crawl", "bulk-backfill", "common-crawl", "cc", "wayback-cdx"),
}


@dataclass(frozen=True)
class EngineBadge:
    """An engine instance annotated with its badge surface."""

    engine: str
    badges: frozenset[str] = field(default_factory=frozenset)
    aliases: tuple[str, ...] = ()
    source_type: str | None = None

    def covers(self, required: frozenset[str] | set[str]) -> bool:
        return frozenset(required) <= self.badges

    @property
    def badge_tokens(self) -> tuple[str, ...]:
        return tuple(sorted(self.badges))


@dataclass(frozen=True)
class BadgeGap:
    """No engine covers a required badge set (never a silent misroute)."""

    required: frozenset[str]
    provided: frozenset[frozenset[str]]
    missing: frozenset[str]

    @property
    def closest_engine(self) -> str | None:
        if not self.provided:
            return None
        best = max(self.provided, key=lambda b: len(b & self.required))
        return ",".join(sorted(best & self.required)) or None


class BadgeNotFoundError(KeyError):
    """Raised for an unexpected badge id (not a gap)."""


class BadgeFacade:
    """Capability-annotated engine façade.

    Selection: :meth:`match_by_badges` returns every engine covering a required
    badge set. Missing capability -> explicit :class:`BadgeGap`.
    """

    def __init__(self) -> None:
        self._engines: list[EngineBadge] = []
        self._alias_index: dict[str, str] = {}

    def _rebuild_index(self) -> None:
        self._alias_index = {}
        for entry in self._engines:
            for token in entry.badge_tokens:
                self._alias_index[token] = token
            if entry.engine:
                self._alias_index[entry.engine] = entry.engine
            for alias in entry.aliases:
                self._alias_index[alias.lower()] = entry.engine

    def register(
        self,
        engine: str,
        *,
        badges: set[str] | frozenset[str] | None = None,
        aliases: tuple[str, ...] | list[str] = (),
        source_type: str | None = None,
    ) -> EngineBadge:
        """Register an engine instance with its badge surface."""
        surface = frozenset(badges) if badges is not None else ENGINE_BADGES.get(engine, frozenset())
        unknown = surface - BADGE_CATALOG
        if unknown:
            raise ValueError(f"unknown badge tokens: {sorted(unknown)}")
        if surface and not surface & BADGE_CATALOG:
            raise ValueError("engine badge surface must contain at least one catalog badge")
        entry = EngineBadge(
            engine=engine,
            badges=surface,
            aliases=tuple(a.lower() for a in aliases) or ENGINE_ALIASES.get(engine, ()),
            source_type=source_type,
        )
        self._engines.append(entry)
        self._rebuild_index()
        return entry

    def seed_defaults(self) -> BadgeFacade:
        """Annotate the canonical execution-class surface (useful hermetic id)."""
        for engine in ("http", "browser", "dataset", "archival", "feed", "api", "custom", "bulk"):
            self.register(engine)
        return self

    def from_adapters(self, registry=None) -> BadgeFacade:
        """Seed from the acquisition adapter registry (lazy import, best effort)."""
        if registry is None:
            try:
                from adapters.registry import REGISTRY  # type: ignore[import-not-found]
            except ImportError:
                return self.seed_defaults()
            registry = REGISTRY
        before = len(self)
        for source in registry:
            try:
                self.register(
                    source.execution_class,
                    badges=set(source.capabilities),
                    source_type=source.source_type,
                )
            except ValueError:
                continue
        if before == 0 and len(self) == 0:
            # Adapters register on import; a cold process holds an empty registry.
            # Best effort must still yield the canonical execution-class surface
            # rather than an empty façade.
            return self.seed_defaults()
        return self

    def match_by_badges(
        self,
        required: frozenset[str] | set[str],
        *,
        include_aliases: bool = True,
    ) -> list[EngineBadge]:
        """All engines covering ``required`` badges (badge.match-by-badges)."""
        wanted: set[str] = set(required)
        if include_aliases:
            resolved: set[str] = set()
            for b in wanted:
                canonical = self._resolve_alias(b)
                resolved.add(canonical if canonical is not None else b)
            wanted = resolved
        return [entry for entry in self._engines if entry.covers(frozenset(wanted))]

    def resolve(self, required: frozenset[str] | set[str]) -> EngineBadge | BadgeGap:
        matches = self.match_by_badges(required)
        if matches:
            return matches[0]
        wanted = frozenset(required)
        provided = frozenset(e.badges for e in self._engines)
        missing = wanted - frozenset().union(*[e.badges for e in self._engines]) if self._engines else wanted
        return BadgeGap(required=wanted, provided=provided, missing=missing)

    def resolve_task(self, task: dict) -> EngineBadge | BadgeGap:
        """Façade entry point: resolve a task dict (mirrors dispatcher semantics)."""
        required = frozenset(task.get("required_badges") or task.get("required_capabilities") or {"http"})
        return self.resolve(required)

    def badge(self, token: str) -> str:
        """Canonical badge for ``token`` (alias-aware)."""
        token = token.lower()
        if token in BADGE_CATALOG:
            return token
        resolved = self._resolve_alias(token)
        if resolved is None:
            raise BadgeNotFoundError(token)
        return resolved

    def engines_for(self, badge: str) -> list[str]:
        canonical = self.badge(badge)
        return sorted({e.engine for e in self._engines if canonical in e.badges})

    def _resolve_alias(self, token: str) -> str | None:
        return self._alias_index.get(token.lower())

    def __iter__(self):
        return iter(self._engines)

    def __len__(self) -> int:
        return len(self._engines)


def default_facade() -> BadgeFacade:
    """Process-wide façade seeded from the live adapter registry when reachable."""
    return BadgeFacade().from_adapters()