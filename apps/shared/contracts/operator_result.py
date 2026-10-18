"""``OperatorResult`` -- the one envelope every derived artifact travels in.

Spec 030 contract 01 / FR-007, FR-047, FR-065, FR-100, FR-111 / task T029.

A result's **provenance, method, cost, uncertainty and failure state** travel with it
everywhere. That is the point: a derived artifact that can be read without its provenance is an
assertion wearing the costume of a finding, and once the envelope is separated from the payload
every reader has to guess which of several runs produced the thing in front of them.

**The validation table in contract 01 is enforced at construction.** Every row is a refusal:

* ``output_digest`` required iff ``status ∈ {succeeded, partial}`` -- R1: an empty output is
  never a status. A parser that cannot process a format returns ``unsupported``; it does not
  return a zero-length document with ``status = succeeded``. ``artifact_refs`` is non-empty on
  the same two statuses, because a digest over nothing plus a success is exactly the
  "empty output carrying a status" this envelope exists to end.
* ``error_code`` required on ``{failed, blocked, quarantined}`` and **absent** on the success
  statuses. It is additionally *permitted* on ``unsupported`` and ``no_result``: contract 01's
  own worked example for an unsupported parser carries ``CAPABILITY_UNAVAILABLE``, and a spec
  whose example violates its own table has to be read with the example honoured.
* ``deterministic = True`` implies ``replay_mode = deterministic`` **and**
  ``model_fingerprint = null``. A deterministic operator that loaded a model is not
  deterministic, and one that claims otherwise cannot be replayed.
* ``completed_at >= started_at``; input ids parallel to input digests; ``tenant_id`` non-empty.
* Cost components absent are ``null``, not omitted (R3) -- ``CostVector`` makes every component
  a declared field so "missing" and "measured as zero" cannot be confused.
* ``uncertainty`` is a keyed map whose values may be ``None``. ``0.0`` means measured as zero;
  ``None`` means not measured. They are different facts.

**R2: the replay key excludes the wall clock.** :meth:`OperatorResult.compute_replay_key` derives
it from tenant/scope, the logical input digest set, operator + version, canonical parameters,
model version, semantic profile and time scope -- and never from ``started_at``. Two runs of the
same operator over the same inputs are the same run for replay purposes even when they happened
an hour apart. Inverting that is how a replay ledger becomes a table of timestamps.

**R4: donors emit; the platform writes.** Nothing here performs I/O. The receiving service does
the write, which is why this module has no store, no session and no client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from contracts.canonical import digest_of, instant_text, normalize_instant
from contracts.error_codes import ErrorCode
from contracts.evidence_span import EvidenceSpanRef
from contracts.stage_outcome import StageStatus

__all__ = [
    "CapacityGap",
    "CostVector",
    "OperatorIdentity",
    "OperatorInputs",
    "OperatorMethod",
    "OperatorOutput",
    "OperatorResult",
    "OperatorResultError",
    "ReplayMode",
    "SourceTime",
    "TimePrecision",
    "SUCCESS_STATUSES",
    "ERROR_STATUSES",
    "DERIVED_OUTPUT_KINDS",
]

#: The two statuses that mean "an output exists and is content-addressed".
SUCCESS_STATUSES = frozenset({StageStatus.SUCCEEDED, StageStatus.PARTIAL})

#: The three statuses that must say why they failed.
ERROR_STATUSES = frozenset(
    {StageStatus.FAILED, StageStatus.BLOCKED, StageStatus.QUARANTINED}
)

#: Output kinds that are *definitionally* derived from raw content. A succeeded or partial
#: result carrying one of these cannot disclaim its source content and declare
#: ``derives_from_raw_content=False``; everything else is a judgement the caller makes and
#: ``missingness`` has to justify. This set is a floor, not the complete list of kinds that need
#: evidence -- treating it as the complete list would let any unlisted kind through ungrounded.
#:
#: The check lives on :class:`OperatorResult` rather than here because only the status
#: distinguishes "this operator ran and produced a layout" from "this operator could not process
#: the format", and the second legitimately has no evidence and no raw content behind it.
DERIVED_OUTPUT_KINDS = frozenset(
    {"derived", "extracted", "assertion_candidates", "features", "document_layout"}
)


class OperatorResultError(ValueError):
    """An operator result says something its own fields do not support.

    Raised at construction rather than defaulted. The default reading of a malformed envelope
    is the status it names, and every status here is a distinct claim about the world.
    """


class ReplayMode(StrEnum):
    """Two replay modes, declared (R2).

    ``DETERMINISTIC`` -- a pure function of the fingerprinted inputs, so recomputation must
    reproduce the recorded output digest. ``RESULT_REPLAY`` -- model-hosted or otherwise
    non-deterministic, so the exact returned result is preserved and the system states plainly
    that recomputation is not possible. The third thing people want -- "we'll figure it out
    later" -- is not a mode and is not available.
    """

    DETERMINISTIC = "deterministic"
    RESULT_REPLAY = "result_replay"


class TimePrecision(StrEnum):
    """Declared precision of a source-time fact. Never collapsed into a single datetime."""

    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"
    SECOND = "second"
    MICROSECOND = "microsecond"


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    """Who ran, at which version, for which tenant and investigation."""

    operator_id: str
    operator_version: str
    tenant_id: str
    investigation_id: str
    policy_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("operator_id", "operator_version", "policy_fingerprint"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise OperatorResultError(f"identity.{name} is required")
            object.__setattr__(self, name, value)
        tenant_id = str(self.tenant_id).strip()
        if not tenant_id:
            raise OperatorResultError(
                "identity.tenant_id is required and non-empty; an operator result with no "
                "tenant scope can be read across tenants (FR-090)"
            )
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "investigation_id", str(self.investigation_id).strip())


@dataclass(frozen=True, slots=True)
class OperatorInputs:
    """The inputs, declared as ids **parallel to** digests.

    Parallel rather than nested, because a nested pair can be reordered, truncated or half
    populated and still parse. ``validate_parallel`` refuses any length mismatch at
    construction, which is where the check belongs: the moment the pairing goes wrong is the
    moment the operator result is created, not when somebody later tries to reproduce it.
    """

    input_observation_ids: tuple[str, ...] = ()
    input_digests: tuple[str, ...] = ()
    semantic_profile_ref: str = ""
    time_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "input_observation_ids", tuple(str(x).strip() for x in self.input_observation_ids)
        )
        object.__setattr__(
            self, "input_digests", tuple(str(x).strip() for x in self.input_digests)
        )
        object.__setattr__(self, "time_scope", tuple(str(x).strip() for x in self.time_scope))
        if not str(self.semantic_profile_ref).strip():
            raise OperatorResultError(
                "inputs.semantic_profile_ref is required -- it names the regime that produced "
                "this, and two runs under different regimes are not the same run"
            )
        object.__setattr__(
            self, "semantic_profile_ref", str(self.semantic_profile_ref).strip()
        )
        self.validate_parallel()

    def validate_parallel(self) -> None:
        if len(self.input_observation_ids) != len(self.input_digests):
            raise OperatorResultError(
                f"{len(self.input_observation_ids)} input observation ids against "
                f"{len(self.input_digests)} input digests; every id MUST have a matching digest "
                "at the same index, because a re-paired list re-attributes the output to "
                "content that did not produce it (FR-007)"
            )
        if any(not digest for digest in self.input_digests):
            raise OperatorResultError(
                "an input digest may not be blank; an unverified input digest makes the replay "
                "key unverifiable"
            )


@dataclass(frozen=True, slots=True)
class OperatorOutput:
    """What was produced. ``output_digest`` and ``artifact_refs`` are conditional on the status.

    ``evidence_refs`` may legitimately be empty for a pure aggregation over already-derived
    features -- but then ``missingness`` must carry the reason, because "this output has no
    source content" and "nobody attached the source content" are different claims (R7).
    """

    output_kind: str
    output_schema_version: str
    output_digest: str | None = None
    artifact_refs: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceSpanRef, ...] = ()
    derives_from_raw_content: bool = True

    def __post_init__(self) -> None:
        for name in ("output_kind", "output_schema_version"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise OperatorResultError(
                    f"output.{name} is required; output_kind is an OPEN vocabulary so any "
                    "non-empty label is legal, but there has to be one"
                )
            object.__setattr__(self, name, value)
        if self.output_digest is not None and not str(self.output_digest).strip():
            raise OperatorResultError(
                "output.output_digest, if supplied, must be a real digest; a blank string is "
                "not a digest and reads as absent"
            )
        object.__setattr__(self, "artifact_refs", tuple(str(x).strip() for x in self.artifact_refs))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if self.derives_from_raw_content and not self.evidence_refs:
            raise OperatorResultError(
                f"output_kind {self.output_kind!r} is declared to derive from raw content and "
                "MUST carry evidence refs; an empty evidence list renders the result grounded "
                "when it is not (FR-005, R7). Set derives_from_raw_content=False only if that "
                "is genuinely true, and say so in missingness."
            )


@dataclass(frozen=True, slots=True)
class OperatorMethod:
    """The method block. ``deterministic`` constrains ``model_fingerprint`` and ``replay_mode``."""

    method_fingerprint: str
    parameters_fingerprint: str
    deterministic: bool
    replay_mode: ReplayMode
    replay_key: str
    model_fingerprint: str | None = None

    def __post_init__(self) -> None:
        for name in ("method_fingerprint", "parameters_fingerprint"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise OperatorResultError(f"method.{name} is required")
            object.__setattr__(self, name, value)
        replay_key = str(self.replay_key).strip()
        if not replay_key:
            raise OperatorResultError(
                "method.replay_key is required; two deliveries of the same replay key produce "
                "one semantic effect, and without it there is nothing to deduplicate on (FR-065)"
            )
        object.__setattr__(self, "replay_key", replay_key)
        object.__setattr__(self, "replay_mode", ReplayMode(self.replay_mode))
        if self.model_fingerprint is not None:
            object.__setattr__(self, "model_fingerprint", str(self.model_fingerprint).strip())
        object.__setattr__(self, "deterministic", bool(self.deterministic))

        if self.deterministic:
            if self.model_fingerprint is not None:
                raise OperatorResultError(
                    "deterministic=True requires model_fingerprint=null; an operator that "
                    "loaded a model is not a pure function of its fingerprinted inputs and "
                    "cannot be replayed by recomputation (R2)"
                )
            if self.replay_mode is not ReplayMode.DETERMINISTIC:
                raise OperatorResultError(
                    f"deterministic=True requires replay_mode=deterministic, got "
                    f"{self.replay_mode.value}"
                )
        else:
            if self.replay_mode is ReplayMode.DETERMINISTIC:
                raise OperatorResultError(
                    "replay_mode=deterministic claims the output can be recomputed, but "
                    "deterministic=False says it cannot be; declare result_replay instead"
                )
            if not self.model_fingerprint:
                raise OperatorResultError(
                    "deterministic=False requires a model_fingerprint; a non-deterministic run "
                    "with no declared model cannot be replayed, audited or attributed"
                )


@dataclass(frozen=True, slots=True)
class SourceTime:
    """One typed source-time fact. NEVER folded into a single datetime (FR-020).

    ``precision`` is load-bearing: a source fact published on a date is not an instant, and
    storing it as one invites a range query to treat a whole day as measured to the nanosecond.
    """

    kind: str
    value: datetime
    precision: TimePrecision

    def __post_init__(self) -> None:
        kind = str(self.kind).strip()
        if not kind:
            raise OperatorResultError(
                "source_times[].kind is required; a timestamp with no named clock is one of the "
                "things FR-020 exists to separate"
            )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "precision", TimePrecision(self.precision))
        object.__setattr__(self, "value", normalize_instant(self.value))

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": instant_text(self.value),
            "precision": str(self.precision),
        }


@dataclass(frozen=True, slots=True)
class CostVector:
    """The cost components. Every one is a declared field, so absent means ``null``.

    Not omitted (R3): an omitted field and a ``null`` field look identical in a diff and mean
    different things -- one is "nobody measured", the other is "there is nothing here". The
    vector is the stored truth; a composite may be added by a versioned policy and must retain
    this vector underneath it.
    """

    network_io_bytes: int | None = None
    cpu_seconds: float | None = None
    memory_bytes: int | None = None
    model_tokens: int | None = None
    latency_ms: int | None = None
    storage_bytes: int | None = None
    retries: int | None = None
    expected_human_review_minutes: float | None = None
    licensing_cost: float | None = None
    policy_version: str = ""

    def __post_init__(self) -> None:
        integer_components = (
            "network_io_bytes",
            "memory_bytes",
            "model_tokens",
            "storage_bytes",
            "retries",
        )
        for name in integer_components:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise OperatorResultError(
                    f"cost.{name} must be a non-negative int or null (meaning not measured), "
                    f"got {value!r}"
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "network_io_bytes": self.network_io_bytes,
            "cpu_seconds": self.cpu_seconds,
            "memory_bytes": self.memory_bytes,
            "model_tokens": self.model_tokens,
            "latency_ms": self.latency_ms,
            "storage_bytes": self.storage_bytes,
            "retries": self.retries,
            "expected_human_review_minutes": self.expected_human_review_minutes,
            "licensing_cost": self.licensing_cost,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class CapacityGap:
    """An explicit "no operator can do this", never a weaker substitute (CE-I13).

    Lives **alongside** :class:`OperatorResult`, not in place of it. A registry lookup that
    cannot satisfy a required capability still produced a result -- a result saying the
    capability is absent, with the reason and the next action attached. Replacing the envelope
    with the gap loses the operator identity, which is the fact the gap is about.
    """

    capability_required: str
    gap_reason: str
    owner: str
    next_action: str
    capability_available: str | None = None
    status: str = "unsupported"
    substitution_attempted: bool = False

    def __post_init__(self) -> None:
        for name in ("capability_required", "gap_reason", "owner", "next_action"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise OperatorResultError(
                    f"capacity_gap.{name} is required; a gap with no next action is an excuse, "
                    "and a gap with no owner is nobody's problem"
                )
            object.__setattr__(self, name, value)
        status = str(self.status).strip()
        if status not in ("unsupported", "approximate"):
            raise OperatorResultError(
                f"capacity_gap.status must be 'unsupported' or 'approximate', got {status!r}"
            )
        object.__setattr__(self, "status", status)
        if self.substitution_attempted:
            raise OperatorResultError(
                "capacity_gap.substitution_attempted MUST be false; a registry lookup that "
                "cannot satisfy a required capability returns an explicit gap, never a weaker "
                "substitute (CE-I13)"
            )
        object.__setattr__(self, "substitution_attempted", False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability_required": self.capability_required,
            "capability_available": self.capability_available,
            "substitution_attempted": self.substitution_attempted,
            "status": self.status,
            "gap_reason": self.gap_reason,
            "owner": self.owner,
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class OperatorResult:
    """The envelope. One per run of one operator over one input set, per tenant.

    Everything contract 01's validation table demands is checked in ``__post_init__``, so an
    invalid combination raises at construction rather than surfacing when a consumer reads it
    three services away.
    """

    identity: OperatorIdentity
    inputs: OperatorInputs
    output: OperatorOutput
    method: OperatorMethod
    status: StageStatus
    started_at: datetime
    completed_at: datetime | None = None
    error_code: ErrorCode | None = None
    warnings: tuple[str, ...] = ()
    missingness: tuple[str, ...] = ()
    binding_limit: str = ""
    resumable: bool | None = None
    uncertainty: dict[str, Any] = field(default_factory=dict)
    source_times: tuple[SourceTime, ...] = ()
    cost: CostVector = field(default_factory=CostVector)
    capacity_gap: CapacityGap | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", StageStatus(self.status))
        object.__setattr__(self, "started_at", normalize_instant(self.started_at))
        if self.completed_at is not None:
            object.__setattr__(self, "completed_at", normalize_instant(self.completed_at))
            if self.completed_at < self.started_at:
                raise OperatorResultError(
                    f"completed_at {instant_text(self.completed_at)} precedes started_at "
                    f"{instant_text(self.started_at)}; a run that finished before it started is "
                    "not a measurement"
                )
        if self.error_code is not None:
            object.__setattr__(self, "error_code", ErrorCode(self.error_code))
        object.__setattr__(self, "warnings", tuple(str(x) for x in self.warnings))
        object.__setattr__(self, "missingness", tuple(str(x) for x in self.missingness))
        object.__setattr__(self, "source_times", tuple(self.source_times))
        object.__setattr__(self, "uncertainty", dict(self.uncertainty))
        object.__setattr__(self, "binding_limit", str(self.binding_limit).strip())
        self.inputs.validate_parallel()
        self._validate_output_status_pairing()
        self._validate_error_pairing()
        self._validate_partial()
        self._validate_evidence()

    # -- the validation table ------------------------------------------------

    def _validate_output_status_pairing(self) -> None:
        """Row: ``output_digest`` present iff ``status ∈ {succeeded, partial}`` (R1)."""
        has_digest = bool(self.output.output_digest)
        if self.status in SUCCESS_STATUSES:
            if not has_digest:
                raise OperatorResultError(
                    f"status {self.status.value} requires output.output_digest; a run with no "
                    "digest produced nothing that can be cited, and 'nothing' is one of five "
                    "different states, not a success (R1)"
                )
            if not self.output.artifact_refs:
                raise OperatorResultError(
                    f"status {self.status.value} requires at least one artifact_ref; a digest "
                    "over an empty artifact list is an empty output carrying a success status"
                )
        elif has_digest:
            raise OperatorResultError(
                f"status {self.status.value} means no output was produced, so an "
                "output_digest is a claim about content that does not exist"
            )

    def _validate_error_pairing(self) -> None:
        """Row: ``error_code`` required iff the status means it did not happen.

        Note the asymmetry, which is deliberate and comes from contract 01 itself: required on
        ``{failed, blocked, quarantined}``, forbidden on the success statuses, and permitted on
        ``unsupported``/``no_result`` -- because contract 01's own worked example for an
        unsupported parser carries ``CAPABILITY_UNAVAILABLE``.
        """
        if self.status in ERROR_STATUSES and self.error_code is None:
            raise OperatorResultError(
                f"status {self.status.value} requires an error_code saying why; a failure with "
                "no code is a failure no retry policy can act on (FR-068)"
            )
        success_like = SUCCESS_STATUSES | {StageStatus.NO_CHANGE}
        if self.status in success_like and self.error_code is not None:
            raise OperatorResultError(
                f"status {self.status.value} is not a failure, so it cannot carry "
                f"error_code={self.error_code}; an error code on a success is a claim that "
                "something also went wrong, which is a different result"
            )

    def _validate_partial(self) -> None:
        """R6: partial is a first-class outcome and carries what it omitted (contract 03 r3)."""
        if self.status is not StageStatus.PARTIAL:
            return
        if not self.missingness:
            raise OperatorResultError(
                "status partial MUST carry missingness: what was processed, what was not, and "
                "the limit that bound it; partial and succeeded differ only by whether the "
                "omitted scope travels with the result"
            )
        if not self.binding_limit:
            raise OperatorResultError(
                "status partial MUST name the binding limit; a partial with no named limit "
                "cannot be resumed and cannot be re-planned"
            )
        if self.resumable is None:
            raise OperatorResultError(
                "status partial MUST declare whether the residual is resumable; an unestimated "
                "boolean is an omission, not an answer"
            )

    def _validate_evidence(self) -> None:
        """R7: declared provenance completeness, not assumed (FR-005)."""
        if self.output.evidence_refs:
            return
        if self.status in SUCCESS_STATUSES:
            if (
                not self.output.derives_from_raw_content
                and self.output.output_kind in DERIVED_OUTPUT_KINDS
            ):
                raise OperatorResultError(
                    f"status {self.status.value} with output_kind "
                    f"{self.output.output_kind!r} and no evidence refs cannot declare "
                    "derives_from_raw_content=False; that kind derives from raw content by "
                    "definition, and an empty evidence list on it renders the result grounded "
                    "when it is not (FR-005)"
                )
            if not self.missingness:
                raise OperatorResultError(
                    "a succeeded/partial result with no evidence refs MUST carry the reason in "
                    "missingness; 'the output has no source content' and 'nobody attached the "
                    "source content' are different claims and only one of them is a finding"
                )
        if self.status is StageStatus.UNSUPPORTED and self.capacity_gap is None:
            raise OperatorResultError(
                "status unsupported with no evidence refs must carry a CapacityGap saying which "
                "capability is missing and what would fix it (CE-I13)"
            )

    # -- derived -------------------------------------------------------------

    @property
    def is_successful(self) -> bool:
        return self.status in SUCCESS_STATUSES

    @property
    def is_deterministic(self) -> bool:
        return self.method.deterministic

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": {
                "operator_id": self.identity.operator_id,
                "operator_version": self.identity.operator_version,
                "tenant_id": self.identity.tenant_id,
                "investigation_id": self.identity.investigation_id,
                "policy_fingerprint": self.identity.policy_fingerprint,
            },
            "inputs": {
                "input_observation_ids": list(self.inputs.input_observation_ids),
                "input_digests": list(self.inputs.input_digests),
                "semantic_profile_ref": self.inputs.semantic_profile_ref,
                "time_scope": list(self.inputs.time_scope),
            },
            "output": {
                "output_kind": self.output.output_kind,
                "output_schema_version": self.output.output_schema_version,
                "output_digest": self.output.output_digest,
                "artifact_refs": list(self.output.artifact_refs),
                "evidence_refs": [ref.as_dict() for ref in self.output.evidence_refs],
            },
            "method": {
                "method_fingerprint": self.method.method_fingerprint,
                "parameters_fingerprint": self.method.parameters_fingerprint,
                "model_fingerprint": self.method.model_fingerprint,
                "deterministic": self.method.deterministic,
                "replay_key": self.method.replay_key,
                "replay_mode": str(self.method.replay_mode),
            },
            "outcome": {
                "status": str(self.status),
                "error_code": str(self.error_code) if self.error_code else None,
                "warnings": list(self.warnings),
                "missingness": list(self.missingness),
                "binding_limit": self.binding_limit,
                "resumable": self.resumable,
                "uncertainty": dict(self.uncertainty),
            },
            "time": {
                "started_at": instant_text(self.started_at),
                "completed_at": (
                    instant_text(self.completed_at) if self.completed_at is not None else None
                ),
                "source_times": [item.as_dict() for item in self.source_times],
            },
            "cost": self.cost.as_dict(),
            "capacity_gap": self.capacity_gap.as_dict() if self.capacity_gap else None,
        }

    # -- R2: the replay key --------------------------------------------------

    @classmethod
    def compute_replay_key(
        cls,
        *,
        tenant_id: str,
        scope_ref: str,
        input_digests: tuple[str, ...] | list[str],
        operator_id: str,
        operator_version: str,
        parameters: dict[str, Any],
        model_fingerprint: str | None,
        semantic_profile_ref: str,
        time_scope: tuple[str, ...] | list[str] = (),
    ) -> str:
        """Derive the replay key from the declared logical inputs -- never the wall clock.

        The wall clock is excluded on purpose. A run that happened at 09:12 and the same run
        that happened at 11:40 are the same run for every purpose replay serves; including the
        timestamp would give each execution its own key, and a replay ledger keyed on execution
        time deduplicates nothing. Include it only when the timestamp is semantically part of
        the input, which is what ``time_scope`` is for.
        """
        return digest_of(
            {
                "tenant_id": str(tenant_id).strip(),
                "scope_ref": str(scope_ref).strip(),
                "input_digests": sorted(str(d).strip() for d in input_digests),
                "operator_id": str(operator_id).strip(),
                "operator_version": str(operator_version).strip(),
                "parameters": parameters,
                "model_fingerprint": model_fingerprint,
                "semantic_profile_ref": str(semantic_profile_ref).strip(),
                "time_scope": sorted(str(t).strip() for t in time_scope),
            }
        )