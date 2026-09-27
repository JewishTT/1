"""Discovery registry + frontier sink (T008-02, FR-005/FR-006).

The registry runs the registered sources for a seed, coalesces candidates and
pushes them into the frontier. The frontier is a protocol here: production
binds the Postgres frontier (ADR-0015); tests bind the in-memory sink. Kafka
is never the queue.

``register`` is also where the engine's access-control boundary is enforced
(FR-018, SC-008, Constitution VII): a source that declares a capability the
engine does not implement, or one that declares it needs an authentication wall,
a CAPTCHA or a paywall traversed, is refused **before** any query is issued. See
:func:`_refusal_reason`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .contracts import Candidate, DiscoverySource, coalesce

#: Every capability a discovery source may declare (FR-001). ``index`` is a
#: data-driven URL index, ``web-graph`` a link/adjacency source, ``api`` a query
#: interface. The set is closed on purpose: a capability the engine cannot honour
#: must be named at registration, where refusing it is a decision somebody can
#: read, rather than discovered later as a source that quietly did nothing.
ALLOWED_CAPABILITIES = frozenset({"index", "web-graph", "api"})

#: The only access mode the engine can honour. It ships **no** mechanism for
#: getting past authentication, CAPTCHA or a paywall -- it operates strictly
#: through a source's public interfaces (Constitution VII, FR-018) -- so a source
#: that needs one is not admissible, whatever it is called.
ALLOWED_ACCESS_MODES = frozenset({"public"})

#: Attributes a source may set to declare that answering *requires* defeating an
#: access control. Checked independently of ``access_mode`` because a source can
#: say both, and either one alone is already a refusal.
ACCESS_CONTROL_REQUIREMENTS = (
    "requires_access_control_bypass",
    "requires_authentication",
    "requires_captcha",
    "requires_paywall_bypass",
    "bypasses_access_controls",
)

#: Fragments that mark a declaration as naming an access control, wherever it
#: appears. Used only to say *why* a value is inadmissible, so the refusal reads
#: as a boundary decision instead of an unknown-value complaint.
_ACCESS_CONTROL_TOKENS = (
    "auth",
    "bypass",
    "captcha",
    "credential",
    "login",
    "paywall",
    "session",
    "token",
)


class DiscoverySourceRefused(ValueError):
    """A source the engine will not run, refused at registration (FR-018, SC-008).

    A ``ValueError`` because the declaration it rejects is a value the source got
    wrong, which is what ``register`` already raised for; a distinct type because
    "this source is inadmissible here" and "this source has no name" are
    different findings, and only one of them is a statement about the engine's
    boundary. The message names the source and the reason, so the refusal stands
    on its own in a log.
    """


def _refusal_reason(source: DiscoverySource) -> str | None:
    """Why ``source`` may not be registered, or ``None`` when it may be.

    A source is read through ``getattr`` rather than through the
    ``DiscoverySource`` protocol because the protocol declares ``name``,
    ``capabilities`` and ``discover`` and nothing else: the access-control
    declarations are optional, and a source that omits every one of them has
    declared nothing to refuse.
    """
    declared = {str(capability) for capability in getattr(source, "capabilities", None) or ()}
    unknown = declared - ALLOWED_CAPABILITIES
    if unknown:
        bypass = sorted(cap for cap in unknown if _names_an_access_control(cap))
        if bypass:
            return (
                f"it declares {bypass}, which require bypassing an access control. The engine "
                "operates only through a source's public interfaces and ships no mechanism for "
                "bypassing authentication, CAPTCHA, a paywall or any other access control "
                "(FR-018, Constitution VII)"
            )
        return f"it declares capabilities outside {sorted(ALLOWED_CAPABILITIES)}: {sorted(unknown)}"

    mode = str(getattr(source, "access_mode", "public"))
    if mode not in ALLOWED_ACCESS_MODES:
        return (
            f"it declares access mode {mode!r}; the only access mode the engine can honour is "
            f"{sorted(ALLOWED_ACCESS_MODES)}, because it operates strictly through a source's "
            "public interfaces and ships no mechanism for bypassing authentication, CAPTCHA, a "
            "paywall or any other access control (FR-018, Constitution VII)"
        )

    for requirement in ACCESS_CONTROL_REQUIREMENTS:
        if getattr(source, requirement, False):
            return (
                f"it declares {requirement}=True, i.e. that it needs an access control bypass to "
                "answer. The engine operates only through a source's public interfaces and ships "
                "no mechanism for bypassing authentication, CAPTCHA, a paywall or any other "
                "access control (FR-018, Constitution VII)"
            )
    return None


def _names_an_access_control(declaration: str) -> bool:
    """Whether a declared capability/access mode is naming an access control."""
    lowered = declaration.lower()
    return any(token in lowered for token in _ACCESS_CONTROL_TOKENS)


class FrontierSink(Protocol):
    """Minimal frontier contract discovery depends on (ADR-0015)."""

    def enqueue(
        self,
        *,
        uri: str,
        tenant_id: str,
        investigation_id: str,
        source: str,
        method: str,
        priority: int = 0,
        provenance: dict[str, Any] | None = None,
    ) -> None: ...


@dataclass
class InMemoryFrontierSink:
    """Deterministic sink for contract tests: idempotent by canonical URI."""

    items: dict[str, dict[str, Any]] = field(default_factory=dict)

    def enqueue(
        self,
        *,
        uri: str,
        tenant_id: str,
        investigation_id: str,
        source: str,
        method: str,
        priority: int = 0,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        if uri in self.items:
            return  # idempotent by canonical URL (FR-006)
        self.items[uri] = {
            "uri": uri,
            "tenant_id": tenant_id,
            "investigation_id": investigation_id,
            "source": source,
            "method": method,
            "priority": priority,
            "provenance": dict(provenance or {}),
        }

    def uris(self) -> list[str]:
        return sorted(self.items)


@dataclass(frozen=True)
class DiscoveryReport:
    """Auditable result of one discovery pass (never a silent hang)."""

    query: str
    sources_run: list[str]
    sources_failed: list[dict[str, str]]
    candidates_found: int
    enqueued: int
    empty_sources: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "sources_run": self.sources_run,
            "sources_failed": self.sources_failed,
            "candidates_found": self.candidates_found,
            "enqueued": self.enqueued,
            "empty_sources": self.empty_sources,
        }


class DiscoveryRegistry:
    """Runs registered discovery sources and feeds the frontier."""

    def __init__(self) -> None:
        self._sources: dict[str, DiscoverySource] = {}

    def register(self, source: DiscoverySource) -> None:
        """Admit a source, or refuse it and say why (FR-018, SC-008).

        Two things are checked here and nowhere else. The source must declare only
        capabilities the engine implements, and it must not declare that answering
        requires bypassing an access control -- the engine ships no such mechanism
        and operates strictly through sources' public interfaces (Constitution VII).

        **At registration, not at query time**, so the refusal is auditable before
        a single request is issued: a source refused on its first ``discover``
        would have already been handed a query, and the refusal would be
        indistinguishable from a source that happened to return nothing.
        """
        if not source.name:
            raise ValueError("discovery source requires a name")
        reason = _refusal_reason(source)
        if reason is not None:
            raise DiscoverySourceRefused(f"discovery source {source.name!r} is refused: {reason}")
        self._sources[source.name] = source

    def names(self) -> list[str]:
        return sorted(self._sources)

    def get(self, name: str) -> DiscoverySource | None:
        return self._sources.get(name)

    def discover(
        self,
        query: str,
        *,
        sources: Iterable[str] | None = None,
        frontier: FrontierSink | None = None,
        tenant_id: str = "default",
        investigation_id: str = "",
        priority: int = 0,
    ) -> DiscoveryReport:
        """Run sources for ``query``; coalesce; enqueue once per canonical URL."""
        selected = list(sources) if sources is not None else self.names()
        collected: list[Candidate] = []
        failed: list[dict[str, str]] = []
        empty: list[str] = []

        for name in selected:
            source = self._sources.get(name)
            if source is None:
                failed.append({"source": name, "error": "not registered"})
                continue
            try:
                found = source.discover(query)
            except Exception as exc:  # audited, never silently dropped
                failed.append({"source": name, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if not found:
                empty.append(name)
            collected.extend(found)

        coalesced = coalesce(collected)

        enqueued = 0
        if frontier is not None:
            before = len(getattr(frontier, "items", {}))
            for cand in coalesced:
                provenance = dict(cand.provenance)
                provenance.setdefault("discovery", {})
                provenance["discovery"].update(
                    {"source": cand.source, "method": cand.method, "query": cand.query}
                )
                frontier.enqueue(
                    uri=cand.canonical_url,
                    tenant_id=tenant_id,
                    investigation_id=investigation_id,
                    source=cand.source,
                    method=cand.method,
                    priority=priority,
                    provenance=provenance,
                )
            after = len(getattr(frontier, "items", {}))
            if after > before:
                enqueued = after - before
            else:
                # Sink without introspection: count unique canonical candidates.
                enqueued = len(coalesced)

        return DiscoveryReport(
            query=query,
            sources_run=selected,
            sources_failed=failed,
            candidates_found=len(coalesced),
            enqueued=enqueued,
            empty_sources=empty,
        )
