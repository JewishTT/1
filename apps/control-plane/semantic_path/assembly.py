"""Assembly: signals become candidates, and disagreements stay disagreements.

Feature 019, T031–T033 (FR-032…FR-036, SC-E, CD-6, CD-7).

Producers report what they saw. This module turns a set of signals into
:class:`~domain.relation_candidate.RelationCandidate` readings, and it is deliberately the
only place that happens: producers do not build candidates, and candidates are not built
anywhere else. One code path, so "how does a signal become a candidate" has one answer.

**What assembly is not allowed to do**, because each of these is a decision with its own
record somewhere else:

* It does not resolve a mention to an entity. A candidate names mentions; resolution
  produces entities; conflating them would put an identity decision inside extraction where
  no ``ResolutionDecisionRecord`` exists to justify it.
* It does not admit. No ``CandidateStatus`` is set here beyond the default ``PROPOSE``, and
  the module imports no admission vocabulary at all - the same discipline
  :mod:`extractors.relations` follows, and the reason it is worth repeating is that a status
  field is one line away from being set by accident.
* It does not project. No ``GraphEdge``, no node, no graph. A projection is a view and a
  view is somebody else's decision.
* It does not merge across disagreement. A conflict is reported as competing candidates and
  both are returned.

**The grouping key is the mention pair, and that choice has consequences.** Signals are
grouped by ``(subject_mention_ref, object_mention_ref)`` because that is the only thing a
signal about *this* pair and a signal about *that* pair have in common, and because
FR-034's independence count is computed over the signals backing a candidate. The
consequence is that direction matters: ``A --works_for--> B`` and ``B --works_for--> A`` are
different pairs, so they are different candidates, and a producer that read the relation
backwards produces a competing candidate rather than corroborating the right one. That is
the right outcome - a reversed direction is a disagreement about the world, not agreement.

**OQ3, resolved: may a hypothesis carry no signals?** *The type may; the assembler never
does.* :attr:`domain.relation_candidate.RelationCandidate.signal_refs` is legal empty, and
:func:`assemble` never produces an empty one - every candidate it returns carries at least
one signal id, and :attr:`AssemblyReport.complete` is the check that says so across a whole
batch.

The two halves answer different questions and only one of them is "no". The *type* has to
allow it because two real paths produce a candidate with no signals behind it: a caller
constructing a hypothesis by hand, and a :class:`domain.regime.SemanticRegime` producing a
second reading of a surface it resolved itself, which by definition had no producer observe
it. Forbidding that at the type level would make predicate resolution inexpressible - the
platform could never revisit its own decision.

The *assembler* may not do it, because a candidate assembled from nothing is a hypothesis
whose origin nobody can state, and FR-032's "origin preserved" would be satisfied
vacuously. The report makes the distinction checkable rather than a convention: a caller
can assert ``report.complete`` and know that no signal was seen and dropped.

**Why a conflict is reported rather than resolved.** When two signals on one pair disagree,
:func:`assemble` returns both readings and names the pair in
:attr:`AssemblyReport.groups_with_conflict`. It does not pick a winner, does not average
them and does not drop the minority. A caller that wants a decision has to make one
explicitly, which is I-3 and FR-006: a finding is a finding, and deleting the reading that
lost is how a platform loses the fact that it was ever considered.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from domain.relation_candidate import (
    CandidateStatus,
    ExtractionStrategy,
    RelationCandidate,
    RelationRoleBinding,
)
from domain.relation_identity import RelationArityMode
from extractors.signals.signal import (
    DirectionHypothesis,
    PredicateHypothesis,
    RelationSignal,
    SignalKind,
)

#: The strategy an assembled reading records. Its own member, because "several producers
#: agreed" is not any of the strategies a single producer could have used, and recording
#: ``LEXICAL_PATTERN`` on a candidate built from a table and a hyperlink would put a false
#: account of how the reading was made into its identity material.
ASSEMBLY_METHOD = ExtractionStrategy.ORCHESTRATED


@dataclass(frozen=True)
class AssemblyReport:
    """What assembly did, stated rather than inferred from the candidates.

    :attr:`signal_count` against :attr:`attributed_signal_count` is the number that matters,
    and it is reported because a short count is the signature of the one failure this module
    must not have: an observation that was seen and then lost. :attr:`groups_with_conflict`
    is here for the same reason - a conflict that is not counted is a conflict nobody is
    told about.
    """

    signal_count: int
    attributed_signal_count: int
    group_count: int
    candidates: tuple[RelationCandidate, ...]
    groups_with_conflict: tuple[str, ...]
    unattributed_signal_ids: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """Whether every signal was attributed to some candidate."""
        return not self.unattributed_signal_ids

    def by_logical_candidate_id(self, logical_candidate_id: str) -> tuple[RelationCandidate, ...]:
        """Every reading of one hypothesis - the answer to "what did we make of this?"."""
        return tuple(
            candidate
            for candidate in self.candidates
            if candidate.logical_candidate_id == logical_candidate_id
        )

    def competing(self) -> tuple[tuple[RelationCandidate, ...], ...]:
        """Every hypothesis that has more than one reading, in candidate order.

        Grouped rather than flattened, because the useful question is not "which candidates
        disagree" but "which hypotheses have more than one reading" - and a caller that
        wanted a flat list of contested candidates would have to reconstruct the grouping to
        answer it.

        **A hypothesis with two readings is narrower than a disagreement, and the
        difference is the surface.** Two signals about one pair with *different* surfaces -
        "CEO of" and "founded" - are two different claims about the world, so they get two
        different ``logical_candidate_id`` values and are two hypotheses. They appear in
        :attr:`groups_with_conflict` but not here. Two signals with the *same* surface and
        different readings - both saying "CEO of", one typed ``works_for`` and the other
        ``affiliation`` - are two readings of one claim about the world, and that is what
        this method returns.

        Both cases produce two candidates and neither overwrites the other; they differ in
        what the platform is claiming, and a reader who conflated them would report a
        disagreement about *how one relation is named* as though it were a disagreement
        about *what relations hold*.
        """
        contested: dict[str, list[RelationCandidate]] = {}
        for candidate in self.candidates:
            contested.setdefault(candidate.logical_candidate_id, []).append(candidate)
        return tuple(
            tuple(readings)
            for _, readings in sorted(contested.items())
            if len(readings) > 1
        )
        contested: dict[str, list[RelationCandidate]] = {}
        for candidate in self.candidates:
            contested.setdefault(candidate.logical_candidate_id, []).append(candidate)
        return tuple(
            tuple(readings)
            for _, readings in sorted(contested.items())
            if len(readings) > 1
        )

    def producer_families(self, logical_candidate_id: str) -> tuple[str, ...]:
        """How many independent producers backed one hypothesis (FR-034).

        Counted over the *readings* of a hypothesis rather than over its signals, because a
        hypothesis with three readings from one producer is one source, not three. The
        producer's own independence family is not available here - that lives on the
        producer's declaration rather than on its output - so this returns producer refs and
        the caller is expected to collapse them by family. Returning a number instead would
        be a number nobody could check, and FR-034's whole point is that it can be checked.
        """
        refs: set[str] = set()
        for candidate in self.by_logical_candidate_id(logical_candidate_id):
            refs.add(candidate.extraction_rule_id or candidate.extraction_method)
        return tuple(sorted(refs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_count": self.signal_count,
            "attributed_signal_count": self.attributed_signal_count,
            "group_count": self.group_count,
            "candidates": [c.candidate_id for c in self.candidates],
            "groups_with_conflict": list(self.groups_with_conflict),
            "unattributed_signal_ids": list(self.unattributed_signal_ids),
            "complete": self.complete,
        }


def pair_of(signal: RelationSignal) -> tuple[str, str]:
    """The mention pair a signal is about.

    The two refs in their signal order, **not** sorted. Direction is part of what a signal
    asserts, so ``(A, B)`` and ``(B, A)`` are different pairs and sorting them would merge a
    relation with its own inverse - which for a directional relation is a statement and its
    negation in one candidate.
    """
    return signal.subject_mention_ref, signal.object_mention_ref


def reading_key(signal: RelationSignal) -> tuple[str, str, str, str]:
    """What makes two signals on one pair the *same reading* of it.

    A four-part key, and each part is load-bearing:

    * ``polarity`` - ``asserted`` or ``denied``. A ``NEGATION`` signal about a pair and a
      positive signal about the same pair are not two readings of one hypothesis; they are
      opposite claims, and merging them would produce a candidate that both asserts and
      denies the relation. Keeping them apart is what makes "Acme did not acquire Beta"
      representable at all - the alternative was dropping the denial or recording the
      acquisition.
    * ``surface`` - the relation's own words, lowercased. Two producers that saw the same
      phrase are reading the same thing even if only one of them could type it.
    * ``ref`` - the resolved operator, or ``""``. Two signals with different operator types
      are different readings, whatever their surfaces; a table saying "Role" and a sentence
      saying "CEO of" are not competing readings of one predicate, they are two predicates
      somebody must decide between.
    * ``direction`` - ordered, object-to-subject, undirected or ambiguous. A signal that
      could not order its ends is not a reading of an ordered one.

    Note what is **not** in the key: the producer. Two producers reading the same phrase
    corroborate one reading, and the corroboration is recorded in ``signal_refs`` - if the
    producer were part of the key, corroboration would arrive as a conflict.
    """
    polarity = "denied" if signal.kind is SignalKind.NEGATION else "asserted"
    surface = " ".join(signal.relation_surface.split()).lower()
    ref = str(signal.relation_ref) if signal.relation_ref else ""
    return polarity, surface, ref, str(signal.direction)


def assemble(
    signals: Iterable[RelationSignal],
    *,
    tenant_id: str,
    context_ref: str,
    semantic_regime_ref: str,
    investigation_id: str = "",
    recorded_by: str = "",
) -> AssemblyReport:
    """Every signal as candidates: one per pair, one per distinct reading within a pair.

    Requires ``tenant_id``, ``context_ref`` and ``semantic_regime_ref`` as keywords and
    refuses to default them, for the same reason :class:`~extractors.signals.protocol.
    ExtractionScope` does: a frame and a regime are somebody else's decisions and a default
    here would be a silent substitution (FR-015, FR-016).

    **Input order does not affect the result.** Signals are grouped into a mapping keyed by
    pair and then by reading key, and both iterations are over sorted keys, so two processes
    handed the same signals in different orders derive byte-identical candidate ids. That is
    constitution VI, and it is a property of this function's structure rather than something
    it has to remember to do.

    Signals from a pair with a ``denied`` polarity produce a candidate whose
    :attr:`~domain.relation_candidate.RelationCandidate.candidate_status` is still
    ``PROPOSE``: assembly does not decide that a denial is weaker than an assertion, and a
    denial that is wrong is a real error in the world that the platform should be able to
    record.
    """
    ordered = tuple(sorted(signals, key=lambda s: s.signal_id))
    if not ordered:
        return AssemblyReport(0, 0, 0, (), (), ())

    groups: dict[tuple[str, str], dict[tuple[str, str, str, str], list[RelationSignal]]] = {}
    for signal in ordered:
        if signal.tenant_id != tenant_id:
            # Refused rather than skipped: a cross-tenant signal reaching this point means
            # a producer was run for the wrong tenant, and dropping it quietly would make
            # one tenant's absence of relations indistinguishable from a bug.
            raise AssemblyError(
                "signal_tenant_mismatch",
                f"signal {signal.signal_id} belongs to tenant {signal.tenant_id!r} and "
                f"assembly is running for {tenant_id!r}; cross-tenant assembly is refused "
                "fail-closed (constitution IV)",
            )
        groups.setdefault(pair_of(signal), {}).setdefault(reading_key(signal), []).append(signal)

    candidates: list[RelationCandidate] = []
    conflicted: list[str] = []
    attributed: list[str] = []
    for pair in sorted(groups):
        readings = groups[pair]
        pair_readings = sorted(readings)
        if len(pair_readings) > 1:
            conflicted.append(f"{pair[0]}->{pair[1]}")
        for key in pair_readings:
            members = sorted(readings[key], key=lambda s: s.signal_id)
            attributed.extend(s.signal_id for s in members)
            candidates.append(
                _candidate_for(
                    pair,
                    members,
                    tenant_id=tenant_id,
                    context_ref=context_ref,
                    semantic_regime_ref=semantic_regime_ref,
                    investigation_id=investigation_id,
                    recorded_by=recorded_by,
                )
            )

    seen: set[str] = set()
    for candidate in candidates:
        seen.update(candidate.signal_refs)
    missing = tuple(s.signal_id for s in ordered if s.signal_id not in seen)
    return AssemblyReport(
        signal_count=len(ordered),
        attributed_signal_count=len(attributed),
        group_count=len(groups),
        candidates=tuple(candidates),
        groups_with_conflict=tuple(conflicted),
        unattributed_signal_ids=missing,
    )


def _candidate_for(
    pair: tuple[str, str],
    members: Sequence[RelationSignal],
    *,
    tenant_id: str,
    context_ref: str,
    semantic_regime_ref: str,
    investigation_id: str,
    recorded_by: str,
) -> RelationCandidate:
    """One reading of one pair, built from every signal that agrees on it.

    The predicate is assembled from the members rather than copied from the first one, and
    that is the interesting part. If the members disagree about the operator *while
    agreeing on everything else in the key* - which can only happen when their
    ``relation_ref`` values are equal but their extra readings are not - the disagreement
    becomes alternatives on one :class:`~domain.predicate_hypothesis.PredicateHypothesis`
    rather than a second candidate. A hypothesis whose readings compete is a hypothesis with
    several names; a hypothesis with two candidates is two hypotheses. Which of those a
    disagreement is depends on whether the *ends* are the same, and here they are, because
    the reading key already established that.
    """
    first = members[0]
    hypothesis = _predicate_from(members)
    return RelationCandidate(
        subject_mention_ref=pair[0],
        object_mention_ref=pair[1],
        relation_ref=first.relation_ref,
        predicate_hypothesis=hypothesis,
        relation_surface=first.relation_surface,
        signal_refs=tuple(sorted(s.signal_id for s in members)),
        arity_mode=_arity_of(members),
        role_assignments=_roles_of(members),
        context_ref=context_ref,
        semantic_regime_ref=semantic_regime_ref,
        extraction_method=ASSEMBLY_METHOD,
        # The producers, in the field that is identity material, so two readings backed by
        # different producers are different readings even when the predicate agrees. What
        # corroboration exists is therefore legible in the address, not only in a list.
        extraction_rule_id="|".join(sorted({s.producer_ref for s in members})),
        observation_refs=tuple(sorted({r for s in members for r in s.extra.get("observation_refs", ())})),
        candidate_status=CandidateStatus.PROPOSE,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        recorded_by=recorded_by,
    ).with_id()


def _arity_of(members: Sequence[RelationSignal]) -> Any:
    """The arity mode of a reading, agreed by its members.

    ``DIRECTED`` unless every member says otherwise, because two participants and no stated
    role shape is what a directed relation is, and defaulting the other way would make a
    producer's silence into an n-ary claim. A disagreement is impossible here in practice -
    the reading key does not include arity, so members *can* disagree - and the majority
    wins rather than the first, because first-wins would make the result depend on sort
    order for no reason a reader could reconstruct.
    """
    stated = [s.extra.get("arity_mode") for s in members if s.extra.get("arity_mode")]
    if not stated:
        return RelationArityMode.DIRECTED
    counts: dict[str, int] = {}
    for mode in stated:
        counts[mode] = counts.get(mode, 0) + 1
    # Most votes wins, ties broken alphabetically. `min` with a negated count expresses that
    # directly, and the tiebreak keeps the choice independent of dict iteration order - which
    # is constitution VI, not a style preference: a result that depends on insertion order
    # is a result two processes can disagree about.
    winner = min(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return RelationArityMode(winner)


def _roles_of(members: Sequence[RelationSignal]) -> tuple[Any, ...]:
    """The role bindings of a reading, rebuilt from what the members stated.

    Pass-through and unanimous-only, and both restrictions are load-bearing. A role binding
    names a *role* and a *member*, so it is a claim about the relation's shape rather than
    about what was observed - and a producer that stated one (a caller's programmatic
    declaration, or a schema that says which slot is which) is stating something the
    producer contract has no field for. :attr:`RelationSignal.extra` is the documented place
    for producer-specific labels, so the binding travels there as a plain tuple - serialisable
    into the durable row, which a frozen dataclass would not be - and the **typed**
    :class:`~domain.relation_candidate.RelationRoleBinding` is rebuilt here, where the field
    that has to be typed actually is.

    Unanimous-only because a partial set of role bindings is a malformed n-ary claim: two
    members of three roles would let :class:`domain.relation_claim.RelationClaim` accept a
    relation whose third participant was never named. A disagreement therefore yields no
    bindings and the reading becomes ``DIRECTED`` - visibly less structured rather than
    quietly wrong.
    """
    stated = [s.extra.get("role_bindings") for s in members if s.extra.get("role_bindings")]
    if not stated or len(stated) != len(members):
        return ()
    first = stated[0]
    if not all(candidate == first for candidate in stated):
        return ()
    built: list[RelationRoleBinding] = []
    for entry in first:
        if isinstance(entry, RelationRoleBinding):
            built.append(entry)
            continue
        try:
            role, member, member_class = entry
        except (TypeError, ValueError):
            return ()
        built.append(RelationRoleBinding(str(role), str(member), str(member_class)))
    return tuple(built)


def _predicate_from(members: Sequence[RelationSignal]) -> PredicateHypothesis:
    """One predicate hypothesis covering every signal in a reading.

    Surfaces are unioned rather than one being chosen, because the members agreed on the
    surface by construction (it is part of the reading key) and the union is therefore a set
    of size one - except for casing and whitespace, which are normalised. Refs are unioned
    the same way, and if more than one survives, the extras become alternatives and the
    state becomes ``ambiguous`` by derivation rather than by assertion.
    """
    surfaces = {" ".join(s.relation_surface.split()) for s in members if s.relation_surface.strip()}
    refs = {s.relation_ref for s in members if s.relation_ref is not None}
    # Min, not a sort: the members already agree on the surface by construction (it is part
    # of the reading key), so this is a normalisation and any of them would do - which means
    # picking the smallest is as good as picking the first and does not depend on the order
    # the members arrived in.
    surface = min(surfaces) if surfaces else ""
    if len(refs) <= 1:
        return PredicateHypothesis(
            relation_ref=next(iter(refs), None),
            surface_form=surface,
        )
    ordered = sorted(refs, key=str)
    return PredicateHypothesis(
        relation_ref=ordered[0],
        alternative_refs=tuple(ordered[1:]),
        surface_form=surface,
    )


class AssemblyError(ValueError):
    """Signals cannot be assembled into candidates.

    A ``ValueError`` carrying a stable snake_case ``code``, matching
    :class:`extractors.signals.signal.SignalContractError` so one caller can switch on any
    of them.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def direction_of(signal: RelationSignal) -> DirectionHypothesis:
    """The signal's direction, named. Re-exported so a caller reading an assembly report
    does not have to import the signal module to interpret it."""
    return signal.direction


__all__ = [
    "ASSEMBLY_METHOD",
    "AssemblyError",
    "AssemblyReport",
    "assemble",
    "direction_of",
    "pair_of",
    "reading_key",
]
