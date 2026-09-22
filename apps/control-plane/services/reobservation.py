"""Re-observation dedup + ETag three-way split (T101, R-08).

When a frontier item is revisited, the worker decides WITHOUT a full refetch
whenever the previous ETag matches: the observation is ``unchanged`` (304), the
existing digest stands, no new content-addressed store object is written. A
fresh body is compared against the stored digest to produce one of
``created`` / ``changed`` / ``unchanged``. ``duplicate`` is the enqueue-level
outcome (same session already observed the uri).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReobsOutcome(str, Enum):
    CREATED = "created"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"


def etag_equal(left: str | None, right: str | None) -> bool:
    """Weak/strong ETag comparison (strip W/ and quotes, case-fold)."""
    def _canon(value: str | None) -> str:
        if not value:
            return ""
        value = value.strip()
        value = value.removeprefix("W/")
        return value.strip('"').lower()

    return bool(left) and _canon(left) == _canon(right)


@dataclass
class Reobservation:
    """The three-way decision inputs for a re-observation."""

    uri: str
    tenant_id: str
    previous_digest: str | None = None
    previous_etag: str | None = None
    new_etag: str | None = None
    new_digest: str | None = None
    has_body: bool = True
    already_seen: bool = False

    def classify(self) -> ReobsOutcome:
        """Three-way + duplicate split.

        Order matters: a matching ETag short-circuits even when the digest was
        not recomputed (no refetch) — the content cannot have changed.
        """
        if self.already_seen:
            return ReobsOutcome.DUPLICATE
        if etag_equal(self.previous_etag, self.new_etag):
            return ReobsOutcome.UNCHANGED
        if self.previous_digest is None:
            return ReobsOutcome.CREATED
        if self.new_digest is None:
            # Different ETag but no fresh body/digest to compare: refetch is
            # required before we can write a stable "changed" observation.
            return ReobsOutcome.CHANGED
        if self.new_digest == self.previous_digest:
            return ReobsOutcome.UNCHANGED
        return ReobsOutcome.CHANGED

    def refetch_required(self) -> bool:
        """True when the planner must pull a fresh body before deciding."""
        if self.already_seen:
            return False
        return self.classify() in (ReobsOutcome.CREATED, ReobsOutcome.CHANGED)


def classify_reobservation(previous: dict, observed: dict) -> dict[str, object]:
    """Dict-friendly entry point used by planner/projection layers."""
    decision = reobserve(previous, observed)
    return {
        "uri": decision.uri,
        "outcome": decision.outcome.value,
        "refetch_required": decision.refetch_required,
        "etag_match": decision.etag_match,
        "reasons": decision.reasons,
    }


@dataclass
class ReobsDecision:
    """Checkpoint carrier produced by :meth:`Reobservation.checkpoint`."""

    uri: str
    tenant_id: str
    outcome: ReobsOutcome
    refetch_required: bool
    etag_match: bool = False
    digest: str | None = None
    etag: str | None = None
    reasons: list[str] = field(default_factory=list)


def reobserve(previous: dict, observed: dict) -> ReobsDecision:
    """Full re-observation pipeline: classify + carry the durable checkpoint."""
    reob = Reobservation(
        uri=observed.get("uri") or previous.get("uri") or "",
        tenant_id=observed.get("tenant_id") or previous.get("tenant_id") or "",
        previous_digest=previous.get("digest") or previous.get("last_digest"),
        previous_etag=previous.get("etag") or previous.get("last_etag"),
        new_etag=observed.get("etag"),
        new_digest=observed.get("digest"),
        has_body=bool(observed.get("payload") is not None or observed.get("has_body", True)),
        already_seen=bool(observed.get("already_seen", False)),
    )
    outcome = reob.classify()
    reasons = []
    if etag_equal(reob.previous_etag, reob.new_etag):
        reasons.append("etag-match")
    elif reob.previous_digest is None:
        reasons.append("first-observation")
    elif reob.new_digest and reob.new_digest == reob.previous_digest:
        reasons.append("digest-equal")
    elif reob.new_digest:
        reasons.append("digest-differ")
    else:
        reasons.append("no-fresh-body")
    return ReobsDecision(
        uri=reob.uri,
        tenant_id=reob.tenant_id,
        outcome=outcome,
        refetch_required=reob.refetch_required(),
        etag_match=etag_equal(reob.previous_etag, reob.new_etag),
        digest=reob.new_digest or reob.previous_digest,
        etag=reob.new_etag or reob.previous_etag,
        reasons=reasons,
    )