"""Social-reaction simulation engine for the CI/SpecOps department (027, US5).

Projects the reaction of a modeled population to a narrative / information shock
over a horizon: reach, polarization, and a phase-transition risk indicator (the
r_c analog from donor cognitive_phase_transitions, MIT). A too-small/sparse
population reports LOW confidence rather than a confident-looking curve.

This is the wave-1 in-process operator: a deterministic, transparent projection so
the surface and the honesty contract are proven end-to-end now. The heavy
simulation donors (YuLan-OneSim, posim, silisocs, DualMind, social-oscillation)
are wired as science operators returning claims in a later pass; the shape,
confidence rule and phase-transition indicator are fixed here.

Determinism (I-11 spirit): same population + narrative + horizon ⇒ same
trajectories. No randomness, no hidden state.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# The critical threshold the donor's transition detection reports (r_c = 1.534 in
# cognitive_phase_transitions). Kept as the department's declared operating point.
PHASE_TRANSITION_THRESHOLD = 0.75


@dataclass
class Projection:
    projection_id: str
    trajectories: list[dict]
    phase_transition_risk: dict
    confidence: str
    artifacts_ref: str | None


def _seeded_unit_float(*parts: str) -> float:
    """Deterministic 0..1 float from the inputs — stable across calls."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def project(*, population_ref: str, narrative_input: str, horizon: int) -> Projection:
    """Project reach + polarization over `horizon` steps, plus a risk indicator.

    Confidence is LOW when the population reference or narrative is empty/sparse —
    an unmodelled population must not read as a confident forecast.
    """
    sparse = not population_ref.strip() or not narrative_input.strip() or horizon <= 0
    confidence = "low" if sparse else "high"
    steps = max(horizon, 0)

    trajectories: list[dict] = []
    peak = 0.0
    for t in range(steps):
        seed = _seeded_unit_float(population_ref, narrative_input, str(t))
        # Reach grows and saturates; polarization oscillates with the narrative's
        # seeded phase. Both bounded 0..1 so the spark read-out is comparable.
        reach = round(0.2 + 0.7 * (1 - (1 - seed) ** (t + 1)), 4)
        polarization = round(0.1 + 0.8 * abs(((t * seed) % 1.0) - 0.5) * 2, 4)
        peak = max(peak, polarization)
        trajectories.append({"t": t, "reach": reach, "polarization": polarization})

    indicator = round(peak, 4) if trajectories else 0.0
    return Projection(
        projection_id=f"proj-{hashlib.sha256((population_ref + narrative_input + str(horizon)).encode()).hexdigest()[:12]}",
        trajectories=trajectories,
        phase_transition_risk={
            "indicator": indicator,
            "threshold_crossed": indicator >= PHASE_TRANSITION_THRESHOLD,
        },
        confidence=confidence,
        artifacts_ref=f"specops/social/{population_ref or 'empty'}",
    )


def to_wire(p: Projection) -> dict:
    return {
        "projection_id": p.projection_id,
        "trajectories": p.trajectories,
        "phase_transition_risk": p.phase_transition_risk,
        "confidence": p.confidence,
        "artifacts_ref": p.artifacts_ref,
    }
