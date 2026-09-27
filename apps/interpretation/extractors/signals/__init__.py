"""Relation signals: what producers saw, before anyone decided what it means.

Feature 019. The package is the substrate every relation producer writes to, and the
reason it exists is in :mod:`~extractors.signals.signal`: extraction previously had one
extension point - a table of lexical cues - so the platform could notice a phrase joining
two words and nothing else.
"""

from extractors.signals.signal import (
    SIGNAL_ID_PREFIX,
    SIGNAL_KINDS,
    STRUCTURAL_SIGNAL_KINDS,
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
    assert_bounded,
    dedupe_by_content,
)

__all__ = [
    "SIGNAL_ID_PREFIX",
    "SIGNAL_KINDS",
    "STRUCTURAL_SIGNAL_KINDS",
    "DirectionHypothesis",
    "Neighbourhood",
    "RelationSignal",
    "SignalContractError",
    "SignalKind",
    "assert_bounded",
    "dedupe_by_content",
]
