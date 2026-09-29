"""Relation signals: what producers saw, before anyone decided what it means.

Features 019 and 021. The package is the substrate every relation producer writes to, and the
reason it exists is in :mod:`~extractors.signals.signal`: extraction previously had one
extension point - a table of lexical cues - so the platform could notice a phrase joining
two words and nothing else.

Phase 021 Phase 4A made the substrate natively n-ary and made it say *why* it looked.
:class:`RelationParticipant` and :class:`SignalBasis` are defined in ``apps/shared/domain`` -
they are value types the candidate layer needs as much as the signal layer does - and
re-exported here so a producer has one import for the whole contract.
"""

from domain.relation_participant import ParticipantContractError, RelationParticipant
from domain.signal_basis import SignalBasis

from extractors.signals.signal import (
    SIGNAL_BASES,
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
    "SIGNAL_BASES",
    "SIGNAL_ID_PREFIX",
    "SIGNAL_KINDS",
    "STRUCTURAL_SIGNAL_KINDS",
    "DirectionHypothesis",
    "Neighbourhood",
    "ParticipantContractError",
    "RelationParticipant",
    "RelationSignal",
    "SignalBasis",
    "SignalContractError",
    "SignalKind",
    "assert_bounded",
    "dedupe_by_content",
]
