"""Translation from an anchored science verdict to a context signal.

Two vocabularies describe the same fact and neither was derived from the other.
``anchoring.EvaluationStatus`` is ``IDENTIFIED / ESTIMATED / REFUTED /
INCONCLUSIVE``. ``context_engine.loop.ScienceOutcome`` is ``SUPPORTED / REFUTED /
DRIFTED / INCONCLUSIVE``. ``loop.py`` even names the anchoring contract in its
docstring and then defines its own dataclass instead of using it, so nothing
enforced agreement between the two and a refutation could have been silently
read as support.

This module is the single place that maps one onto the other, on the science
side, so ``control-plane`` consumes a plain payload instead of importing
``anchoring``. The mapping is deliberately lossy in one direction and explicit
about it:

* ``REFUTED`` is the only verdict that becomes a contradiction.
* ``ESTIMATED`` becomes ``DRIFTED`` when a drift was actually measured and is
  outside the declared tolerance -- or when a drift was measured and no tolerance
  was declared, since then no one can certify it as acceptable. An estimate with
  no drift measurement is support: there is nothing out of bounds.
* ``IDENTIFIED`` and an acceptable ``ESTIMATED`` are support, which produces no
  signal: a settled question must not generate new obligations.
"""

from __future__ import annotations

from typing import Any

from anchoring import EvaluationStatus, ScienceEvaluation

#: Mirrors ``context_engine.loop.ScienceOutcome``. Spelled as literals because
#: that module sits in a layer this one must not import.
SUPPORTED = "supported"
REFUTED = "refuted"
DRIFTED = "drifted"
INCONCLUSIVE = "inconclusive"


def outcome_of(evaluation: ScienceEvaluation) -> str:
    """The context-engine outcome for one anchored verdict."""
    status = evaluation.status
    if status is EvaluationStatus.REFUTED:
        return REFUTED
    if status is EvaluationStatus.INCONCLUSIVE:
        return INCONCLUSIVE
    if status is EvaluationStatus.ESTIMATED:
        # Drift needs a measurement. `is_within_tolerance()` fails closed, so it
        # returns False both for "measured and outside" and for "nothing was
        # measured"; asking it alone would call an unmeasured estimate drifted.
        if evaluation.calibration_drift() is None:
            return SUPPORTED
        if not evaluation.is_within_tolerance():
            return DRIFTED
    return SUPPORTED


def feedback_payload(
    evaluation: ScienceEvaluation,
    *,
    claim_ref: str = "",
    detail: str = "",
) -> dict[str, Any]:
    """The wire shape ``control-plane`` turns into a ``ScienceFeedback``.

    ``claim_ref`` and ``detail`` are carried through when given, and otherwise
    recovered from the evaluation's own ``verdict``/``kind`` so a verdict is never
    anonymous on the wire.
    """
    return {
        "evaluation_id": evaluation.evaluation_id,
        "kind": evaluation.kind,
        "outcome": outcome_of(evaluation),
        "status": evaluation.status.value,
        "claim_ref": claim_ref or evaluation.verdict or evaluation.evaluation_id,
        "detail": detail or _describe(evaluation),
        "snapshot_id": evaluation.anchor.snapshot_id,
        "watermark": evaluation.anchor.watermark,
        "method_fingerprint": evaluation.method_fingerprint,
        "measurements": dict(evaluation.measurements),
        "tolerance": evaluation.tolerance,
        "within_tolerance": evaluation.is_within_tolerance(),
    }


def _describe(evaluation: ScienceEvaluation) -> str:
    """A short human-readable reason, preferring a recorded measurement."""
    drift = evaluation.calibration_drift()
    if drift is not None and evaluation.tolerance is not None:
        relation = "within" if evaluation.is_within_tolerance() else "outside"
        return f"drift={drift} {relation} tolerance={evaluation.tolerance}"
    if evaluation.verdict:
        return evaluation.verdict
    stages = [stage for stage, outcome in evaluation.stages.items() if outcome]
    if stages:
        return "stages: " + ", ".join(sorted(stages))
    return evaluation.kind
