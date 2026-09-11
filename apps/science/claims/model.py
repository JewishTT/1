"""Core value types for probabilistic claims (T084, data-model §1–§5).

First-party scientific module (feature 006). ``ScientificClaim``/``Hypothesis``
carry a fully-provenanced ``CredenceDistribution`` (FR-001: never fabricated,
FR-002: method must resolve to a declared model). Evidence links are append-
only (FR-015). Enums are ``StrEnum`` with lowercase values so they serialise
directly into ``science.*`` event payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ClaimStatus(StrEnum):
    """FR-001 lifecycle for a probabilistic claim (append-only transitions)."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    WEAKENED = "weakened"
    DISCARDED = "discarded"
    UNCERTAIN = "uncertain"


class HypothesisStatus(StrEnum):
    """FR-004 lifecycle for a competing explanatory hypothesis."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    STRENGTHENED = "strengthened"
    WEAKENED = "weakened"
    DISCARDED = "discarded"
    CONFIRMED = "confirmed"
    RESOLVED = "resolved"


class ReviewState(StrEnum):
    """US7 evidence-ladder review state (derived from review events, not stored)."""

    REVIEW_PENDING = "review_pending"
    IN_REVIEW = "in_review"
    CONFIRMED = "confirmed"
    DISCARDED = "discarded"


class EvidenceDirection(StrEnum):
    """Direction of an evidence link (FR-004: supports | refutes | discriminates)."""

    SUPPORTS = "supports"
    REFUTES = "refutes"
    DISCRIMINATES = "discriminates"


class CalibrationVerdict(StrEnum):
    """FR-003 verdict produced by the calibration harness."""

    CALIBRATED = "calibrated"
    OVERCONFIDENT = "overconfident"
    UNCALIBRATED = "uncalibrated"


@dataclass(frozen=True)
class CredenceDistribution:
    """Probability over stated outcomes (FR-002: method must be a declared model)."""

    states: list[str]
    labels: list[str]
    probs: list[float]
    method: str
    calibration_ref: str | None = None

    def __post_init__(self) -> None:
        if len({len(self.states), len(self.labels), len(self.probs)}) != 1:
            raise ValueError("states / labels / probs must have equal length")
        if any(p < 0.0 for p in self.probs):
            raise ValueError("probabilities cannot be negative")

    @property
    def total(self) -> float:
        """Sum of the probability mass (validate with the calibration harness)."""
        return sum(self.probs)

    def state_index(self, state: str) -> int:
        return self.states.index(state)


@dataclass
class EvidenceLink:
    """Immutable evidence attachment (FR-015: append-only, never edited/deleted)."""

    link_id: str
    observation_id: str
    raw_sha256: str
    direction: EvidenceDirection
    weight: float
    attached_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceLink:
        return cls(
            link_id=data["link_id"],
            observation_id=data["observation_id"],
            raw_sha256=data["raw_sha256"],
            direction=EvidenceDirection(data["direction"]),
            weight=data["weight"],
        )

    def to_ref(self) -> dict[str, str]:
        """Refs-only representation for event payloads (I-5)."""
        return {
            "link_id": self.link_id,
            "observation_id": self.observation_id,
            "raw_sha256": self.raw_sha256,
            "direction": self.direction.value,
        }


@dataclass
class DecisionRecord:
    """Append-only decision (SC-003: discards require who/when/why)."""

    actor: str
    reason: str
    at: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScientificClaim:
    """A probabilistic statement about a structure/process (data-model §1)."""

    claim_id: str
    project_id: str
    statement: str
    distribution: CredenceDistribution
    model_id: str
    status: ClaimStatus = ClaimStatus.DRAFT
    provenance: list[EvidenceLink] = field(default_factory=list)
    producer_run: str | None = None
    ladder_rung: int | None = None
    review_state: ReviewState = ReviewState.REVIEW_PENDING
    timestamps: dict[str, str] = field(default_factory=dict)

    def to_ref(self) -> dict[str, str]:
        """Refs-only representation for event payloads (I-5)."""
        ref = {
            "claim_id": self.claim_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "model_id": self.model_id,
            "provenance_refs": [link.to_ref() for link in self.provenance],
        }
        if self.distribution.calibration_ref:
            ref["distribution_ref"] = self.distribution.calibration_ref
        return ref


@dataclass
class Hypothesis:
    """Competing explanatory statement (data-model §3, FR-004)."""

    hypothesis_id: str
    project_id: str
    text: str
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    credence: CredenceDistribution | None = None
    evidence_links: list[EvidenceLink] = field(default_factory=list)
    decisions: list[DecisionRecord] = field(default_factory=list)
    gain_priority: float | None = None
    coverage: dict[str, Any] | None = None

    @property
    def is_dead(self) -> bool:
        return self.status in {HypothesisStatus.DISCARDED, HypothesisStatus.RESOLVED}


@dataclass
class CalibrationReport:
    """FR-003: per-model observed-vs-expected calibration."""

    report_id: str
    model_id: str
    buckets: list[dict[str, Any]]
    brier: float
    ece: float
    verdict: CalibrationVerdict
    thresholds: dict[str, float] = field(default_factory=dict)