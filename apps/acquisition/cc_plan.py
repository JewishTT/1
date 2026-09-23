"""CC query planner (L1, CC-TEMPORALITY v1): entity identity -> CC index plan.

Deterministic, pure, allocation-light: no network, no global state, same input
always yields the same plan (Constitution I-11). Priority of identity keys is
fixed: ``url`` > ``domain``/``host``/``site`` > ``name``/``full_name``/``account``.

SURT normalization (Sort-friendly URI Reordering Tuple, e.g.
``http://com,example,``) is implemented here without external libraries.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from typing import Mapping

__all__ = ["CcQueryPlan", "build_cc_plan", "surt_from_host"]


@dataclass(frozen=True)
class CcQueryPlan:
    """Atomic plan for a CC index query (L0 consumes primitives, not this)."""

    entity_id: str
    kind: str  # "domain" | "url" | "name"
    url_query: str
    match_type: str  # "domain" | "prefix"
    surt_prefix: str | None
    limit: int


_PRIORITY: tuple[tuple[str, ...], ...] = (
    ("url",),
    ("domain", "host", "site"),
    ("name", "full_name", "account"),
)


def surt_from_host(host: str) -> str | None:
    """Deterministic SURT host prefix, e.g. ``WWW.Example.com.`` -> ``http://com,example,``.

    No libraries, no allocations beyond the output string. Returns None for an
    empty host.
    """
    cleaned = host.strip().lower().rstrip(".")
    if not cleaned:
        return None
    if cleaned.startswith("www."):
        cleaned = cleaned[4:]
    if not cleaned:
        return None
    parts = cleaned.split(".")
    # host may carry a port; the port never belongs to the SURT name
    if parts and ":" in parts[-1]:
        parts[-1] = parts[-1].split(":", 1)[0]
    parts = [p for p in parts if p]
    if not parts:
        return None
    return "http://" + ",".join(reversed(parts)) + ","


def _host_of_url(url: str) -> str | None:
    try:
        host = urlsplit(url.strip()).hostname
    except ValueError:
        return None
    return host or None


def _first_value(identity: Mapping[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = identity.get(key)
        if value is None:
            continue
        value = value.strip()
        if value:
            return value
    return None


def build_cc_plan(
    entity_id: str, canonical_identity: Mapping[str, str]
) -> CcQueryPlan | None:
    """Deterministic CC query plan from a canonical identity, or None.

    Priority (fixed): ``url`` -> prefix match; ``domain``/``host``/``site`` ->
    domain match with SURT normalization; ``name``/``full_name``/``account``
    -> name query (match_type="prefix", no SURT). Empty identity -> None.
    """
    if not canonical_identity:
        return None

    url_value = _first_value(canonical_identity, _PRIORITY[0])
    if url_value is not None:
        host = _host_of_url(url_value)
        return CcQueryPlan(
            entity_id=entity_id,
            kind="url",
            url_query=url_value,
            match_type="prefix",
            surt_prefix=surt_from_host(host) if host else None,
            limit=50,
        )

    domain_value = _first_value(canonical_identity, _PRIORITY[1])
    if domain_value is not None:
        host = domain_value.rstrip("/")
        return CcQueryPlan(
            entity_id=entity_id,
            kind="domain",
            url_query=host,
            match_type="domain",
            surt_prefix=surt_from_host(host),
            limit=50,
        )

    name_value = _first_value(canonical_identity, _PRIORITY[2])
    if name_value is not None:
        return CcQueryPlan(
            entity_id=entity_id,
            kind="name",
            url_query=name_value,
            match_type="prefix",
            surt_prefix=None,
            limit=50,
        )

    return None
