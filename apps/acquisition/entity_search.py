"""Deterministic entity search planning surface.

The surface joins the existing web-query derivation and Common Crawl plan
without performing I/O. Inputs are canonicalized before either planner sees
them, so equivalent mappings produce byte-equivalent output regardless of
mapping insertion order.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from acquisition.cc_plan import CcQueryPlan, build_cc_plan
from websearch.contracts import SearchQuery
from websearch.queries import entity_identifiers_to_queries

__all__ = ["EntitySearchSurface", "build_entity_search_surface"]


@dataclass(frozen=True, slots=True)
class EntitySearchSurface:
    """Immutable, provider-neutral plan for searching one entity.

    ``queries`` are generic web-search queries and ``cc_plan`` is the optional
    Common Crawl specialization. Both are planning artifacts; execution remains
    behind the injected provider/network boundaries.
    """

    entity_id: str
    identifiers: tuple[tuple[str, str], ...]
    queries: tuple[SearchQuery, ...]
    cc_plan: CcQueryPlan | None
    exact_urls: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()
    registered_domains: tuple[str, ...] = ()
    url_prefixes: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    usernames: tuple[str, ...] = ()
    emails: tuple[str, ...] = ()
    phones: tuple[str, ...] = ()
    organization_aliases: tuple[str, ...] = ()
    historical_names: tuple[str, ...] = ()
    source_constraints: tuple[str, ...] = ()
    crawl_partitions: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        """Return whether at least one search route can be executed."""
        return bool(self.queries or self.cc_plan)

    def as_dict(self) -> dict[str, Any]:
        """Return a stable, JSON-serializable planning payload."""
        cc_plan = self.cc_plan
        payload = {
            "entity_id": self.entity_id,
            "identifiers": dict(self.identifiers),
            "queries": [query.as_dict() for query in self.queries],
            "cc_plan": None if cc_plan is None else {
                "kind": cc_plan.kind, "url_query": cc_plan.url_query,
                "match_type": cc_plan.match_type, "surt_prefix": cc_plan.surt_prefix, "limit": cc_plan.limit,
            },
        }
        if not self:
            return payload
        payload.update({
            "exact_urls": list(self.exact_urls), "hosts": list(self.hosts),
            "registered_domains": list(self.registered_domains), "url_prefixes": list(self.url_prefixes),
            "names": list(self.names), "aliases": list(self.aliases), "usernames": list(self.usernames),
            "emails": list(self.emails), "phones": list(self.phones), "organization_aliases": list(self.organization_aliases),
            "historical_names": list(self.historical_names), "source_constraints": list(self.source_constraints),
            "crawl_partitions": list(self.crawl_partitions),
        })
        return payload


def _canonical_identifiers(
    canonical_identity: Mapping[str, object],
) -> dict[str, str]:
    """Copy and sort identifiers so mapping order cannot affect the surface."""
    return {
        str(key).strip(): str(value).strip()
        for key, value in sorted(
            canonical_identity.items(), key=lambda item: str(item[0]).strip()
        )
        if str(key).strip() and str(value).strip()
    }


def build_entity_search_surface(
    entity_id: str,
    canonical_identity: Mapping[str, object],
    *,
    max_queries: int = 12,
) -> EntitySearchSurface:
    """Build a deterministic web + Common Crawl search surface for an entity.

    The returned value is always inspectable, including for an unsupported or
    empty identity. In that case it has no queries or CC plan and is falsy.
    """
    identifiers = _canonical_identifiers(canonical_identity)
    queries = tuple(entity_identifiers_to_queries(identifiers, max_queries=max_queries))
    cc_plan = build_cc_plan(entity_id, identifiers)
    urls = tuple(v for k, v in identifiers.items() if k in {"url", "urls", "website", "uri"} and v.startswith(("http://", "https://")))
    hosts = []
    for value in urls:
        try:
            host = (urlsplit(value).hostname or "").lower()
        except ValueError:
            host = ""
        if host and host not in hosts:
            hosts.append(host)
    for key in ("domain", "host", "site"):
        value = identifiers.get(key, "").lower().strip().removeprefix("www.")
        if value and value not in hosts:
            hosts.append(value)
    names = tuple(v for k, v in identifiers.items() if k in {"name", "full_name"})
    aliases = tuple(v for k, v in identifiers.items() if k in {"alias", "aliases", "organization_alias"})
    usernames = tuple(v for k, v in identifiers.items() if k in {"username", "handle", "usernames"})
    emails = tuple(v for k, v in identifiers.items() if k in {"email", "emails"})
    phones = tuple(v for k, v in identifiers.items() if k in {"phone", "phones"})
    historical = tuple(v for k, v in identifiers.items() if k in {"historical_name", "former_name"})
    constraints = tuple(sorted(identifiers.get(k, "") for k in ("country", "locale", "language", "source") if identifiers.get(k)))
    return EntitySearchSurface(
        entity_id=entity_id, identifiers=tuple(identifiers.items()), queries=queries, cc_plan=cc_plan,
        exact_urls=tuple(sorted(set(urls))), hosts=tuple(sorted(set(hosts))),
        registered_domains=tuple(sorted(set(hosts))), url_prefixes=tuple(sorted(set(urls))),
        names=tuple(sorted(set(names))), aliases=tuple(sorted(set(aliases))),
        usernames=tuple(sorted(set(usernames))), emails=tuple(sorted(set(emails))),
        phones=tuple(sorted(set(phones))), organization_aliases=tuple(sorted(set(aliases))),
        historical_names=tuple(sorted(set(historical))), source_constraints=constraints,
        crawl_partitions=("common_crawl",) if cc_plan is not None or queries else (),
    )
