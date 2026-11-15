"""Counterintelligence subject board engine for the CI/SpecOps department (027, US4).

Subjects carry tracked invariants — belief-state, narrative-position, bias-profile,
coordination-signature, phase-state — each with the evidence that supports it. The
load-bearing honesty rule (FR-008): an invariant with no evidence is UNSUPPORTED
and is rendered as such, never asserted. This engine is the wave-1 stand-in with a
small in-memory subject set; the cognitive operators (CognitiveAttack,
DIMA-OntoToolkit, io-coordinated-replies, IO-detecting) are wired to emit these as
claims in a later pass — the shape and the honesty contract are fixed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

INVARIANT_KINDS = (
    "belief-state",
    "narrative-position",
    "bias-profile",
    "coordination-signature",
    "phase-state",
)


@dataclass
class Invariant:
    kind: str
    value: str
    confidence: float | None
    evidence_refs: list[str] = field(default_factory=list)

    @property
    def supported(self) -> bool:
        return len(self.evidence_refs) > 0


@dataclass
class Subject:
    subject_id: str
    kind: str
    display: str
    invariants: list[Invariant] = field(default_factory=list)


class SubjectRegistry:
    """In-memory subject store seeded with one illustrative subject.

    The seed demonstrates the honesty contract: one invariant carries evidence
    (supported), one does not (unsupported) — so the board's rendering of both is
    exercised from the first load. A durable/operator-fed store is a later concern.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, Subject] = {}
        self._seed()

    def _seed(self) -> None:
        s = Subject(
            subject_id="subj-demo-1",
            kind="core:Person",
            display="Demo subject (seeded)",
            invariants=[
                Invariant("belief-state", "pro-X / anti-Y split", 0.62, ["obs-1001", "obs-1002"]),
                Invariant("narrative-position", "amplifier", 0.41, ["obs-1003"]),
                # Deliberately unsupported: no evidence yet — must render as such.
                Invariant("coordination-signature", "suspected inauthentic cluster", None, []),
            ],
        )
        self._by_id[s.subject_id] = s

    def get(self, subject_id: str) -> Subject | None:
        return self._by_id.get(subject_id)


REGISTRY = SubjectRegistry()


def to_wire(subject: Subject) -> dict:
    return {
        "subject_id": subject.subject_id,
        "kind": subject.kind,
        "display": subject.display,
        "invariants": [
            {
                "kind": inv.kind,
                "value": inv.value,
                "confidence": inv.confidence,
                "evidence_refs": list(inv.evidence_refs),
            }
            for inv in subject.invariants
        ],
        "relations": [],
    }
