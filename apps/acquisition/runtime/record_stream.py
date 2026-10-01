"""One reader for line-delimited record streams, shared by Airbyte and BBOT.

The unification, stated precisely: **Airbyte's ``RECORD`` stream and BBOT's event
stream are the same shape.** Both are NDJSON on stdout, one addressable record per
line, both multiplexed, both interleaved with non-record messages, and both needing
a locator that survives interleaving. Two implementations of that reader are two
places for the §98 "only the last page survived" class of bug to live.

What differs is *what a line means*, and that belongs to the adapter, not the
reader:

===============  ==========================  ==================================
                 Airbyte ``RECORD``          BBOT event
===============  ==========================  ==================================
identity         stream + emitted_at        BBOT ``uuid`` (donor's own)
locator          ``airbyte:<ns>/<stream>:<n>``  ``bbot:event:<n>``
provenance       image digest, connector     ``parent``, ``parent_uuid``,
                                            ``discovery_path``, ``parent_chain``,
                                            ``module``, ``module_sequence``
interpretation   none - it is a table row     a **derivation context**, not a
                                            RelationClaim (§49)
===============  ==========================  ==================================

That last row is the reason this is worth unifying *and* worth separating: the
two streams are structurally identical and semantically opposite. Airbyte rows are
records with no opinion about how they relate. A BBOT event names its parent, and
the temptation is to read that as "A is a parent of B" - which §49 and §160
forbid. The reader handles framing; only the BBOT adapter sees provenance, and it
carries it as :class:`~domain.acquisition_artifact.AcquisitionArtifact` metadata
that nothing downstream is allowed to read as a relation.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from runtime import RuntimeError_


@dataclass(frozen=True)
class StreamRecord:
    """One line that was decoded into a record."""

    index: int
    data: Any
    raw: str
    extra: dict[str, Any] = field(default_factory=dict)


class RecordStreamAdapter(Protocol):
    """What a family-specific adapter must say about its records."""

    locator: str

    def accepts(self, message: dict[str, Any]) -> bool:
        """Is this line a record for this family?"""
        ...

    def index_fields(self, message: dict[str, Any]) -> dict[str, Any]:
        """Family-specific provenance to carry alongside the record."""
        ...


async def read_record_stream(
    lines: AsyncIterator[str],
    adapter: RecordStreamAdapter,
    *,
    max_record_bytes: int = 1024 * 1024,
) -> AsyncIterator[StreamRecord]:
    """Decode an NDJSON stream into records, framing left to the adapter.

    Streams as it goes and never buffers the run: §36 forbids reading a connector's
    entire output into memory, and BBOT's event stream on a real target is
    unbounded. A malformed line is **skipped and counted** rather than fatal, because
    §32 distinguishes a protocol failure from one bad line - refusing the whole run
    over a single corrupt event discards the records that were fine.
    """
    index = 0
    async for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            # Retained on the adapter's quarantine list by the caller, which knows
            # where to put it; the reader only declines to decode it.
            index += 1
            continue
        if not isinstance(message, dict):
            index += 1
            continue
        if not adapter.accepts(message):
            index += 1
            continue
        encoded = len(line.encode("utf-8"))
        if encoded > max_record_bytes:
            raise RuntimeError_(
                "resource_limit_exceeded",
                f"record at index {index} is {encoded} bytes, over the {max_record_bytes} cap",
            )
        yield StreamRecord(
            index=index,
            data=message.get("data", message.get("record", message)),
            raw=line,
            extra=adapter.index_fields(message),
        )
        index += 1
