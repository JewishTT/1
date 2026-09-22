"""Zero-layer: any input to contacts pipeline (spec/010, NO AI).

Top-level package ``zero`` exposes the deterministic contact-harvesting
pipeline: Layer 1 type detection → harvest modules → Layer 2 Fellegi-Sunter
entity resolution → Layer 3 enrichment + feedback, all emitting immutable
observations through ``zero.observation_gate``. Everything is deterministic
stdlib-conform logic (regex + heuristics + probabilistic matching); this layer
never calls an LLM (Layer 0 constitution, spec §0.1).

   Source lessons: donors/theHarvester, donors/sherlock, donors/maigret,
   donors/Email-Permutator, donors/gitsnitch — all vendored as thin adapters,
   licensed MIT, see per-module docstrings.
"""

from __future__ import annotations

from .harvest_wave import HarvestWave, WaveSummary
from .harvesters.contracts import CommandSpec, HarvestResult, ObservationCandidate
from .observation_gate import ZeroLayerGate, ZeroLayerObservation
from .resolution.fellegi_sunter import FellegiSunter
from .resolution.similarity import jaro_winkler, levenshtein
from .type_detector import InputType, SeedInput, TypeCandidate, TypeDetector

__all__ = [
    "CommandSpec",
    "FellegiSunter",
    "HarvestResult",
    "HarvestWave",
    "InputType",
    "ObservationCandidate",
    "SeedInput",
    "TypeCandidate",
    "TypeDetector",
    "WaveSummary",
    "ZeroLayerGate",
    "ZeroLayerObservation",
    "jaro_winkler",
    "levenshtein",
]