"""``ResolutionDecision`` — append-only, supersession-based, with a surviving trail (T082, T083).

ADR-030-03 D1–D3, FR-080, FR-082. The 029 audit already found the shape used elsewhere in this
codebase (``engine/temporal.py`` supersede-by-reference, ``candidate.py`` reverse-appends); this
module is that idiom made explicit for identity, because identity is the case where getting it
wrong fuses two people irreversibly.

Three properties are load-bearing and each is enforced by the type rather than by convention:

**Decisions are frozen.** A :class:`ResolutionDecision` cannot be edited after it is constructed.
Not "is not edited" — cannot be. Soft-delete (``revoked_at``) was considered and rejected in
ADR-030-03 §B: the row survives, so it *looks* append-only, but the content stays mutable behind
the flag and "what did the system believe at time T" becomes a query that depends on the reader
remembering which flag to filter on.

**The store has no update and no delete.** There is no method here that rewrites a row, so the
append-only property does not depend on a caller being careful. Supersession is a *new row* that
points back at the old one by id; the old one stays readable forever.

**Corroboration is measured and the measure is named.** A decision that says "corroboration 2"
without saying whether that is two hosts or two lineage roots is unreadable: twenty mirrors of one
wire story on twenty domains are one source wearing twenty hats (WP-E T071, ``engine/intake.py``).
:data:`CORROBORATION_MEASURES` is closed — ``lineage_roots`` counts distinct origins,
``hosts`` counts distinct hostnames and is retained only so a reader can see what the weaker
measure says beside it, and ``none`` is an explicit "not measured" rather than a silent zero.

Competing hypotheses are first-class and are never collapsed by a decision (FR-080, T083). A
decision *selects among* retained hypotheses; it does not delete the ones it rejected, because
"we considered same-name-different-person and rejected it" is the sentence an auditor needs and
the sentence that cannot be reconstructed from a single surviving row.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from .span import EvidenceSpanRef, Grounding, grounding_of

__all__ = [
    "CORROBORATION_MEASURES",
    "ClaimBinding",
    "DecisionKind",
    "DecisionStore",
    "DecisionStoreError",
    "DuplicateDecision",
    "IdentityHypothesis",
    "MatcherProfile",
    "ResolutionDecision",
    "UnknownDecision",
]


class DecisionStoreError(RuntimeError):
    """The store refused a write or a read. Named so the refusal is the finding."""


class DuplicateDecision(DecisionStoreError):
    """A decision id already exists. Ids are content-free but unique; a collision is a bug."""


class UnknownDecision(DecisionStoreError):
    """A referenced decision does not exist."""


class DecisionKind(StrEnum):
    """What a decision *does*. Every kind is an append; none of them rewrites another."""

    MERGE = "merge"
    SPLIT = "split"
    NO_MATCH = "no_match"
    #: Not a resolution outcome: a pair that was surfaced and is deliberately undecided.
    REVIEW = "review"


#: The closed set of corroboration measures. Named on every decision (T080).
#: - ``lineage_roots``: distinct origins documents ultimately derive from. The only measure
#:   that may be cited as independence.
#: - ``hosts``: distinct hostnames. Retained so a reader sees the flattering number *and* the
#:   honest one; never sufficient on its own to raise corroboration.
#: - ``none``: deliberately not measured. An explicit hole beats an implicit zero.
CORROBORATION_MEASURES = frozenset({"lineage_roots", "hosts", "none"})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True, slots=True)
class MatcherProfile:
    """The matcher that produced the proposal, and what its profile says about itself.

    ``calibrated`` is a *declaration*, not a property this module infers from a score. A profile
    that declares itself uncalibrated has not been fitted against labelled pairs, whatever its
    thresholds look like — the same distinction ``engine/calibration.CalibrationProfile.is_calibrated``
    draws for the admission lane, carried through to the point where a merge is actually written.
    """

    name: str
    version: str
    calibrated: bool
    calibration_evidence: str = ""
    """What backs the calibration claim. Empty when uncalibrated, which is the honest default."""

    def __post_init__(self) -> None:
        if not self.name:
            raise DecisionStoreError("a matcher profile must name the matcher")
        if self.calibrated and not self.calibration_evidence:
            # A calibration claim with no referent is not a claim, it is a wish.
            raise DecisionStoreError(
                f"matcher {self.name!r} declares itself calibrated but names no evidence for it"
            )

    @classmethod
    def from_calibration_profile(cls, profile, *, name: str = "") -> MatcherProfile:
        """Adapt ``engine.calibration.CalibrationProfile`` without importing it at module scope."""
        return cls(
            name=name or f"admission-profile:{profile.entity_type}",
            version=str(profile.version or ""),
            calibrated=bool(profile.is_calibrated),
            calibration_evidence="" if not profile.is_calibrated else "admission-profile",
        )

    @property
    def declares_uncalibrated(self) -> bool:
        return not self.calibrated

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "calibrated": self.calibrated,
            "calibration_evidence": self.calibration_evidence,
        }


@dataclass(frozen=True, slots=True)
class IdentityHypothesis:
    """A proposed reading of a pair. Retained whatever any decision concludes (T083).

    ``statement`` is the hypothesis in words, because the difference between "same person" and
    "same name, different person" is the whole content of the case and it does not survive being
    flattened into a score.
    """

    hypothesis_id: str
    pair_key: str
    statement: str
    raised_by: str
    score: float | None = None
    score_semantics: str = ""
    """What ``score`` means. An uncalibrated weight with no probability reading says so here."""
    evidence_refs: tuple[str, ...] = ()
    span_refs: tuple[EvidenceSpanRef, ...] = ()
    raised_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.statement:
            raise DecisionStoreError("a hypothesis without a statement says nothing")

    @property
    def grounding(self) -> Grounding:
        return grounding_of(self.span_refs)

    def to_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "pair_key": self.pair_key,
            "statement": self.statement,
            "raised_by": self.raised_by,
            "score": self.score,
            "score_semantics": self.score_semantics,
            "evidence_refs": list(self.evidence_refs),
            "raised_at": self.raised_at,
            "grounding": self.grounding.value,
        }


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    """One append-only identity decision. Frozen: written once, read forever."""

    decision_id: str
    pair_key: str
    kind: DecisionKind
    supersedes: str | None = None
    hypothesis_id: str | None = None
    decided_by: str = ""
    """Who or what authored this decision. Empty is rejected — an unattributed decision has
    nobody to challenge it and nothing to reverse it against."""
    decided_at: str = field(default_factory=_now)
    matcher: MatcherProfile | None = None
    corroboration_measure: str = ""
    """REQUIRED. Which measure produced ``corroboration_value`` (T080)."""
    corroboration_value: int = 0
    corroboration_detail: Mapping[str, int | str] = field(default_factory=dict)
    rule_version: str = "identity-resolution-v1"
    rationale: str = ""
    evidence_refs: tuple[str, ...] = ()
    span_refs: tuple[EvidenceSpanRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise DecisionStoreError("decision_id is REQUIRED")
        if not self.pair_key:
            raise DecisionStoreError("pair_key is REQUIRED")
        if not self.decided_by:
            raise DecisionStoreError(
                "decided_by is REQUIRED: an identity decision with no author cannot be "
                "challenged or reversed against anybody"
            )
        if self.corroboration_measure not in CORROBORATION_MEASURES:
            raise DecisionStoreError(
                f"corroboration_measure must be one of {sorted(CORROBORATION_MEASURES)}, got "
                f"{self.corroboration_measure!r}. A measure that is not named is a number "
                "whose meaning has to be guessed (T080)"
            )
        if self.supersedes == self.decision_id:
            raise DecisionStoreError("a decision cannot supersede itself")
        if (
            self.kind is DecisionKind.MERGE
            and self.supersedes is None
            and not self.matcher
            and not self.evidence_refs
        ):
            # A merge with no matcher is a human merge; legal. A merge with neither a matcher
            # nor provenance is not, and this is the last cheap place to notice.
            raise DecisionStoreError(
                "a merge must carry evidence: a matcher profile, evidence refs, or both"
            )
        object.__setattr__(self, "corroboration_detail", MappingProxyType(dict(self.corroboration_detail)))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "span_refs", tuple(self.span_refs))

    @property
    def grounding(self) -> Grounding:
        return grounding_of(self.span_refs)

    @property
    def asserts_identity(self) -> bool:
        """Whether this decision, on its own, fuses two candidates."""
        return self.kind is DecisionKind.MERGE

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "pair_key": self.pair_key,
            "kind": self.kind.value,
            "supersedes": self.supersedes,
            "hypothesis_id": self.hypothesis_id,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "matcher": self.matcher.to_dict() if self.matcher else None,
            "corroboration_measure": self.corroboration_measure,
            "corroboration_value": self.corroboration_value,
            "corroboration_detail": dict(self.corroboration_detail),
            "rule_version": self.rule_version,
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
            "grounding": self.grounding.value,
        }


@dataclass(frozen=True, slots=True)
class ClaimBinding:
    """A claim, and the identity interpretation it was written under (ADR-030-03 D3).

    Written once. Re-interpreting identity does not rewrite the binding — it produces a *new*
    reading of the same claim under a new decision, and both readings stay available. That is
    FR-082's second clause, and it is the clause a mutable ``entity_id`` column destroys.
    """

    claim_id: str
    interpretation_id: str | None
    bound_at: str = field(default_factory=_now)
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "interpretation_id": self.interpretation_id,
            "bound_at": self.bound_at,
            "note": self.note,
        }


class DecisionStore:
    """Append-only identity decision log (FR-082).

    Deliberately has no ``update``, ``delete``, ``revoke`` or ``set_state``. There is nothing to
    call that would rewrite history, so the property cannot be forgotten at a call site.
    """

    def __init__(self) -> None:
        self._decisions: dict[str, ResolutionDecision] = {}
        self._order: list[str] = []
        self._superseded_by: dict[str, str] = {}
        self._hypotheses: dict[str, IdentityHypothesis] = {}
        self._bindings: list[ClaimBinding] = []

    # -- writes ---------------------------------------------------------------

    def append(self, decision: ResolutionDecision) -> ResolutionDecision:
        """Write one decision. Refuses to write over an existing id."""
        if decision.decision_id in self._decisions:
            raise DuplicateDecision(
                f"decision {decision.decision_id!r} already exists; append-only means append, "
                "and superseding is a new row (ADR-030-03 D1)"
            )
        if decision.supersedes is not None:
            prior = self._decisions.get(decision.supersedes)
            if prior is None:
                raise UnknownDecision(
                    f"cannot supersede {decision.supersedes!r}: it is not in this store"
                )
            if prior.pair_key != decision.pair_key:
                raise DecisionStoreError(
                    f"superseding a decision for {prior.pair_key!r} with one for "
                    f"{decision.pair_key!r} would move an interpretation across pairs"
                )
            if decision.supersedes in self._superseded_by:
                raise DecisionStoreError(
                    f"decision {decision.supersedes!r} is already superseded by "
                    f"{self._superseded_by[decision.supersedes]!r}; a chain, not a fork"
                )
        self._decisions[decision.decision_id] = decision
        self._order.append(decision.decision_id)
        if decision.supersedes is not None:
            self._superseded_by[decision.supersedes] = decision.decision_id
        return decision

    def record_hypothesis(self, hypothesis: IdentityHypothesis) -> IdentityHypothesis:
        """Retain a competing reading of a pair. Never removed, whatever a decision concludes."""
        if hypothesis.hypothesis_id in self._hypotheses:
            raise DuplicateDecision(f"hypothesis {hypothesis.hypothesis_id!r} already recorded")
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        return hypothesis

    def bind_claim(self, claim_id: str, interpretation_id: str | None, *, note: str = "") -> ClaimBinding:
        """Record which identity interpretation a claim was written under.

        ``interpretation_id`` is the decision in force *at write time*, or ``None`` when no
        decision existed yet — which is a real state (claims written before any merge is
        decided) and is stored as such rather than being back-filled later.
        """
        if interpretation_id is not None and interpretation_id not in self._decisions:
            raise UnknownDecision(f"cannot bind a claim to unknown decision {interpretation_id!r}")
        binding = ClaimBinding(claim_id=claim_id, interpretation_id=interpretation_id, note=note)
        self._bindings.append(binding)
        return binding

    # -- reads ----------------------------------------------------------------

    def get(self, decision_id: str) -> ResolutionDecision | None:
        return self._decisions.get(decision_id)

    def require(self, decision_id: str) -> ResolutionDecision:
        found = self._decisions.get(decision_id)
        if found is None:
            raise UnknownDecision(f"no decision {decision_id!r} in this store")
        return found

    def is_superseded(self, decision_id: str) -> bool:
        return decision_id in self._superseded_by

    def superseding(self, decision_id: str) -> ResolutionDecision | None:
        successor = self._superseded_by.get(decision_id)
        return self._decisions.get(successor) if successor else None

    def history(self, pair_key: str) -> tuple[ResolutionDecision, ...]:
        """Every decision ever written for this pair, oldest first. Nothing is filtered out."""
        return tuple(d for d in self._all() if d.pair_key == pair_key)

    def current(self, pair_key: str) -> ResolutionDecision | None:
        """The latest non-superseded decision for a pair (ADR-030-03 D2).

        A query over the log, never a stored column. That is what makes a split a first-class
        event rather than a deletion.
        """
        latest: ResolutionDecision | None = None
        for decision in self._all():
            if decision.pair_key == pair_key and not self.is_superseded(decision.decision_id):
                latest = decision
        return latest

    def current_identity(self, pair_key: str) -> tuple[str, str] | None:
        """The ``(candidate_a, candidate_b)`` the current decision fuses, or ``None``.

        Split by unpacking the pair key, which is how ``candidate.pair_key`` is built. Returning
        ``None`` after a split is the whole point: the pair is no longer one identity.
        """
        decision = self.current(pair_key)
        if decision is None or decision.kind is not DecisionKind.MERGE:
            return None
        return tuple(decision.pair_key.split("&&"))  # type: ignore[return-value]

    def merges_in_force(self) -> tuple[ResolutionDecision, ...]:
        return tuple(
            d
            for d in self._all()
            if d.kind is DecisionKind.MERGE and not self.is_superseded(d.decision_id)
        )

    def hypotheses(self, pair_key: str | None = None) -> tuple[IdentityHypothesis, ...]:
        found = self._hypotheses.values()
        if pair_key is None:
            return tuple(found)
        return tuple(h for h in found if h.pair_key == pair_key)

    def claim_binding(self, claim_id: str) -> ClaimBinding | None:
        """The interpretation a claim was *written* under. Never re-pointed at a newer one."""
        for binding in reversed(self._bindings):
            if binding.claim_id == claim_id:
                return binding
        return None

    def claims_written_under(self, interpretation_id: str) -> tuple[ClaimBinding, ...]:
        return tuple(b for b in self._bindings if b.interpretation_id == interpretation_id)

    def reading_of(self, claim_id: str) -> ResolutionDecision | None:
        """How the claim reads *now*, under the interpretation currently in force.

        Distinct from :meth:`claim_binding` on purpose. The binding is a historical fact; this
        is a present-tense lookup. A claim written under ``D1`` and later superseded still returns
        ``D1`` from the first and ``D2`` from the second, and that gap is FR-082.
        """
        binding = self.claim_binding(claim_id)
        if binding is None or binding.interpretation_id is None:
            return None
        return self.get(binding.interpretation_id)

    def readings_of(self, claim_id: str) -> tuple[ResolutionDecision, ...]:
        """Every interpretation this claim has ever been read under, oldest first."""
        return tuple(
            d
            for d in self._all()
            if d.decision_id
            in {b.interpretation_id for b in self._bindings if b.claim_id == claim_id}
        )

    def all_decisions(self) -> tuple[ResolutionDecision, ...]:
        return self._all()

    def __len__(self) -> int:
        return len(self._decisions)

    def _all(self) -> list[ResolutionDecision]:
        return [self._decisions[i] for i in self._order]


def corroboration_from_counts(
    *,
    documents: int,
    hosts: int,
    lineage_roots: int | None,
) -> tuple[str, int, dict[str, int | str]]:
    """Build the ``(measure, value, detail)`` triple a decision carries (WP-E T071).

    ``lineage_roots`` present and non-zero selects ``lineage_roots`` as the measure. Everything
    else — including ``lineage_roots is None`` — is reported under ``hosts``, with
    ``independence_measured_on`` recorded so a reader can tell which one they are looking at.
    Both counts are always in the detail; an analyst reading "20 hosts" must be able to see
    "1 origin" beside it.
    """
    if lineage_roots:
        return (
            "lineage_roots",
            int(lineage_roots),
            {
                "documents": int(documents),
                "hosts": int(hosts),
                "effective_sources": int(lineage_roots),
                "independence_measured_on": "lineage",
            },
        )
    return (
        "hosts",
        int(hosts),
        {
            "documents": int(documents),
            "hosts": int(hosts),
            "effective_sources": int(hosts),
            "independence_measured_on": "hosts",
        },
    )


def new_decision(
    pair_key: str,
    kind: DecisionKind,
    *,
    decided_by: str,
    supersedes: str | None = None,
    hypothesis_id: str | None = None,
    matcher: MatcherProfile | None = None,
    corroboration: tuple[str, int, Mapping[str, int | str]] | None = None,
    rationale: str = "",
    evidence_refs: Iterable[str] = (),
    span_refs: Sequence[EvidenceSpanRef] = (),
    rule_version: str = "identity-resolution-v1",
) -> ResolutionDecision:
    """Build a decision with the corroboration measure required (T080) rather than optional."""
    measure, value, detail = corroboration or ("none", 0, {"independence_measured_on": "none"})
    return ResolutionDecision(
        decision_id=_new_id("RDC"),
        pair_key=pair_key,
        kind=kind,
        supersedes=supersedes,
        hypothesis_id=hypothesis_id,
        decided_by=decided_by,
        matcher=matcher,
        corroboration_measure=measure,
        corroboration_value=value,
        corroboration_detail=detail,
        rationale=rationale,
        evidence_refs=tuple(evidence_refs),
        span_refs=tuple(span_refs),
        rule_version=rule_version,
    )