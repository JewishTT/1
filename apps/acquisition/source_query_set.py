"""Deterministic multi-route source query planning (feature 015, US2).

``EntitySearchSurface`` is multidimensional, but execution was one-dimensional: a
single prioritized :func:`acquisition.cc_plan.build_cc_plan` result was executed and
every other identity dimension was discarded. This module derives an ordered,
deduplicated :class:`SourceQuerySet` covering every applicable route instead.

Design constraints:

* **Pure.** No network, no clock, no database, no global state. The same identity
  always produces the same plan, independent of mapping insertion order (FR-002).
* **Total.** Every identity dimension yields a query. A dimension no provider can
  execute becomes an explicitly *unsupported* query carrying a machine-readable
  reason, never a silent drop (FR-004). Declaring is preferred to inventing: a
  fabricated derivation for, say, a phone number would produce results whose
  provenance cannot be justified.
* **Attributable.** Deduplication keeps every originating identity attribute in
  ``origin_refs``, so a query never loses the record of where it came from (FR-003).
* **Backwards compatible.** The legacy single-plan planner is untouched and remains
  reachable through the surface (FR-005).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from acquisition.cc_plan import surt_from_host

__all__ = [
    "COMMON_CRAWL_PROVIDER",
    "RouteProvider",
    "SourceQuery",
    "SourceQuerySet",
    "UnsupportedReason",
    "build_source_query_set",
    "identity_fingerprint",
]


class UnsupportedReason:
    """Machine-readable reasons a route cannot be executed (FR-004)."""

    NO_PROVIDER = "no_provider_for_route"
    NORMALIZATION_FAILED = "normalization_failed"
    VALUE_TOO_SHORT = "value_too_short"


#: Route kinds in stable execution-precedence order. Most specific locator first,
#: then progressively weaker textual matches, then the derived routes that no
#: provider currently serves. Ordinals follow this order, so a plan's execution
#: order never depends on mapping iteration order.
ROUTE_ORDER: tuple[str, ...] = (
    "exact_url",
    "url_prefix",
    "domain",
    "name",
    "alias",
    "historical_name",
    "username_derived",
    "email_derived",
    "phone_derived",
)

_ROUTE_RANK = {kind: rank for rank, kind in enumerate(ROUTE_ORDER)}

#: Identity attribute -> route kinds it can produce. Mirrors the key groups used by
#: ``acquisition.entity_search`` so the surface and the planner cannot drift.
_KEY_ROUTES: dict[str, tuple[str, ...]] = {
    "url": ("exact_url", "url_prefix"),
    "urls": ("exact_url", "url_prefix"),
    "website": ("exact_url", "url_prefix"),
    "uri": ("exact_url", "url_prefix"),
    "domain": ("domain",),
    "host": ("domain",),
    "site": ("domain",),
    "name": ("name",),
    "full_name": ("name",),
    "alias": ("alias",),
    "aliases": ("alias",),
    "organization_alias": ("alias",),
    "historical_name": ("historical_name",),
    "former_name": ("historical_name",),
    "username": ("username_derived",),
    "handle": ("username_derived",),
    "usernames": ("username_derived",),
    "email": ("email_derived",),
    "emails": ("email_derived",),
    "phone": ("phone_derived",),
    "phones": ("phone_derived",),
}

_URL_KEYS = frozenset({"url", "urls", "website", "uri"})
_DOMAIN_KEYS = frozenset({"domain", "host", "site"})

#: Minimum usable length per route family, below which a value cannot form a
#: meaningful query and is reported as too short rather than searched for.
_MIN_LENGTH: dict[str, int] = {
    "name": 2,
    "alias": 2,
    "historical_name": 2,
    "username_derived": 3,
    "email_derived": 3,
    "phone_derived": 3,
}

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class RouteProvider:
    """A registered provider able to execute a set of route kinds.

    Providers are an explicit registry, so adding one later makes a previously
    unsupported route executable without touching the planner (D2).
    """

    name: str
    route_kinds: frozenset[str] = field(default_factory=frozenset)

    def supports(self, route_kind: str) -> bool:
        return route_kind in self.route_kinds


#: The only provider that exists today. Username, email and phone routes are
#: intentionally absent: no provider defines how to query them, so they are
#: declared unsupported instead of being given an invented derivation.
COMMON_CRAWL_PROVIDER = RouteProvider(
    name="common_crawl",
    route_kinds=frozenset(
        {"exact_url", "url_prefix", "domain", "name", "alias", "historical_name"}
    ),
)


@dataclass(frozen=True, slots=True)
class SourceQuery:
    """One executable (or explicitly unsupported) acquisition intent."""

    query_id: str
    ordinal: int
    route_kind: str
    query_value: str
    match_type: str
    surt_prefix: str | None
    provider: str | None
    executable: bool
    unsupported_reason: str | None
    origin_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "ordinal": self.ordinal,
            "route_kind": self.route_kind,
            "query_value": self.query_value,
            "match_type": self.match_type,
            "surt_prefix": self.surt_prefix,
            "provider": self.provider,
            "executable": self.executable,
            "unsupported_reason": self.unsupported_reason,
            "origin_refs": list(self.origin_refs),
        }


@dataclass(frozen=True, slots=True)
class SourceQuerySet:
    """The ordered, deduplicated query set derived for one entity."""

    entity_id: str
    query_set_id: str
    identity_fingerprint: str
    queries: tuple[SourceQuery, ...]

    @property
    def executable(self) -> tuple[SourceQuery, ...]:
        return tuple(query for query in self.queries if query.executable)

    @property
    def unsupported(self) -> tuple[SourceQuery, ...]:
        return tuple(query for query in self.queries if not query.executable)

    @property
    def executable_count(self) -> int:
        return len(self.executable)

    @property
    def unsupported_count(self) -> int:
        return len(self.unsupported)

    @property
    def is_complete(self) -> bool:
        """True when every route in the plan is executable.

        A complete plan means the surface was fully served. A complete *entity*
        also needs this to be true, which is why coverage reporting treats it as a
        first-class fact rather than an implementation detail.
        """
        return not self.unsupported

    def by_kind(self, route_kind: str) -> tuple[SourceQuery, ...]:
        return tuple(query for query in self.queries if query.route_kind == route_kind)

    def unsupported_reasons(self) -> dict[str, str]:
        return {q.route_kind: str(q.unsupported_reason) for q in self.unsupported}

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "query_set_id": self.query_set_id,
            "identity_fingerprint": self.identity_fingerprint,
            "query_count": len(self.queries),
            "executable_count": self.executable_count,
            "unsupported_count": self.unsupported_count,
            "complete": self.is_complete,
            "queries": [query.as_dict() for query in self.queries],
        }


def identity_fingerprint(identifiers: dict[str, str] | tuple[tuple[str, str], ...]) -> str:
    """Canonical hash of an identity mapping.

    Uses the same canonicalization as the ``identity_fingerprint`` column written
    by migration 015 and by the outbox, so a query set and a reconstruction
    request for the same identity agree on identity across subsystems.
    """
    items = identifiers.items() if isinstance(identifiers, dict) else identifiers
    material = json.dumps(
        dict(sorted((str(k), str(v)) for k, v in items)),
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _clean(value: str) -> str:
    """Trim and collapse internal whitespace."""
    return _WHITESPACE.sub(" ", str(value)).strip()


def _normalize_url(value: str) -> str:
    cleaned = _clean(value)
    if not cleaned:
        return ""
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    return cleaned


def _normalize_domain(value: str) -> str:
    cleaned = _clean(value).lower().rstrip("/")
    if "://" in cleaned:
        cleaned = urlsplit(cleaned).hostname or ""
    cleaned = cleaned.split("/")[0].split(":")[0]
    if cleaned.startswith("www."):
        cleaned = cleaned[4:]
    return cleaned.strip(".")


def _normalize_route_value(route_kind: str, raw: str) -> str:
    if route_kind in ("exact_url", "url_prefix"):
        return _normalize_url(raw)
    if route_kind == "domain":
        return _normalize_domain(raw)
    return _clean(raw).lower() if route_kind.endswith("_derived") else _clean(raw)


def _surt_for(route_kind: str, value: str) -> str | None:
    """SURT prefix for host-bearing routes.

    Domain routes carry a bare host, for which ``urlsplit(...).hostname`` is
    ``None`` because a bare host parses as a path. Both forms are therefore
    normalized to a host before SURT is derived.
    """
    if route_kind not in ("exact_url", "url_prefix", "domain") or not value:
        return None
    if route_kind == "domain":
        return surt_from_host(value)
    try:
        host = urlsplit(value).hostname or ""
    except ValueError:
        host = ""
    return surt_from_host(host)


def _match_type_for(route_kind: str) -> str:
    if route_kind == "exact_url":
        return "exact"
    if route_kind in ("url_prefix", "domain"):
        return "domain" if route_kind == "domain" else "prefix"
    return "prefix"


def _query_id(fingerprint: str, route_kind: str, query_value: str) -> str:
    """Content-derived query identity.

    Derived from the identity fingerprint rather than the query set id so that a
    query keeps the same id across re-plans. Frontier entries are keyed by it, so
    stability across runs is what makes the frontier survive (FR-007).
    """
    material = f"{fingerprint}\x00{route_kind}\x00{query_value}"
    return "q-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:56]


def _provider_for(route_kind: str, providers: tuple[RouteProvider, ...]) -> RouteProvider | None:
    for provider in providers:
        if provider.supports(route_kind):
            return provider
    return None


def build_source_query_set(
    *,
    entity_id: str,
    surface: Any,
    providers: tuple[RouteProvider, ...] = (COMMON_CRAWL_PROVIDER,),
) -> SourceQuerySet:
    """Derive the full multi-route query set for one entity search surface.

    Args:
        entity_id: Owning entity; participates in query identity.
        surface: An :class:`acquisition.entity_search.EntitySearchSurface`.
        providers: Registered providers. A route no provider serves becomes an
            explicitly unsupported query rather than being dropped.

    Returns:
        A :class:`SourceQuerySet`. Planning never raises for an unexecutable
        identity; the run fails later with ``no_executable_query`` (AS-008).
    """
    identifiers = dict(surface.identifiers)
    fingerprint = identity_fingerprint(identifiers)

    # (route_kind, query_value) -> {"refs": set[str], "reason": str | None}
    # A route that fails normalization is still emitted, marked unsupported with a
    # reason. Dropping it would be the exact silent discard FR-004 forbids.
    collected: dict[tuple[str, str], dict[str, Any]] = {}

    for key in sorted(identifiers):
        raw = identifiers[key]
        for route_kind in _KEY_ROUTES.get(key, ()):
            value = _normalize_route_value(route_kind, raw)
            entry = collected.setdefault((route_kind, value), {"refs": set(), "reason": None})
            entry["refs"].add(key)
            if not value:
                entry["reason"] = UnsupportedReason.NORMALIZATION_FAILED
                continue
            minimum = _MIN_LENGTH.get(route_kind)
            if minimum is not None and len(value) < minimum:
                entry["reason"] = UnsupportedReason.VALUE_TOO_SHORT

    ordered_keys = sorted(collected, key=lambda item: (_ROUTE_RANK.get(item[0], 99), item[1]))
    queries: list[SourceQuery] = []
    for ordinal, (route_kind, value) in enumerate(ordered_keys):
        entry = collected[(route_kind, value)]
        provider = _provider_for(route_kind, providers)
        # A declared value problem is the more specific and actionable reason than
        # a missing provider, so it wins when both apply.
        reason = entry["reason"] or (
            None if provider else UnsupportedReason.NO_PROVIDER
        )
        queries.append(
            SourceQuery(
                query_id=_query_id(fingerprint, route_kind, value),
                ordinal=ordinal,
                route_kind=route_kind,
                query_value=value,
                match_type=_match_type_for(route_kind),
                surt_prefix=_surt_for(route_kind, value),
                provider=provider.name if provider and reason is None else None,
                executable=provider is not None and reason is None,
                unsupported_reason=reason,
                origin_refs=tuple(sorted(entry["refs"])),
            )
        )

    return SourceQuerySet(
        entity_id=entity_id,
        query_set_id="qs-" + hashlib.sha256(
            f"{entity_id}\x00{fingerprint}".encode()
        ).hexdigest()[:56],
        identity_fingerprint=fingerprint,
        queries=tuple(queries),
    )

