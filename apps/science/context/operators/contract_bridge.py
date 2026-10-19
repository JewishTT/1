"""Bridge a science `OperatorResult` into the canonical envelope (FR-014, WP2/F1).

The WP0 capability matrix found two types named `OperatorResult`: the contract in
`apps/shared/contracts/operator_result.py` (51 tests, no production importer) and the
science-local one in `context/operators/base.py`, which the adapters actually return.

They are not duplicates. The science type records **what one calculation produced**;
the contract records **one operator run over one input set for one tenant**, with the
replay identity, the evidence refs, the cost and the status vocabulary a consumer
needs three services away. The science type cannot answer the contract's questions
because it was never given the context to.

That is exactly why this bridge exists in this shape: it **requires** the missing
context as arguments instead of inventing defaults. A conversion that filled in
`tenant_id=""` or an empty `artifact_refs` would satisfy the type checker and violate
the contract's own validation table, and the failure would surface at the far end of
the pipeline where nothing can be repaired.

What the bridge can map, it maps — and says so:

* `Determinism` → `ReplayMode`: the four replay classes collapse onto the contract's
  two, because the contract asks one question ("can recomputation reproduce the
  digest?") and `EXACT`, `FIXED_POINT` and `FLOAT_QUANTIZED` all answer yes.
* A deferred result → `BLOCKED`, with the deferral reason carried as
  `binding_limit`. Deferred is not a result and must not wear a success status.
* The replay key comes from :meth:`OperatorResult.compute_replay_key`, so the bridge
  cannot drift from the contract's rule that the wall clock is not an input.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from contracts.canonical import digest_of
from contracts.operator_result import (
    CostVector,
    OperatorIdentity,
    OperatorInputs,
    OperatorMethod,
    OperatorOutput,
    OperatorResult as ContractOperatorResult,
    OperatorResultError,
    ReplayMode,
)
from contracts.stage_outcome import StageStatus

from .base import Determinism, OperatorResult as ScienceOperatorResult

__all__ = [
    "DEFERRED_STATUS",
    "replay_mode_for",
    "to_operator_result",
]

#: A deferred science result has not run. `BLOCKED` is the contract's word for
#: "the work could not be attempted", which is what deferral means.
DEFERRED_STATUS = StageStatus.BLOCKED

#: The replay class of each science determinism level.
_REPLAY_MODES: dict[Determinism, ReplayMode] = {
    Determinism.EXACT: ReplayMode.DETERMINISTIC,
    # A fixed-point or quantised result is reproducible by construction: the
    # quantisation is part of the method, not noise around it.
    Determinism.FIXED_POINT: ReplayMode.DETERMINISTIC,
    Determinism.FLOAT_QUANTIZED: ReplayMode.DETERMINISTIC,
    # No recomputation guarantee exists, so the recorded result IS the evidence.
    Determinism.NON_DETERMINISTIC: ReplayMode.RESULT_REPLAY,
}


def replay_mode_for(determinism: Determinism) -> ReplayMode:
    """The contract's replay class for a science determinism level.

    Refuses rather than defaults: an unrecognised determinism value means the two
    vocabularies have diverged, and guessing would record a replay guarantee nobody
    can honour.
    """
    try:
        return _REPLAY_MODES[Determinism(determinism)]
    except (KeyError, ValueError) as exc:
        raise OperatorResultError(
            f"unknown determinism {determinism!r}; the science vocabulary and the contract's "
            "replay modes have diverged and a guess here would record a guarantee that does "
            "not exist"
        ) from exc


def to_operator_result(
    result: ScienceOperatorResult,
    *,
    identity: OperatorIdentity,
    inputs: OperatorInputs,
    output: OperatorOutput,
    started_at: datetime,
    parameters: dict[str, Any] | None = None,
    status: StageStatus | None = None,
    model_fingerprint: str | None = None,
    error_code: str | None = None,
    completed_at: datetime | None = None,
    cost: CostVector | None = None,
    warnings: tuple[str, ...] = (),
    missingness: tuple[str, ...] = (),
    uncertainty: dict[str, Any] | None = None,
    source_times: tuple[Any, ...] = (),
) -> ContractOperatorResult:
    """Convert one science result into the canonical envelope.

    The keyword-only arguments are the context the science result does not carry.
    They are required, not defaulted: a caller that cannot name its tenant, its
    inputs or its artifact cannot produce a contract result, and the constructor
    should say so here rather than three services later.

    ``status`` defaults to ``SUCCEEDED`` for a non-deferred result and to
    ``BLOCKED`` for a deferred one. A caller may override it — an operator that
    parsed nothing returns ``NO_RESULT`` even though it was not deferred — but the
    contract will refuse a success status without an output digest and artifact.

    ``model_fingerprint`` is required by the contract whenever the result is not
    deterministic: a non-deterministic run with no declared model cannot be replayed,
    audited or attributed. The bridge refuses to invent one, so a caller that cannot
    name its model gets the contract error rather than a fabricated attribution.

    ``error_code`` is required by the contract on ``BLOCKED``. A deferred result
    defaults to ``CAPABILITY_UNAVAILABLE`` — deferral means the capability could not
    be exercised here — and a caller with a more precise code passes it.
    """
    if result.deferred and status is None:
        status = DEFERRED_STATUS
    resolved_status = StageStatus(status) if status is not None else StageStatus.SUCCEEDED
    resolved_error = error_code
    if resolved_error is None and resolved_status is DEFERRED_STATUS:
        resolved_error = "CAPABILITY_UNAVAILABLE"

    replay_mode = replay_mode_for(result.determinism)
    params = dict(parameters or {})

    method = OperatorMethod(
        method_fingerprint=result.method_fingerprint or result.dependency_fingerprint,
        parameters_fingerprint=digest_of(params),
        deterministic=replay_mode is ReplayMode.DETERMINISTIC,
        replay_mode=replay_mode,
        replay_key=ContractOperatorResult.compute_replay_key(
            tenant_id=identity.tenant_id,
            scope_ref=identity.investigation_id,
            input_digests=inputs.input_digests,
            operator_id=result.operator_id,
            operator_version=result.operator_version,
            parameters=params,
            model_fingerprint=model_fingerprint,
            semantic_profile_ref=inputs.semantic_profile_ref,
            time_scope=inputs.time_scope,
        ),
        model_fingerprint=model_fingerprint,
    )

    return ContractOperatorResult(
        identity=identity,
        inputs=inputs,
        output=output,
        method=method,
        status=resolved_status,
        started_at=started_at,
        completed_at=completed_at,
        error_code=resolved_error,
        warnings=tuple(warnings) + ((result.deferral_reason,) if result.deferred else ()),
        missingness=tuple(missingness),
        binding_limit=result.deferral_reason if result.deferred else "",
        uncertainty=dict(uncertainty or {}),
        source_times=tuple(source_times),
        cost=cost or CostVector(),
    )
