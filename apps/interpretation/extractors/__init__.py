"""Extractor package (spec 007): deterministic, no-ML entity extraction.

Blind exports for the deterministic stack: persons, places,
organizations, sanctions dictionary entities, contacts and the
normalization post-pass (canonical forms + evidence).
"""

from __future__ import annotations

from .types import ExtractionResult, NormalizedName, TypedMention

__all__ = ["ExtractionResult", "NormalizedName", "TypedMention"]