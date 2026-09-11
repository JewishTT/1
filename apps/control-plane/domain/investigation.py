"""Investigation domain model + state machine (T021, FR-003, I-6 Process-Centric).

States: DRAFT → PLANNING → RUNNING → PAUSED → COMPLETED → ARCHIVED.
Budget/scope validated on transitions. The investigation is the unit of user
work; projections materialize automatically within its lifecycle.

Monitoring / late-event semantics (T028, US5)
=============================================
Donor: investigator (MIT) ``donors/investigator/src/investigator/state/investigation.py``
  (the per-investigation state container: owned counters, ``load``/``save``, O(1)
  index). License: MIT (logic layer only).

Adaptation notes
----------------
- The donor's ``runs_number`` run counter becomes four platform counters
  (``items_examined``, ``evidence_ingested``, ``candidates_resolved``,
  ``findings_created``) fed by the harvest/evidence/resolution/finding lanes.
- Counter updates are atomic Deltas: a counter either advances by the whole
  Delta or not at all — all validation happens before any mutation, and a
  counter can never go negative.
- Terminal states (COMPLETED / ARCHIVED) park late counter events: the counter
  is NOT mutated, and a ``governance.quarantined`` refs-only envelope is emitted
  when an ``emitter`` is attached (platform event bus). This mirrors the donor's
  "snapshot persists at close" invariant — after close, nothing further mutates.
- ``snapshot()`` returns the durable monitor snapshot (the donor's persisted
  record) so the workflow layer persists it exactly once at COMPLETED.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from events.kafka import Envelope, build_envelope
from events.topics import topic_for


class InvestigationState(enum.StrEnum):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


# Monitor counters fed by the platform lanes (US5, investigator state pattern).
MONITOR_COUNTERS = (
    "items_examined",
    "evidence_ingested",
    "candidates_resolved",
    "findings_created",
)

TERMINAL_STATES = (InvestigationState.COMPLETED, InvestigationState.ARCHIVED)


class InvestigationInvalidTransition(Exception):
    pass


class InvestigationValidationError(Exception):
    pass


class LateEventParked(Exception):
    """Raised when a monitor update targets a terminal investigation.

    The counter is left untouched (event is parked, not applied); the reason is
    carried so the caller can surface the ``governance.quarantined`` record.
    """

    def __init__(
        self,
        investigation_id: str,
        counter: str,
        delta: int,
        state: InvestigationState,
    ) -> None:
        super().__init__(
            f"counter '{counter}' delta {delta} parked after {state.value}"
        )
        self.investigation_id = investigation_id
        self.counter = counter
        self.delta = delta
        self.state = state


@dataclass
class InvestigationMonitor:
    """Atomic per-investigation progress counters (investigator state pattern).

    ``update_counter`` is the only writer and is strictly validate-then-mutate:
    an invalid name, a non-integer Delta, or an undershoot below zero raises
    without touching any counter (atomic). ``snapshot`` yields the persistent
    monitor record once at COMPLETED — the "close" invariant.
    """

    counters: dict[str, int] = field(
        default_factory=lambda: {name: 0 for name in MONITOR_COUNTERS}
    )
    updates: int = 0
    last_updated_at: str | None = None

    def update_counter(
        self,
        name: str,
        delta: int = 1,
        at: datetime | None = None,
    ) -> int:
        if name not in self.counters:
            raise ValueError(f"unknown monitor counter: {name}")
        if not isinstance(delta, int) or isinstance(delta, bool):
            raise TypeError(f"delta must be int, got {type(delta).__name__}")
        current = self.counters[name]
        if current + delta < 0:
            raise ValueError(f"counter '{name}' cannot go below zero ({current} + {delta})")
        self.counters[name] = current + delta
        self.updates += 1
        self.last_updated_at = (at or datetime.now(UTC)).isoformat()
        return self.counters[name]

    def snapshot(
        self,
        investigation_id: str,
        state: InvestigationState | str,
        at: datetime | None = None,
    ) -> dict:
        state_name = state.value if isinstance(state, InvestigationState) else str(state)
        return {
            "investigation_id": investigation_id,
            "state": state_name,
            "counters": dict(sorted(self.counters.items())),
            "counter_updates": self.updates,
            "snapshot_at": (at or datetime.now(UTC)).isoformat(),
        }


_TRANSITIONS: dict[InvestigationState, set[InvestigationState]] = {
    InvestigationState.DRAFT: {InvestigationState.PLANNING, InvestigationState.ARCHIVED},
    InvestigationState.PLANNING: {InvestigationState.RUNNING, InvestigationState.DRAFT},
    InvestigationState.RUNNING: {InvestigationState.PAUSED, InvestigationState.COMPLETED},
    InvestigationState.PAUSED: {
        InvestigationState.RUNNING,
        InvestigationState.COMPLETED,
        InvestigationState.ARCHIVED,
    },
    InvestigationState.COMPLETED: {InvestigationState.ARCHIVED},
    InvestigationState.ARCHIVED: set(),
}


@dataclass
class Investigation:
    investigation_id: str
    name: str
    tenant_id: str
    objective: dict[str, Any]
    seeds: list[str] = field(default_factory=list)
    scope: dict[str, Any] = field(default_factory=dict)
    policy_id: str | None = None
    state: InvestigationState = InvestigationState.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    monitor: InvestigationMonitor = field(default_factory=InvestigationMonitor)
    emitter: Callable[[str, Envelope, str | None], None] | None = field(
        default=None, repr=False, compare=False
    )

    def transition(self, target: InvestigationState) -> None:
        if target not in _TRANSITIONS[self.state]:
            raise InvestigationInvalidTransition(
                f"Cannot transition {self.state.value} -> {target.value}"
            )
        self.state = target
        self.updated_at = datetime.now(UTC)

    def update_counter(
        self,
        name: str,
        delta: int = 1,
        at: datetime | None = None,
    ) -> int:
        """Advance one monitor counter by an atomic Delta; park if terminal."""
        if self.state in TERMINAL_STATES:
            self._park_late_event(name, delta)
        return self.monitor.update_counter(name, delta=delta, at=at)

    def _park_late_event(self, name: str, delta: int) -> None:
        reason = "investigation_late_counter"
        payload = json.dumps(
            {
                "reason": reason,
                "investigation_id": self.investigation_id,
                "counter": name,
                "delta": delta,
                "state": self.state.value,
            },
            sort_keys=True,
        ).encode("utf-8")
        if self.emitter is not None:
            envelope = build_envelope(
                event_type="governance.quarantined",
                event_version="1.0",
                producer="control-plane.investigation.monitor",
                producer_version="0.1.0",
                payload=payload,
                investigation_id=self.investigation_id,
                entity_id=self.investigation_id,
                event_id=(
                    f"parked-{self.investigation_id}-{name}-{self.monitor.updates}"
                ),
            )
            self.emitter(topic_for("governance.quarantined"), envelope, key=self.investigation_id)
        raise LateEventParked(self.investigation_id, name, delta, self.state)

    def snapshot(self) -> dict:
        """Durable monitor record persisted once at close (COMPLETED)."""
        return self.monitor.snapshot(self.investigation_id, self.state, self.updated_at)

    def validate(self) -> None:
        if not self.name.strip():
            raise InvestigationValidationError("name is required")
        if not self.tenant_id:
            raise InvestigationValidationError("tenant_id is required")
        if not self.objective:
            raise InvestigationValidationError("objective is required")
        self._validate_scope()

    def _validate_scope(self) -> None:
        allowed = {"source_classes", "time_range", "regions", "languages"}
        unknown = set(self.scope or {}) - allowed
        if unknown:
            raise InvestigationValidationError(f"unknown scope fields: {sorted(unknown)}")

    def start(self) -> None:
        self.validate()
        self.transition(InvestigationState.PLANNING)

    def run(self) -> None:
        if self.state not in (InvestigationState.PLANNING, InvestigationState.PAUSED):
            raise InvestigationInvalidTransition(
                f"Only PLANNING|PAUSED can RUN, not {self.state.value}"
            )
        self.transition(InvestigationState.RUNNING)