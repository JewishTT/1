"""``AcquisitionArtifact``: what a runtime produced, before the platform decides anything.

Directive §5. Five runtimes with five paradigms - an HTTP search backend, a
line-delimited connector protocol, three external tools - all reduce to one
frozen value, and this module is where that reduction happens.

**Why the reduction is at the artifact and not further downstream.** A runtime's
native output is not a capture and is not an observation. A SearXNG response is
a JSON document; an Airbyte ``read`` is a stream of protocol messages carrying
control state alongside evidence; a BBOT scan is an event stream whose events
reference their parents. Each has its own shape, and the temptation is to let the
lowest common denominator decide what an observation is. That is how a connector's
``STATE`` checkpoint and its ``RECORD`` evidence end up in the same bucket.

So an artifact is the *whole* of what a runtime emitted for one addressable
thing, and it carries its own provenance (``producer``, ``producer_version``,
``transport``) rather than having it inferred from ``runtime_ref``. §97 forbids
inference from incidental structure, and a producer is not incidental - it is
attribution.

**Streaming is the contract, not an optimisation.** §5 requires
``async for artifact in worker.run(task)`` rather than a completed run handed over
whole, because three of the five runtimes are unbounded in principle: an Airbyte
``read`` against a large source, a SpiderFoot scan with a long module set, a BBOT
subdomain enumeration that discovers targets as it goes. A runtime that buffers
its entire run before returning cannot honour a resource limit (§143, §36), and
the limit is what stops one source from consuming the whole budget. Hence
:func:`stream_artifact`, which yields as the producer yields, and
:class:`ArtifactBudget`, which counts what has passed so the sink can stop a run
that outgrew its class rather than discovering the overflow in memory.

**What is deliberately absent.** No ``observation_id``, no ``capture_id``, no
``event_id``: those are the platform's to mint, from
:mod:`domain.observation_identity` and :class:`domain.capture.Capture`, and a
runtime that could address its own output would make the address a fact about the
tool rather than about the evidence. Also absent is any type, confidence or
entity - §3 forbids the shortcut from tool output to entity, and the shortest way
to honour that is for the artifact never to have carried one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from domain.observation_identity import ObservationIdentityError

ARTIFACT_SCHEMA_V1: Final = "acquisition-artifact/v1"

#: Named refusals. A runtime emitting an artifact with none of these set is
#: malformed, and the codes exist so the sink can say which field was missing
#: rather than admitting an unaddressable blob.
REFUSAL_BODY_MISSING: Final = "artifact_body_missing"
REFUSAL_LOCATOR_MISSING: Final = "artifact_locator_missing"
REFUSAL_PRODUCER_MISSING: Final = "artifact_producer_missing"


class ArtifactContractError(ValueError):
    """An artifact is missing a component the platform needs to address it."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _require(code: str, name: str, value: Any) -> Any:
    if value is None:
        raise ArtifactContractError(code, f"{name} is required on an acquisition artifact")
    if isinstance(value, str) and not value.strip():
        raise ArtifactContractError(code, f"{name} is blank on an acquisition artifact")
    return value


@dataclass(frozen=True)
class AcquisitionArtifact:
    """One addressable thing a runtime produced (§5).

    Frozen because an artifact is evidence on arrival. A runtime that wants to
    revise what it emitted emits a new artifact, which is a new capture and a new
    observation - the same rule §176 applies to a changed SearXNG page. Mutating
    one in place would leave an address pointing at bytes that were never fetched.
    """

    task_id: str
    source_id: str
    worker_ref: str

    target_uri: str
    locator: str

    body: bytes
    content_type: str | None

    fetched_at: datetime
    transport: str

    producer: str
    producer_version: str

    metadata: Mapping[str, Any] = field(default_factory=dict)

    #: Which *capture* this record belongs to, when one response yields many
    #: records. §6 draws the line: a capture is what physically came back - one
    #: SearXNG page, one Airbyte run - and a record is an addressable thing inside
    #: it. §20 is explicit: each response page becomes one capture, and its
    #: results become observations of that capture.
    #:
    #: The distinction is load-bearing rather than cosmetic, because
    #: :class:`domain.capture.Capture` folds ``locator`` into its identity
    #: material. Passing a per-record locator there gave one fetch as many
    #: captures, so a page carrying two hundred results was stored once and
    #: registered two hundred times - the §98 "pages fetched, only some persisted"
    #: bug wearing the opposite sign.
    #:
    #: ``None`` means the artifact is the whole capture and its own ``locator``
    #: serves, which is the single-record case every other runtime produces. It is
    #: declared after the required fields because a defaulted field cannot precede
    #: a non-defaulted one, and making it required would force the single-record
    #: case to name twice what it already has.
    capture_locator: str | None = None

    #: §5's schema marker, carried so a stored artifact can be read by the code
    #: that understands it. Bumping it is a real change to what a consumer may
    #: rely on, which is the point of having it on the value rather than in a
    #: migration note.
    schema: str = ARTIFACT_SCHEMA_V1

    def __post_init__(self) -> None:
        _require(REFUSAL_LOCATOR_MISSING, "locator", self.locator)
        _require(REFUSAL_PRODUCER_MISSING, "producer", self.producer)
        _require(REFUSAL_PRODUCER_MISSING, "producer_version", self.producer_version)
        if self.body is None:
            raise ArtifactContractError(REFUSAL_BODY_MISSING, "body is required")
        if not isinstance(self.body, bytes):
            raise ArtifactContractError(
                REFUSAL_BODY_MISSING,
                f"body must be raw bytes; a runtime decoded it into {type(self.body).__name__}, "
                f"and decoding is the parser's job (§3), not the transport's",
            )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @property
    def byte_length(self) -> int:
        return len(self.body)

    def effective_capture_locator(self) -> str:
        """The locator the *capture* is addressed by.

        A record inside a shared capture inherits the capture's locator, so every
        record of one response resolves to the same durable object; a standalone
        artifact is its own capture and uses its own.
        """
        return self.capture_locator or self.locator

    def record_digest(self) -> str:
        """Digest of *this artifact's* bytes, the record-level identity input (§61).

        The capture's digest and this are usually the same number, and where they
        are not, that is information: a record slice re-addressed from a stored
        capture is a different observation from the capture itself, and §34's
        reason - identical JSON in two streams is two occurrences - depends on the
        distinction surviving.
        """
        import hashlib

        return hashlib.sha256(self.body).hexdigest()

    def observation_identity(self, *, tenant_id: str, capture_id: str) -> str:
        """Address this artifact as one record inside a capture (§11).

        Delegates to the single writer rather than cutting a digest here; a second
        addresser in a second module is how the two would drift.
        """
        from domain.observation_identity import observation_id_for

        return observation_id_for(
            tenant_id=tenant_id,
            capture_id=capture_id,
            locator=self.locator,
            record_digest=self.record_digest(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Metadata view. The body is deliberately absent (§69)."""
        return {
            "task_id": self.task_id,
            "source_id": self.source_id,
            "worker_ref": self.worker_ref,
            "target_uri": self.target_uri,
            "locator": self.locator,
            "capture_locator": self.effective_capture_locator(),
            "content_type": self.content_type,
            "byte_length": self.byte_length,
            "content_digest": self.record_digest(),
            "fetched_at": self.fetched_at.isoformat(),
            "transport": self.transport,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "schema": self.schema,
            "metadata": dict(self.metadata),
        }


class ArtifactBudget:
    """Boundedness for one run's artifact stream (§36, §66, §143).

    Counts what has *passed through*, which is what a resource limit can honestly
    speak about. A limit checked only after a runtime has finished tells you the
    run was too large after the memory was already spent; checking here means the
    sink can stop consuming, and the runtime's producer is then free to be
    abandoned rather than killed mid-write.

    The counters are public because the run manifest (§71) reports them, and a
    limit that is enforced but never reported is indistinguishable from a run
    that stopped for no reason.
    """

    def __init__(
        self,
        *,
        max_artifacts: int | None = None,
        max_bytes: int | None = None,
        max_runtime_seconds: float | None = None,
    ) -> None:
        self.max_artifacts = max_artifacts
        self.max_bytes = max_bytes
        self.max_runtime_seconds = max_runtime_seconds

        self.artifacts = 0
        self.bytes = 0
        self.elapsed: float | None = None

    def admit(self, artifact: AcquisitionArtifact) -> None:
        """Account for one artifact, or refuse it by name.

        Deliberately refuses rather than truncating. A truncated artifact is a
        capture whose ``content_digest`` no longer describes what the source
        returned, and §61 requires the digest to be of the stored bytes - so the
        only honest options are the whole artifact or none of it.
        """
        if self.max_artifacts is not None and self.artifacts >= self.max_artifacts:
            raise ArtifactContractError(
                "resource_limit_exceeded",
                f"run produced more than {self.max_artifacts} artifacts; "
                f"partial run state is retained for replay (§91)",
            )
        if self.max_bytes is not None and self.bytes + artifact.byte_length > self.max_bytes:
            raise ArtifactContractError(
                "resource_limit_exceeded",
                f"run exceeded {self.max_bytes} bytes at artifact #{self.artifacts + 1} "
                f"({artifact.byte_length} more); partial state retained (§91)",
            )
        self.artifacts += 1
        self.bytes += artifact.byte_length

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": self.artifacts,
            "bytes": self.bytes,
            "elapsed_seconds": self.elapsed,
            "max_artifacts": self.max_artifacts,
            "max_bytes": self.max_bytes,
            "max_runtime_seconds": self.max_runtime_seconds,
        }


async def stream_artifact(
    producer: AsyncIterator[AcquisitionArtifact], *, budget: ArtifactBudget | None = None
) -> AsyncIterator[AcquisitionArtifact]:
    """Admit artifacts from a runtime as it produces them (§5, §36).

    The generator exists to be the *only* place a runtime's output enters the
    platform, so that "did the budget apply?" has one answer. Passing ``budget``
    is optional because a fixture needs none; a live run should always pass one.
    """
    async for artifact in producer:
        if budget is not None:
            budget.admit(artifact)
        yield artifact


__all__ = [
    "ARTIFACT_SCHEMA_V1",
    "AcquisitionArtifact",
    "ArtifactBudget",
    "ArtifactContractError",
    "ObservationIdentityError",
    "REFUSAL_BODY_MISSING",
    "REFUSAL_LOCATOR_MISSING",
    "REFUSAL_PRODUCER_MISSING",
    "stream_artifact",
]
