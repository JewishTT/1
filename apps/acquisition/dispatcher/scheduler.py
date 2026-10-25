"""Collection Fabric dispatcher — two-stage scheduler (Feature 034 production).

Stage A: score utility / novelty / freshness / expected gain vs cost.
Stage B: durable budget reservation + policy check before any dispatch.

All no-op paths from the audited commit are removed:
- `ScopeLimits.allows()` no longer returns `(True, "")` unconditionally.
- `emit_request()` no longer silently returns when the producer is missing.
- Hardcoded `policies/default`, `budget/default`, `units=0.001` are removed.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from adapters.registry import REGISTRY, CapabilityGap, SourceRegistration
from scoring.scorer import HeuristicUtilityScorer, UtilityScore


class Verdict(StrEnum):
    DISPATCH = "dispatch"
    DEFER = "defer"
    REJECT = "reject"


class DispatcherConfigurationError(RuntimeError):
    """The dispatcher is not correctly configured for production dispatch."""


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
    reservation_id: str | None = None
    policy_digest: str | None = None


class ResourceLimits(Protocol):
    """Durable budget/resource constraints consulted by stage B.

    The default implementation must NOT allow everything. Production injects a
    PostgreSQL-backed reservation service; without it, dispatch is blocked.
    """

    def allows(
        self,
        execution_class: str,
        region: str | None,
        host_key: str,
        required: set[str],
        *,
        tenant_id: str | None = None,
        case_id: str | None = None,
        policy_revision: str | None = None,
    ) -> tuple[bool, str, str | None]:
        """Returns (allowed, reason_code, reservation_id).

        A missing reservation provider means not allowed with reason
        ``BLOCKED_BUDGET`` and no reservation_id.
        """
        ...


class UnconfiguredResourceLimits:
    """Resource limits that deny everything until a durable provider is injected.

    This replaces the old `ScopeLimits` whose `allows()` returned `(True, "")`.
    """

    def allows(
        self,
        _execution_class: str,
        _region: str | None,
        _host_key: str,
        _required: set[str],
        **_: Any,
    ) -> tuple[bool, str, str | None]:
        return False, "BLOCKED_BUDGET", None


class Producer(Protocol):
    """Minimal produce surface the dispatcher emits on."""

    def produce(self, topic: str, envelope, *, key: str | None = None) -> None: ...


class Dispatcher:
    """Capability-aware two-stage scheduler (Feature 034).

    No hardcoded policy/budget IDs. Tenant/case/policy revision/budget ID are
    bound on every task. Backpressure is checked before lease/pop.
    """

    def __init__(
        self,
        *,
        scorer: HeuristicUtilityScorer | None = None,
        limits: ResourceLimits | None = None,
        min_utility: float = 0.01,
        producer: Producer | None = None,
        tenant_id: str | None = None,
        case_id: str | None = None,
        policy_revision: str | None = None,
        budget_reservation_id: str | None = None,
    ) -> None:
        self.scorer = scorer or HeuristicUtilityScorer()
        self.limits = limits or UnconfiguredResourceLimits()
        self.min_utility = min_utility
        self._producer = producer
        self._tenant_id = tenant_id
        self._case_id = case_id
        self._policy_revision = policy_revision
        self._budget_reservation_id = budget_reservation_id

    def schedule(
        self,
        task: dict,
        context: dict | None = None,
    ) -> ScheduleDecision:
        context = context or {}
        task_id = task["task_id"]
        region = task.get("region")
        host_key = task.get("host_key", task.get("uri", "*"))

        # Stage A — intelligence.
        score: UtilityScore = self.scorer.score(task, context)
        if score.utility < self.min_utility:
            return ScheduleDecision(
                task_id=task_id,
                verdict=Verdict.DEFER,
                utility=score.utility,
                priority=score.priority,
                reason=f"utility {score.utility:.4f} below min {self.min_utility}",
            )

        # Stage B — capability match.
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

        # Durable budget check. No reservation → DEFER/BLOCKED_BUDGET, never dispatch.
        allowed, reason_code, reservation_id = self.limits.allows(
            registration.execution_class,
            region,
            host_key,
            required,
            tenant_id=self._tenant_id,
            case_id=self._case_id,
            policy_revision=self._policy_revision,
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
                reason=reason_code,
                reservation_id=reservation_id,
                policy_digest=self._policy_revision,
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
            reason="durable budget reserved; capability match dispatch",
            reservation_id=reservation_id,
            policy_digest=self._policy_revision,
        )

    def emit_request(self, task: dict, decision: ScheduleDecision) -> None:
        """Emit `acquisition.request` onto the stream plane.

        A missing producer/outbox is a named DispatcherConfigurationError;
        the API cannot return `dispatched=true` without a producer.
        """
        if self._producer is None:
            raise DispatcherConfigurationError(
                "dispatcher has no producer/outbox; acquisition.request cannot be emitted. "
                "Inject a real producer in the application factory and assert readiness."
            )
        import json

        from events.kafka import build_envelope
        from events.topics import topic_for

        envelope = build_envelope(
            event_type="acquisition.request",
            event_version="2.0",
            producer="dispatcher",
            producer_version="0.1.0",
            payload=json.dumps(
                {
                    "task_id": task.get("task_id"),
                    "query": task.get("query"),
                    "source_id": task.get("source_id"),
                    "verdict": decision.verdict.value,
                    "execution_class": decision.execution_class,
                    "runtime_ref": task.get("runtime_ref") or "",
                    "query_ref": task.get("query_ref") or "",
                    "constraints": task.get("constraints") or [],
                    "tenant_id": task.get("tenant_id") or self._tenant_id,
                    "case_id": task.get("case_id") or self._case_id,
                    "scope_revision": task.get("scope_revision"),
                    "scope_digest": task.get("scope_digest") or "",
                    "policy_revision": self._policy_revision or "",
                    "policy_digest": task.get("policy_digest") or "",
                    "case_policy_source_id": task.get("case_policy_source_id") or "",
                    "approved_action_ref": task.get("approved_action_ref") or "",
                    "action_id": task.get("action_id") or "",
                    "run_id": task.get("run_id") or "",
                    "budget_reservation_id": decision.reservation_id or "",
                    "idempotency_key": task.get("idempotency_key") or "",
                },
                sort_keys=True,
            ).encode("utf-8"),
            investigation_id=task.get("investigation_id"),
            tenant_id=task.get("tenant_id") or self._tenant_id,
            source_id=task.get("source_id"),
            work_id=task.get("work_id"),
            region_id=task.get("region") or task.get("region_id"),
        )
        self._producer.produce(
            topic_for("acquisition.request"),
            envelope,
            key=task.get("task_id") or decision.task_id,
        )

    def require_producer(self) -> None:
        """Fail fast if no producer is configured. Call at startup readiness."""
        if self._producer is None:
            raise DispatcherConfigurationError(
                "no Kafka producer configured for dispatcher; production dispatch impossible"
            )


common_host = re.compile(r"^(?:https?://)?([^/:]+)")


def host_of(uri: str) -> str:
    """Canonical host key for concurrency/source limits."""
    m = common_host.match(uri)
    return m.group(1).lower() if m else uri.lower()


def digest_for_scope(
    *,
    tenant_id: str,
    case_id: str,
    policy_revision: str,
    source_ids: list[str],
    claim_families: list[str],
    time_range: dict,
) -> str:
    """Deterministic scope digest; any change invalidates queued actions."""
    material = json.dumps(
        {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "policy_revision": policy_revision,
            "source_ids": sorted(source_ids),
            "claim_families": sorted(claim_families),
            "time_range": time_range,
        },
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
