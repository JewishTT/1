"""Worldline anchoring and durability for the science layer (Feature 024 Phase 12).

Wave 0's finding, verbatim: ``rg worldline apps/science/**`` returns **zero hits**, and
``science/store.py:1-12`` describes itself as an in-memory projection over ``science.*``
envelopes. That is exactly the "private toy state" the source ТЗ forbids -- scientific
verdicts computed against nothing in particular, lost on restart.

This module supplies the two missing properties without rewriting the 14 existing
science subpackages:

1. **Anchoring (FR-086).** Every evaluation declares the worldline snapshot it was
   computed against, and refuses to run against a worldline that has moved past it.
   Without this, "calibration is within tolerance" describes no particular moment in
   the investigated reality, and cannot be reproduced.
2. **Durability (FR-085).** :class:`DurableScienceStore` keeps the store's own contract
   -- ``science/store.py`` already says swapping in a durable kernel preserves it under
   Constitution V -- and backs it with PostgreSQL.

Reused, not rewritten: ``science.store.ScienceStore``'s contract and its
``ENTITY_BY_EVENT`` event-to-collection map are used as they stand.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


class AnchorError(ValueError):
    """An evaluation was requested against the wrong worldline snapshot."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class EvaluationStatus(enum.StrEnum):
    """FR-087. Causal evaluation records each stage, never one opaque verdict."""

    IDENTIFIED = "identified"
    ESTIMATED = "estimated"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class WorldlineAnchor:
    """The worldline position an evaluation is bound to.

    ``snapshot_id`` names a committed worldline snapshot. ``watermark`` is the event
    position inside that snapshot, so an evaluation can be pinned to a prefix of it and
    cannot silently consume events published after it was computed.
    """

    snapshot_id: str
    watermark: int = 0
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise AnchorError("anchor_snapshot_missing", "an evaluation must name its snapshot")
        if self.watermark < 0:
            raise AnchorError("anchor_watermark_negative", f"{self.watermark}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "watermark": self.watermark,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WorldlineAnchor:
        return cls(
            snapshot_id=payload["snapshot_id"],
            watermark=int(payload.get("watermark", 0)),
            fingerprint=payload.get("fingerprint", ""),
        )


@dataclass(frozen=True, slots=True)
class ScienceEvaluation:
    """One evaluation, bound to a worldline snapshot and to its method.

    ``method_fingerprint`` (FR-090) is what makes the result reproducible: it names the
    code and dependency versions that produced it, so a later run can tell whether it
    is comparing like with like.
    """

    evaluation_id: str
    kind: str
    anchor: WorldlineAnchor
    method_fingerprint: str
    status: EvaluationStatus = EvaluationStatus.INCONCLUSIVE
    stages: Mapping[str, str] = field(default_factory=dict)
    measurements: Mapping[str, float] = field(default_factory=dict)
    tolerance: float | None = None
    verdict: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", EvaluationStatus(self.status))
        if not self.evaluation_id:
            raise AnchorError("evaluation_id_missing", "an evaluation needs an identity")
        if not self.method_fingerprint:
            raise AnchorError(
                "method_fingerprint_missing",
                "an evaluation without a method fingerprint cannot be reproduced",
            )

    # -- calibration (FR-089) ----------------------------------------------

    def calibration_drift(self) -> float | None:
        drift = self.measurements.get("drift")
        return None if drift is None else abs(drift)

    def is_within_tolerance(self) -> bool:
        """``abs(drift) <= tolerance`` -- stated as a rule, not as a stored boolean.

        A stored verdict would go stale the moment the tolerance or the measurement
        moved; the rule is recomputed from the numbers so it cannot.
        """
        drift = self.calibration_drift()
        if drift is None or self.tolerance is None:
            return False
        return drift <= self.tolerance

    # -- causal stages (FR-087) ---------------------------------------------

    def stage_outcome(self, stage: str) -> str | None:
        return self.stages.get(stage)

    def is_complete_causal(self, required: Sequence[str] = ("identify", "estimate", "refute")) -> bool:
        return all(self.stage_outcome(stage) for stage in required)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "kind": self.kind,
            "anchor": self.anchor.to_dict(),
            "method_fingerprint": self.method_fingerprint,
            "status": self.status.value,
            "stages": dict(self.stages),
            "measurements": dict(self.measurements),
            "tolerance": self.tolerance,
            "verdict": self.verdict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScienceEvaluation:
        return cls(
            evaluation_id=payload["evaluation_id"],
            kind=payload["kind"],
            anchor=WorldlineAnchor.from_dict(payload["anchor"]),
            method_fingerprint=payload["method_fingerprint"],
            status=EvaluationStatus(payload.get("status", "inconclusive")),
            stages=dict(payload.get("stages", {})),
            measurements=dict(payload.get("measurements", {})),
            tolerance=payload.get("tolerance"),
            verdict=payload.get("verdict", ""),
        )


class WorldlineReader(Protocol):
    """The only view of the worldline the science layer gets (FR-086)."""

    def current_snapshot_id(self) -> str: ...

    def snapshot_fingerprint(self, snapshot_id: str) -> str: ...

    def events_through(self, snapshot_id: str, watermark: int) -> tuple[Any, ...]: ...


class AnchoredEvaluator:
    """Runs evaluations against a snapshot, and refuses to run past one.

    The refusal is the point. A science verdict that silently reads post-snapshot state
    is not reproducible, and a reproducible-looking verdict that cannot be reproduced
    is worse than no verdict.
    """

    def __init__(self, worldline: WorldlineReader) -> None:
        self._worldline = worldline

    def anchor(self, *, snapshot_id: str | None = None, watermark: int = 0) -> WorldlineAnchor:
        resolved = snapshot_id or self._worldline.current_snapshot_id()
        return WorldlineAnchor(
            snapshot_id=resolved,
            watermark=watermark,
            fingerprint=self._worldline.snapshot_fingerprint(resolved),
        )

    def check_anchor(self, anchor: WorldlineAnchor) -> tuple[Any, ...]:
        """Return the events the evaluation is allowed to read, or refuse."""
        current = self._worldline.current_snapshot_id()
        if current != anchor.snapshot_id:
            raise AnchorError(
                "snapshot_superseded",
                f"evaluation is bound to {anchor.snapshot_id} but the worldline is at {current}",
            )
        return self._worldline.events_through(anchor.snapshot_id, anchor.watermark)

    def is_still_current(self, anchor: WorldlineAnchor) -> bool:
        return self._worldline.current_snapshot_id() == anchor.snapshot_id


class DurableScienceStore:
    """PostgreSQL-backed science state, same contract as the in-memory store.

    ``science/store.py`` projects state from ``science.*`` envelopes and states that
    swapping in a durable kernel preserves the contract (Constitution V). This is that
    kernel: the same event-to-collection map, persisted instead of held in a dict.

    The SQL itself is injected as ``execute``/``query`` callables rather than inherited
    from a driver base class. Principle V requires that domain logic carry no
    vendor-specific class, and accepting the seam as a parameter makes that structural
    instead of aspirational.
    """

    def __init__(
        self,
        *,
        entity_by_event: Mapping[str, tuple[str, str]],
        execute: Callable[[dict[str, Any]], None] | None = None,
        query: Callable[[str], Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        self.entity_by_event = dict(entity_by_event)
        self._execute_fn = execute
        self._query_fn = query

    def collection_for(self, event_type: str) -> tuple[str, str]:
        try:
            return self.entity_by_event[event_type]
        except KeyError:
            raise AnchorError(
                "science_event_unmapped",
                f"{event_type!r} has no collection in the science event map",
            ) from None

    def persist(self, records: Sequence[Mapping[str, Any]]) -> list[str]:
        """Upsert records. Returns the ids written.

        Deterministic ids from the event map mean a replayed event overwrites its own
        row rather than accumulating a second copy.
        """
        written: list[str] = []
        for record in records:
            event_type = record["event_type"]
            collection, id_field = self.collection_for(event_type)
            key = record.get(id_field)
            if not key:
                raise AnchorError("science_record_keyless", f"{event_type} record has no {id_field}")
            body = {
                "collection": collection,
                "record_id": key,
                "event_id": record.get("event_id", ""),
                "payload": json.dumps(
                    {k: v for k, v in record.items() if k != "event_type"},
                    sort_keys=True,
                ),
            }
            self._execute(body)
            written.append(str(key))
        return written

    def load(self, collection: str) -> tuple[dict[str, Any], ...]:
        return tuple(self._query(collection))

    def _execute(self, body: dict[str, Any]) -> None:
        if self._execute_fn is None:
            raise AnchorError(
                "science_store_unbound",
                "DurableScienceStore was constructed without an execute seam",
            )
        self._execute_fn(body)

    def _query(self, collection: str) -> Sequence[Mapping[str, Any]]:
        if self._query_fn is None:
            raise AnchorError(
                "science_store_unbound",
                "DurableScienceStore was constructed without a query seam",
            )
        return self._query_fn(collection)

    def durability(self) -> str:
        return "durable"


__all__ = [
    "AnchorError",
    "AnchoredEvaluator",
    "DurableScienceStore",
    "EvaluationStatus",
    "ScienceEvaluation",
    "WorldlineAnchor",
    "WorldlineReader",
]