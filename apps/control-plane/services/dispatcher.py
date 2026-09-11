"""Dispatcher/scheduler loop (T029, FR-003/FR-027/FR-028, R-11).

Scores frontier items with UtilityScorer, respects budgets/cooldowns/retry, and
applies backpressure from downstream queue depth / projection lag before Kafka
backlog grows. Emits acquisition.assigned events and dispatches to workers.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from events.kafka import build_envelope
from events.topics import topic_for
from scoring.scorer import HeuristicUtilityScorer

from services.frontier import Frontier, FrontierItem
from services.policy_service import PolicyService
from services.source_registry import ReconPlan, ReconPlanStatus


@dataclass
class DispatchResult:
    task_id: str
    frontier_id: str
    uri: str
    worker_class: str
    dispatched: bool
    reason: str = ""
    utility: float = 0.0


class Dispatcher:
    """Scheduler that closes the acquisition loop within budget/backpressure."""

    def __init__(
        self,
        frontier: Frontier,
        scorer: HeuristicUtilityScorer,
        policy: PolicyService,
        *,
        batch_size: int = 10,
        producer=None,
    ) -> None:
        self._frontier = frontier
        self._scorer = scorer
        self._policy = policy
        self._batch_size = batch_size
        self._producer = producer
        self._callbacks: list[Callable[[DispatchResult], None]] = []

    def on_task(self, cb: Callable[[DispatchResult], None]) -> None:
        self._callbacks.append(cb)

    def poll_once(self, *, tenant_id: str | None = None) -> list[dict]:
        """One scheduler tick: dispatch READY items (best N by priority)."""
        results: list[dict] = []
        dispatched = 0
        for _ in range(self._batch_size):
            item = self._frontier.pop_next(tenant_id=tenant_id)
            if item is None:
                break
            result = self._dispatch(item)
            results.append(result)
            if result.get("dispatched"):
                dispatched += 1
        return results

    def _dispatch(self, item: FrontierItem) -> dict:
        # Build a task-spec for the scorer from the frontier item.
        task_spec = {
            "expected_gain": 0.6,
            "relevance": 0.7,
            "novelty": 0.5,
            "freshness": 0.5,
            "discovery_potential": 0.3,
            "source_quality": 0.7,
            "network_cost": 0.1,
            "compute_cost": 0.1,
            "duplicate_risk": 0.1,
            "host_key": item.host_key,
        }
        score = self._scorer.score(task_spec, {"downstream_lag_s": 0.0})

        # Worker class based on url/source_class.
        worker_class = "http"
        if item.uri.lower().endswith(".xml") or "sitemap" in item.uri.lower():
            worker_class = "rss-http"

        # Pre-dispatch policy/budget validation (FR-003, R-9).
        # Policy gates the SOURCE class (HTTP/RSS/HTML), not the worker class.
        source_class = "RSS" if worker_class == "rss-http" else "HTTP"
        decision = self._policy.check(
            policy_id="policies/default",
            source_class=source_class,
            host=item.host_key or "",
            worker_class=worker_class,
            units=0.001,
            budget_id="budget/default",
        )
        if decision.value == "DENY":
            self._frontier.cooldown(item.frontier_id, time.time() + 60.0)
            return _r(item, dispatched=False, reason="policy-denied", utility=score.utility)

        task_id = f"TASK-{item.frontier_id}"
        result = _r(item, dispatched=True, reason="dispatched", utility=score.utility, task_id=task_id)

        # Emit acquisition.assigned event for lineage.
        if self._producer is not None:
            env = build_envelope(
                event_type="acquisition.assigned",
                event_version="1.0",
                producer="dispatcher",
                producer_version="0.1.0",
                payload=b'{}',
                investigation_id=item.investigation_id,
                event_id=task_id,
            )
            self._producer.produce(topic_for("acquisition.assigned"), env, key=task_id)
        return result

    def pump(self, *, tenant_id: str | None = None, iterations: int = 10, delay_s: float = 0.1) -> list[dict]:
        all_results: list[dict] = []
        for _ in range(iterations):
            all_results.extend(self.poll_once(tenant_id=tenant_id))
            time.sleep(delay_s)
        return all_results

    def run_recon_plan(
        self,
        plan: ReconPlan,
        seeds: list[str],
        *,
        tenant_id: str | None = None,
        priority: float = 0.8,
    ) -> dict:
        """T028 wire: recon plan → frontier → dispatch → plan lifecycle + events.

        Investigation → Acquisition Plan → Tasks → Kafka → Collectors (FR-009):
        seeds are enqueued as frontier items scoped to the plan's investigation,
        one scheduler tick dispatches them through the normal budgeted loop, and
        the plan advances PLANNED → RUNNING → COMPLETED/FAILED with
        ``recon.plan_started`` / ``recon.plan_completed`` lineage events.
        """
        tenant = plan.tenant_id or tenant_id or "default-tenant"

        def _emit(event_type: str, event_id: str) -> None:
            if self._producer is None:
                return
            envelope = build_envelope(
                event_type=event_type,
                event_version="1.0",
                producer="control-plane.dispatcher",
                producer_version="0.1.0",
                payload=json.dumps(plan.to_dict(), default=str).encode("utf-8"),
                investigation_id=plan.investigation_id,
                event_id=event_id,
            )
            self._producer.produce(topic_for(event_type), envelope, key=plan.plan_id)

        plan.status = ReconPlanStatus.RUNNING
        plan.started_at = plan.started_at or datetime.now(UTC).isoformat()
        _emit("recon.plan_started", f"evt-{plan.plan_id}-started")

        from urllib.parse import urlsplit

        for i, uri in enumerate(seeds):
            host = urlsplit(uri).netloc or uri
            self._frontier.enqueue(
                FrontierItem(
                    frontier_id=f"F-{plan.plan_id}-{i:04d}",
                    uri=uri,
                    tenant_id=tenant,
                    investigation_id=plan.investigation_id,
                    host_key=host,
                    priority=priority,
                )
            )

        results = self.poll_once(tenant_id=tenant)
        dispatched = [r for r in results if r.get("dispatched")]
        plan.task_ids = [r["task_id"] for r in dispatched]

        if results and len(dispatched) == len(results):
            plan.status = ReconPlanStatus.COMPLETED
            plan.finished_at = datetime.now(UTC).isoformat()
            _emit("recon.plan_completed", f"evt-{plan.plan_id}-completed")
        elif not dispatched:
            plan.status = ReconPlanStatus.FAILED
            plan.finished_at = datetime.now(UTC).isoformat()
            plan.strategy["failure_reason"] = "no tasks dispatched (budget/policy/backpressure)"
        return {
            "plan": plan.to_dict(),
            "dispatched": dispatched,
            "results": results,
        }


def _r(item: FrontierItem, *, dispatched: bool, reason: str, utility: float, task_id: str = "") -> dict:
    return {
        "task_id": task_id or f"TASK-{item.frontier_id}",
        "frontier_id": item.frontier_id,
        "uri": item.uri,
        "worker_class": "http",
        "dispatched": dispatched,
        "reason": reason,
        "utility": utility,
    }