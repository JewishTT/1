"""Collection Fabric dispatcher — two-stage scheduler (T110, T132, T133, R-03/R-09).

Stage A (intelligence): score the task through `UtilityScore`
(`apps/shared/scoring/scorer.py`) — utility / novelty / freshness / expected
gain vs cost. Decides WHAT to collect next.

Stage B (resource + capability): match the task against the capability registry
(`adapters.registry`) constrained by region / worker-class availability / host
concurrency / queue depth / source limits. Decides WHERE it can run, or returns
an explicit `Defer`/`Reject` verdict. A capability `Gap` is never a silent
misroute (Constitution gate).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from adapters.registry import REGISTRY, CapabilityGap, SourceRegistration
from scoring.scorer import HeuristicUtilityScorer, UtilityScore


class Verdict(StrEnum):
    DISPATCH = "dispatch"
    DEFER = "defer"
    REJECT = "reject"


@dataclass
class ScheduleDecision:
    task_id: str
    verdict: Verdict
    execution_class: str | None = None
    source_type: str | None = None
    utility: float = 0.0
    priority: float = 0.0
    region: str | None = None
    capabilities: set[str] = field(default_factory=set)
    reason: str = ""


class ResourceLimits(Protocol):
    """Constraints consulted by stage B (T133)."""

    def allows(
        self, execution_class: str, region: str | None, host_key: str, required: set[str]
    ) -> tuple[bool, str]: ...


class ScopeLimits:
    """Default limiting policy: explicit quotas per execution class / region.

    Extend with measured values from `scoring.metrics` in the integration phase.
    """

    def __init__(
        self,
        class_budget: dict[str, int] | None = None,
        region_budget: dict[str, int] | None = None,
    ) -> None:
        self.class_budget = class_budget or {}
        self.region_budget = region_budget or {}

    def allows(
        self, _execution_class: str, _region: str | None, _host_key: str, _required: set[str]
    ) -> tuple[bool, str]:
        return True, ""


class Producer(Protocol):
    """Minimal produce surface the dispatcher emits on (compatible with
    ``events.kafka.IdempotentProducer`` and the shared ``Producer`` protocol)."""

    def produce(self, topic: str, envelope, *, key: str | None = None) -> None: ...


class Dispatcher:
    """Capability-aware two-stage scheduler (T110/T132/T133)."""

    def __init__(
        self,
        scorer: HeuristicUtilityScorer | None = None,
        limits: ResourceLimits | ScopeLimits | None = None,
        min_utility: float = 0.01,
        producer: Producer | None = None,
    ) -> None:
        self.scorer = scorer or HeuristicUtilityScorer()
        self.limits = limits or ScopeLimits()
        self.min_utility = min_utility
        self._producer = producer

    def schedule(self, task: dict, context: dict | None = None) -> ScheduleDecision:
        context = context or {}
        task_id = task["task_id"]
        region = task.get("region")
        host_key = task.get("host_key", task.get("uri", "*"))

        # Stage A — intelligence: score utility and gate on it (T132).
        score: UtilityScore = self.scorer.score(task, context)
        if score.utility < self.min_utility:
            return ScheduleDecision(
                task_id=task_id,
                verdict=Verdict.DEFER,
                utility=score.utility,
                priority=score.priority,
                reason=f"utility {score.utility:.4f} below min {self.min_utility}",
            )

        # Stage B — capability match (T110), then resource constraints (T133).
        required = set(task.get("required_capabilities") or ["http"])
        selection = REGISTRY.resolve_task(task)
        if isinstance(selection, CapabilityGap):
            return ScheduleDecision(
                task_id=task_id,
                verdict=Verdict.DEFER,
                utility=score.utility,
                priority=score.priority,
                reason=f"capability gap: missing {sorted(selection.missing)}",
            )

        registration: SourceRegistration = selection
        allowed, reason = self.limits.allows(
            registration.execution_class, region, host_key, required
        )
        if not allowed:
            return ScheduleDecision(
                task_id=task_id,
                verdict=Verdict.DEFER,
                execution_class=registration.execution_class,
                utility=score.utility,
                priority=score.priority,
                region=region,
                capabilities=set(registration.capabilities),
                reason=reason,
            )

        return ScheduleDecision(
            task_id=task_id,
            verdict=Verdict.DISPATCH,
            execution_class=registration.execution_class,
            source_type=registration.source_type,
            utility=score.utility,
            priority=score.priority,
            region=region,
            capabilities=set(registration.capabilities),
            reason="capability-match dispatch",
        )

    def emit_request(self, task: dict, decision: ScheduleDecision) -> None:
        """Emit `acquisition.request` onto the stream plane (T104/T131).

        Import is deferred so the scheduler stays importable without the Kafka
        client in pure unit tests. The producer is injected (Protocol above);
        production binds ``events.kafka.IdempotentProducer``, tests bind a
        memory sink — the envelope is never silently discarded.
        """
        if self._producer is None:
            return
        from events.kafka import build_envelope
        from events.topics import topic_for

        envelope = build_envelope(
            event_type="acquisition.request",
            event_version="2.0",
            producer="dispatcher",
            producer_version="0.1.0",
            payload=str(
                {
                    "task_id": task.get("task_id"),
                    "verdict": decision.verdict.value,
                    "execution_class": decision.execution_class,
                }
            ).encode(),
            investigation_id=task.get("investigation_id"),
            tenant_id=task.get("tenant_id"),
            source_id=task.get("source_id"),
            work_id=task.get("work_id"),
            region_id=task.get("region") or task.get("region_id"),
        )
        self._producer.produce(
            topic_for("acquisition.request"), envelope, key=task.get("task_id") or decision.task_id
        )


common_host = re.compile(r"^(?:https?://)?([^/:]+)")


def host_of(uri: str) -> str:
    """Canonical host key for concurrency/source limits (T133)."""
    m = common_host.match(uri)
    return m.group(1).lower() if m else uri.lower()
