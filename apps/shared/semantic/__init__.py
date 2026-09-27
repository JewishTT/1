"""Semantic Fabric: ontologies as external semantic tools, never as foundation.

Feature 017. This package attaches vocabularies, mappings, profiles and
constraints *beside* the graph so the platform can use external semantic
resources without letting them become its language.

The public surface is deliberately three names - :class:`SemanticRef`,
:class:`RelationRef`, :class:`ValidationReport` - because that is the whole
contract the core domain is allowed to depend on (FR-005). Importing anything
else from here into ``domain`` is a defect, not a style choice.

Submodules are imported lazily where they pull in optional capability, so that
``import semantic`` stays cheap and dependency-free.
"""

from semantic.contracts import (
    RelationRef,
    SemanticRef,
    SemanticStatus,
    TypeAssertion,
    TypeScope,
    ValidationFinding,
    ValidationReport,
    ValidationStage,
    Verdict,
    content_key,
    is_adverse,
)

__all__ = [
    "RelationRef",
    "SemanticRef",
    "SemanticStatus",
    "TypeAssertion",
    "TypeScope",
    "ValidationFinding",
    "ValidationReport",
    "ValidationStage",
    "Verdict",
    "content_key",
    "is_adverse",
]
