"""Causal model + conclusion (T109, US3; data-model §6–7, FR-006/FR-007).

A ``CausalModel`` declares a directed influence graph, explicitly named and
controlled confounders, stated assumptions, and the outcome classes it may
explain. Scope declarations are validated at creation: the person-level
sensitive classes are hard-excluded and rejected (``ScopeBoundaryError``) so
no model can ever be registered that scores people by sensitive attributes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum

from causal.scope import FORBIDDEN_CLASSES, ensure_scoped
from claims.model import EvidenceLink
from errors import ScopeBoundaryError


class CausalLabel(StrEnum):
    """FR-006: a conclusion is either correlational or declaration-backed causal."""

    CORRELATIONAL = "correlational"
    CAUSAL = "causal"


@dataclass(frozen=True)
class CausalModel:
    model_id: str
    graph: dict[str, list[str]]
    confounders: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    scope_decl: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        for scope_class in self.scope_decl:
            if scope_class in FORBIDDEN_CLASSES or _looks_forbidden(scope_class):
                raise ScopeBoundaryError(scope_class)
        unknown = [c for c in self.confounders if c not in self.graph]
        if unknown:
            raise ValueError(f"confounders not in graph: {unknown}")

    def declares(self, outcome_attribute: str) -> bool:
        return outcome_attribute in self.scope_decl


def _looks_forbidden(scope_class: str) -> bool:
    try:
        ensure_scoped(scope_class, entry_point="causal.model.scope_validation")
        return False
    except ScopeBoundaryError:
        return True


@dataclass(frozen=True)
class CausalConclusion:
    conclusion_id: str
    label: CausalLabel
    model_ref: str | None
    controlled_confounders: list[str]
    assumptions: list[str]
    possible_confounders: list[str]
    evidence_links: list[EvidenceLink]

    def to_ref(self) -> dict[str, object]:
        return {
            "conclusion_id": self.conclusion_id,
            "label": self.label.value,
            "model_ref": self.model_ref,
            "controlled_confounders": self.controlled_confounders,
            "assumptions": self.assumptions,
            "possible_confounders": self.possible_confounders,
            "evidence_refs": [link.link_id for link in self.evidence_links],
        }


def _conclusion_id(evidence: list[EvidenceLink], model_ref: str | None) -> str:
    digest = hashlib.sha256(
        f"{model_ref or 'correlational'}|{'|'.join(l.link_id for l in evidence)}".encode()
    ).hexdigest()[:12]
    return f"CS-{digest}"