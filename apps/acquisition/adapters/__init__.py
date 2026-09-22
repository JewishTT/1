"""Collection Fabric adapters (T089, T096-T100, R-09).

External engines (Heritrix, Browsertrix, StormCrawler, Nutch, Crawlee/Scrapy,
Common Crawl index, datasets, feeds, APIs) plug into Cognitive exclusively via
:class:`~adapters.registry.SourceRegistration` + capability-intersection
selection. Adapters emit bytes + metadata only; they MUST NOT write to stores
or emit events directly — everything converges on the Observation Gate.
"""

from __future__ import annotations

from .registry import (
    EXECUTION_CLASSES,
    KNOWN_CAPABILITIES,
    REGISTRY,
    CapabilityGap,
    SourceRegistration,
    register,
)

__all__ = [
    "CapabilityGap",
    "KNOWN_CAPABILITIES",
    "EXECUTION_CLASSES",
    "REGISTRY",
    "SourceRegistration",
    "register",
]