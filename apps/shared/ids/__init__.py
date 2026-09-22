"""Globally-unique identifiers + multi-region partitioning (T119)."""

from __future__ import annotations

from .gen import (
    _DEFAULT_REGION,
    global_id,
    host_partition,
    normalize_region,
    partition_of,
    region_group,
    ulid,
)

__all__ = [
    "_DEFAULT_REGION",
    "global_id",
    "host_partition",
    "normalize_region",
    "partition_of",
    "region_group",
    "ulid",
]