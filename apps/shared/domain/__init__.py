"""Domain base models + invariant enforcement (T014, I-1…I-12).

Observation is immutable (I-1). Mention != Candidate != Entity (I-2).
Assertion != truth (I-3). No blobs on Kafka (I-5). Projections rebuildable (I-12).
ConstraintViolation raised on invariant breach; enforced at model layer.
"""

from __future__ import annotations


class ConstraintViolation(Exception):
    """Raised when a domain invariant is breached."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class ObservationImmutableError(ConstraintViolation):
    """I-1: observation never edited once recorded."""

    def __init__(self, observation_id: str) -> None:
        super().__init__("I-1", f"Observation {observation_id} is immutable; mutation rejected")


class MentionCandidateEntitySeparationError(ConstraintViolation):
    """I-2: Mention != Candidate != Entity."""

    def __init__(self, msg: str = "Mention, Candidate, Entity are distinct concepts") -> None:
        super().__init__("I-2", msg)


class AssertionNotTruthError(ConstraintViolation):
    """I-3: Assertion != truth."""

    def __init__(self, assertion_id: str) -> None:
        super().__init__("I-3", f"Assertion {assertion_id} is an admitted claim, not truth")


class NoBlobsOnKafkaError(ConstraintViolation):
    """I-5: Kafka carries refs, never raw blobs."""

    def __init__(self, detail: str = "Raw blob detected in event payload; carry refs only") -> None:
        super().__init__("I-5", detail)


class ProjectionRebuildableError(ConstraintViolation):
    """I-12: projections are rebuildable from durable evidence/events."""

    def __init__(
        self, detail: str = "Projection write blocked: evidence/event provenance missing"
    ) -> None:
        super().__init__("I-12", detail)


class TDAIsNotTruthError(ConstraintViolation):
    """I-6: TDA gives structural signals, not identity claims."""

    def __init__(self, detail: str = "TDA output cannot create trusted Entity directly") -> None:
        super().__init__("I-6", detail)


def enforce_observation_immutable(existing: dict, update: dict) -> None:
    """I-1: reject mutable updates to an already-recorded observation."""
    mutable_keys = {k for k in update if k not in ("status", "duplicate", "provenance")}
    if existing and mutable_keys:
        raise ObservationImmutableError(existing.get("observation_id", "unknown"))


def enforce_no_blobs(payload_bytes: bytes, max_inline: int = 0) -> None:
    """I-5: raw blobs must not appear inline in event payloads."""
    if len(payload_bytes) > max_inline:
        raise NoBlobsOnKafkaError(
            f"Payload size {len(payload_bytes)} bytes exceeds inline limit {max_inline}"
        )


def enforce_projection_provenance(
    provenance: dict | None, required_fields: list[str] | None = None
) -> None:
    """I-12: projections must carry event/observation provenance."""
    required = required_fields or ["event_id", "observation_id"]
    if not provenance:
        raise ProjectionRebuildableError("No provenance attached to projection write")
    missing = [f for f in required if f not in provenance]
    if missing:
        raise ProjectionRebuildableError(f"Missing provenance fields: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Donor-pattern invariants (feature 002: donor-pattern-integration)
# ---------------------------------------------------------------------------
# FollowTheMoney/OpenOSINT/Vitni semantics adopted as concepts only (FR-014).

class StatementProvenanceError(ConstraintViolation):
    """FR-001: every statement must carry dataset_id, extraction_version, original_value."""

    def __init__(self, statement_id: str = "unknown", missing: str = "") -> None:
        detail = f"Statement {statement_id} missing required provenance field(s): {missing}"
        super().__init__("FR-001", detail)


class CorrelationNoMergeError(ConstraintViolation):
    """I-2: correlation edges never auto-merge candidates into entities."""

    def __init__(
        self, detail: str = "Correlation edge cannot auto-merge candidates into entities"
    ) -> None:
        super().__init__("I-2", detail)


class ReviewAppendOnlyError(ConstraintViolation):
    """FR-006: analyst review decisions are append-only provenance."""

    def __init__(self, review_id: str = "unknown") -> None:
        super().__init__("FR-006", f"Review {review_id} is immutable; mutation rejected")


_REQUIRED_STATEMENT_FIELDS = ("dataset_id", "extraction_version", "original_value")


def enforce_statement_provenance(statement: dict) -> dict:
    """FR-001: every statement must carry the FTM-style provenance fields."""
    missing = [f for f in _REQUIRED_STATEMENT_FIELDS if not statement.get(f)]
    if missing:
        raise StatementProvenanceError(
            statement.get("statement_id", "unknown"), ", ".join(missing)
        )
    return statement


def enforce_correlation_no_merge(edge: dict) -> dict:
    """I-2: a correlation edge must never carry an auto-merge instruction."""
    if edge.get("auto_merge") is True or edge.get("merge") is True:
        raise CorrelationNoMergeError(
            f"Correlation edge {edge.get('edge_id', 'unknown')} cannot trigger a merge; "
            "identity comes only from admitted assertions"
        )
    return edge


_IMMUTABLE_REVIEW_FIELDS = ("decision", "target_type", "target_id", "analyst_id", "reviewed_at")


def enforce_review_append_only(existing: dict, update: dict) -> dict:
    """FR-006: an existing review decision cannot be mutated in place."""
    changed = [
        k for k in _IMMUTABLE_REVIEW_FIELDS
        if k in update and update.get(k) != existing.get(k)
    ]
    if changed:
        raise ReviewAppendOnlyError(existing.get("review_id", "unknown"))
    return existing