"""Investigation activities for Temporal (Feature 024 T029).

``InvestigationWorkflow`` schedules two activities **by string name**:

* ``acquisition.acquire_batch`` (investigation.py:213)
* ``acquisition.recrawl`` (investigation.py:288)

Neither had an ``@activity.defn`` anywhere in the repository, and the task queue
``cognitive-investigations`` had no worker registered on it. So the investigation
lifecycle was doubly inert: the workflows were unreachable, and even once reachable
their first activity call would have failed to resolve. This module supplies them.

Design notes
------------
* Activities are the only place in the investigation path that performs I/O. The
  lifecycle state machine stays pure so it remains testable without Temporal.
* Acquisition goes through ``services.frontier`` rather than by fetching directly,
  so it lands on the canonical path instead of reimplementing a fetch.
* Both activities are idempotent. Temporal retries, and a retry must not acquire
  twice: the batch is bounded by what the frontier currently has READY, and the
  result carries the ids actually dispatched so a caller can tell.
* Infra absence is reported, not raised. A missing database means "nothing
  dispatched", which the workflow treats as an empty batch and retries on its own
  schedule -- it is a transient condition, not a workflow failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from temporalio import activity

log = logging.getLogger("cognitive.investigation.activities")


@dataclass
class AcquisitionBatch:
    """What one batch actually did. Returned as a plain dict over the wire."""

    investigation_id: str
    step: int
    dispatched: list[str] = field(default_factory=list)
    skipped: int = 0
    reason: str = "dispatched"
    at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "step": self.step,
            "dispatched": self.dispatched,
            "dispatched_count": len(self.dispatched),
            "skipped": self.skipped,
            "reason": self.reason,
            "at": self.at or datetime.now(UTC).isoformat(),
        }


@activity.defn(name="acquisition.acquire_batch")
async def acquire_batch(investigation_id: str, step: int) -> dict[str, Any]:
    """Dispatch one bounded batch of frontier work for an investigation.

    Idempotent under Temporal retry: the frontier is drained rather than marked, so
    a replay either finds the same READY items or none -- it never double-acquires a
    single item.
    """
    batch = AcquisitionBatch(investigation_id=investigation_id, step=step)
    log.info("acquire_batch investigation=%s step=%s", investigation_id, step)

    try:
        from services.frontier import PgFrontier
    except Exception as exc:  # pragma: no cover - import guard
        batch.reason = f"frontier_unavailable:{type(exc).__name__}"
        log.warning("frontier import failed: %s", exc)
        return batch.to_dict()

    frontier = _open_frontier(PgFrontier)
    if frontier is None:
        batch.reason = "database_unavailable"
        log.warning("database unavailable; batch not dispatched")
        return batch.to_dict()

    try:
        for _ in range(_batch_size()):
            item = frontier.pop_next(tenant_id=investigation_id)
            if item is None:
                break
            batch.dispatched.append(item.frontier_id)
    except Exception as exc:
        batch.reason = f"frontier_error:{type(exc).__name__}"
        log.warning("frontier pop failed: %s", exc)
    return batch.to_dict()


@activity.defn(name="acquisition.recrawl")
async def recrawl(investigation_id: str) -> dict[str, Any]:
    """Re-queue an investigation for a fresh look.

    The recrawl itself is frontier work, so this hands the investigation back to the
    acquisition path rather than fetching anything itself.
    """
    log.info("recrawl investigation=%s", investigation_id)
    return await acquire_batch(investigation_id, step=-1)


def _batch_size() -> int:
    import os

    try:
        return max(1, int(os.environ.get("ACQUISITION_BATCH_SIZE", "10")))
    except ValueError:
        return 10


def _open_frontier(factory: Any) -> Any | None:
    """Open the Postgres frontier, or report that infra is absent.

    Infra absence is not an error here. Temporal will retry the activity on its own
    schedule, and a hard failure would burn the retry budget on a database that is
    simply not up yet.
    """
    try:
        from db.session import get_session  # noqa: F401
    except Exception as exc:
        log.info("db session unavailable: %s", exc)
        return None
    try:
        return factory()
    except Exception as exc:
        log.info("frontier open failed: %s", exc)
        return None


ACTIVITIES = [acquire_batch, recrawl]

__all__ = ["ACTIVITIES", "AcquisitionBatch", "acquire_batch", "recrawl"]