"""Globally-unique region-prefixed identifiers + multi-region partition (T119).

Frontier items are partitioned across regions (``partition`` = host region) so
dispatchers can shed load independently per region. Every entity id an
observation produces is prefixed ``<kind>.<region>.<ulid>`` — unique across
the whole fabric without a central counter.
"""

from __future__ import annotations

import secrets
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_BASE = len(_CROCKFORD)
_DEFAULT_REGION = "global"


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        value, rem = divmod(value, _BASE)
        chars.append(_CROCKFORD[rem])
    return "".join(reversed(chars))


def ulid() -> str:
    """Crockford base32 ULID: 48-bit millisecond timestamp + 80-bit entropy."""
    ms = int(time.time() * 1000)
    entropy = int.from_bytes(secrets.token_bytes(10), "big")
    return _encode(ms, 10) + _encode(entropy, 16)


def global_id(kind: str, region: str = _DEFAULT_REGION) -> str:
    """Globally-unique id for an observation-family entity.

    ``kind`` namespaces the id across factories (``obs``, ``frontier``,
    ``entity``, ``finding``, ``event``); ``region`` is a partition scope.
    """
    cleaned = region.lower().strip().replace("_", "-") or _DEFAULT_REGION
    return f"{kind}.{cleaned}.{ulid()}"


def normalize_region(region: str) -> str:
    return (region or _DEFAULT_REGION).lower().strip().replace("_", "-") or _DEFAULT_REGION


def partition_of(
    uri: str,
    *,
    region_map: dict[str, str] | None = None,
) -> str:
    """Partition name for ``uri``: the region its host belongs to.

    Suffix keys taking priority (``.ru`` over ``.example.com`` is caller's
    ordering concern); defaults to ``global``.
    """
    host = _host(uri)
    for suffix, region in (region_map or {}).items():
        if suffix.startswith(".") and host.endswith(suffix):
            return normalize_region(region)
        if host == suffix or host.endswith("." + suffix):
            return normalize_region(region)
    return _DEFAULT_REGION


def host_partition(uri: str, region_map: dict[str, str] | None = None) -> dict[str, str]:
    """``{"host": ..., "region": ..., "partition": ...}`` for a frontier item."""
    host = _host(uri)
    region = partition_of(host, region_map=region_map)
    return {"host": host, "region": region, "partition": region}


def region_group(partitions: list[str], *, shards: int = 1) -> str:
    """Coarse region group for parallel frontier shards (T119)."""
    p = [normalize_region(x) for x in partitions if x]
    if not p:
        return _DEFAULT_REGION
    if shards <= 1:
        return _DEFAULT_REGION
    total = sum(ord(c) for c in "".join(sorted(p)))
    return p[total % shards]


def _host(uri: str) -> str:
    rest = (uri or "").split("://", 1)[-1]
    rest = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if ":" in rest and not rest.endswith("]"):
        rest = rest.rsplit(":", 1)[0]
    return rest.lower()