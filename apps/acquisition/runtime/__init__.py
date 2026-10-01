"""Runtimes: concrete implementations of the ``AcquisitionWorker`` contract.

Directive §13 requires a source to name an explicit ``worker_ref`` **and**
``runtime_ref``, and forbids inferring the worker from capabilities - a BBOT task
must not reach a generic HTTP worker merely because both speak HTTP. So the
routing key is the pair, and a runtime is what makes the second half real.

**The contract is three methods, and the middle one is the point.**

``capabilities()``
    what this runtime can do. Used to *check* compatibility after the runtime has
    already been resolved by name, never to choose it. §57 requires resolution
    first and validation second; a capability-first design is the forbidden
    ``infer worker from capabilities`` by another spelling.

``estimate()``
    what one run would cost, before it starts. §66 makes acquisition budgeted:
    a scheduler that cannot ask "how much" cannot decide how much, and a backlog
    that can only be met by running everything is a backlog that grows.

``acquire()``
    produce artifacts. Returns an **async iterator**, never a list. §5 and §36
    both require that a run which can be unbounded is bounded while it streams:
    Airbyte's ``read`` against a large source, a SpiderFoot module set, a BBOT
    enumeration that discovers targets as it runs. A runtime that returns a
    completed list has already spent the memory the limit was supposed to bound.

**Why ``runtime_ref`` is a string and not a class.** §14 makes ``source_id``
content-addressed and ``runtime_ref`` the specific executable implementation. A
string in the source definition is what makes a run's provenance reportable
without importing the code that performed it, and what lets two definitions share
one runtime while differing in every other respect.

**What no runtime here does.** None of them parse, type, classify, resolve or
score. Each one's whole job ends at
:class:`~domain.acquisition_artifact.AcquisitionArtifact`; everything semantic
happens downstream of the sink. That boundary is §3, and it is enforced by the
return type rather than by convention.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from domain.acquisition_artifact import AcquisitionArtifact

#: Reason codes a runtime may refuse with. §73 requires failures to be
#: classified, and a runtime raising a bare exception is the classification the
#: caller has to invent.
RUNTIME_UNHEALTHY = "runtime_unhealthy"
RUNTIME_HTTP_ERROR = "runtime_http_error"
RUNTIME_PROTOCOL_INVALID = "runtime_protocol_invalid"
RUNTIME_TIMEOUT = "runtime_timeout"
RUNTIME_RESOURCE_LIMIT = "resource_limit_exceeded"
RUNTIME_NOT_FOUND = "runtime_not_found"


class RuntimeError_(RuntimeError):
    """A runtime refused or failed. Carries a §73 classification code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ResourceClass:
    """One runtime's share of the budget (§66, §143).

    Named and frozen rather than three bare ints, because ``ResourceLimits`` in
    the platform is shared vocabulary and a runtime that invents its own field
    names cannot be compared against another runtime's - and §143 is precisely a
    demand that they *not* share one default.
    """

    name: str
    max_runtime_seconds: float
    max_output_bytes: int
    max_records: int | None = None
    max_parallel: int = 1


@dataclass(frozen=True)
class CostEstimate:
    """What a run is expected to cost (§66).

    Estimates, not guarantees: the scheduler uses them to budget, and the run
    manifest reports what actually happened. Presenting an estimate as a fact
    would make backpressure decisions on numbers nobody measured.
    """

    expected_artifacts: int
    expected_bytes: int
    expected_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_artifacts": self.expected_artifacts,
            "expected_bytes": self.expected_bytes,
            "expected_seconds": self.expected_seconds,
        }


@runtime_checkable
class AcquisitionWorker(Protocol):
    """The contract every runtime satisfies. Resolution key, not a capability set."""

    #: §14's ``runtime_ref``. The stable, reportable identity of this
    #: implementation - it appears in the run manifest and the event's producer
    #: fields, so it must not change when the class is renamed.
    runtime_ref: str

    #: §14's ``execution_class``. A deployment-level grouping, coarser than
    #: ``runtime_ref``: three HTTP-ish runtimes may share ``api/http`` while each
    #: keeping its own ``runtime_ref``.
    execution_class: str

    def capabilities(self) -> list[str]: ...

    def estimate(self, task: dict[str, Any]) -> CostEstimate: ...

    def acquire(self, task: dict[str, Any]) -> AsyncIterator[AcquisitionArtifact]: ...

    async def aclose(self) -> None: ...


@dataclass
class RuntimeHealth:
    """§17's readiness verdict, and §103's requirement that it be specific.

    ``ready`` alone is not enough. The reason a runtime is *not* ready is the
    diagnostic that decides whether to retry, reconfigure or stop - and SearXNG's
    canonical failure, JSON output not declared, produces a 403 that is otherwise
    indistinguishable from a forbidden request.
    """

    ready: bool
    detail: str = ""
    checks: dict[str, Any] = field(default_factory=dict)

    def require(self) -> None:
        if not self.ready:
            code = str(self.checks.get("code") or RUNTIME_UNHEALTHY)
            raise RuntimeError_(code, self.detail or f"{self.runtime_ref} is not ready")

    runtime_ref: str = ""


__all__ = [
    "AcquisitionWorker",
    "CostEstimate",
    "RUNTIME_HTTP_ERROR",
    "RUNTIME_NOT_FOUND",
    "RUNTIME_PROTOCOL_INVALID",
    "RUNTIME_RESOURCE_LIMIT",
    "RUNTIME_TIMEOUT",
    "RUNTIME_UNHEALTHY",
    "ResourceClass",
    "RuntimeError_",
    "RuntimeHealth",
]
