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

**Phase 4B removed the one place this module did resolve a disagreement, and it was the
worst of them.** :func:`_arity_of` used to take a **majority vote** over the members' stated
``arity_mode`` and break ties **alphabetically**. Two producers reading four ends and two
producers reading two ended up as one candidate whose shape whichever way the dictionary
sorted, and the minority reading disappeared with no trace - so a platform could report a
binary relation that two of its own producers had explicitly called n-ary, and had no way to
find out. ``ARBITRATION`` §3 is the authority: a structural disagreement is not a denial, it
is a disagreement about *shape*, and the three things - predicate conflict, structural
conflict, and :attr:`~domain.relation_candidate.CandidateStatus.CONTRADICTED` - are never
collapsed into one another. The fix is not a better vote; it is to make a structural
disagreement **two readings** by putting the declared shape into :func:`reading_key`, exactly
as ``polarity`` and ``direction`` already were. Both readings are preserved, the pair is
named in :attr:`AssemblyReport.groups_with_structural_conflict` with the axes spelled out, and
:func:`_arity_of` returns a plain :class:`~domain.relation_identity.RelationArityMode` with
no tie-break in it. ``CONTRADICTED`` is never written: this module has one construction site
for a candidate and it says ``PROPOSE``.

**The structural verdict now lives on the candidate, and the report projects it.**
:attr:`~domain.relation_candidate.RelationCandidate.assembly_state` is
``CandidateAssemblyState.CONFLICTING`` on **every** reading of a structurally contested pair,
and :attr:`AssemblyReport.groups_with_structural_conflict` is a **property computed from the
candidates** - there is no stored copy left to disagree with them. That is the whole of the
change from the report-only arrangement Phase 4B was forced into, and it matters because a
verdict that lives only on a report is lost the moment the candidates are persisted and the
report is not: a structural conflict would become an invisible disagreement between two rows
that look like ordinary competing readings. The verdict is **revision** material, so the two
readings still share one ``logical_candidate_id`` - one hypothesis, two readings, and the
disagreement is the evidence.

**Phase 4C added the fourth structural axis, and ``ARBITRATION`` §3 was the argument for it.**
The record names four things producers can disagree about structurally - *arity, direction,
polarity or role slots* - and three of the four were implemented and the fourth was answered
with a tuple: :func:`_roles_of` returned ``()`` whenever a reading's members did not *unanimously*
declare role bindings, so a producer that named the slots of a configuration and a producer
that named none produced one candidate and the disagreement was gone. Role slots are now the
sixth component of :func:`reading_key`, exactly as ``arity_mode`` is the fifth and for the same
reason: **a structural disagreement is prevented by the key rather than resolved by the
assembler.** The partial set is therefore two readings, both preserved, both ``CONFLICTING``,
and the pair is named in :attr:`AssemblyReport.structural_conflicts` under ``role_slots`` with
both declared sets spelled out. The full argument, including the old rationale and why it was
the reason the finding had to be *visible* rather than dropped, is on :func:`_roles_of`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from domain.relation_candidate import (
    CandidateAssemblyState,
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

    **The two conflict fields answer different questions and are not interchangeable.**
    :attr:`groups_with_conflict` is a *semantic* disagreement: two readings of one pair that
    disagree about the world - a sentence saying "CEO of" and a table saying "founder of"
    are two claims, and the pair is contested.
    :attr:`groups_with_structural_conflict` is a **structural** one: producers describing the
    same pair in incompatible *shapes* - three ends against two, an ordered reading against
    an undirected one, a producer that named the role slots against one that named none.
    ``ARBITRATION`` §3 requires these to be three distinct things and never collapsed: a
    predicate-level conflict, a candidate-level structural conflict, and
    :attr:`~domain.relation_candidate.CandidateStatus.CONTRADICTED`, which means the
    assertion was **denied** and is reserved for a positive reading meeting an explicit
    denial. Assembly sets ``PROPOSE`` and nothing else, so a structural disagreement can
    never arrive here as a contradicted candidate, and the two lists are kept apart so a
    caller can tell the two apart too.

    **What Phase 4B did not do, and what has since replaced it.** Phase 4B carried the structural
    verdict **on this report**, because
    :attr:`RelationCandidate.assembly_state` — the field ``ARBITRATION`` §3 puts the verdict *on* —
    did not exist: ``CandidateAssemblyState`` was declared ``NEW`` in
    ``domain/relation_candidate.py``, and that file was outside that phase's ownership. The field
    exists now, and the verdict is **on the candidate**:
    :attr:`~domain.relation_candidate.RelationCandidate.assembly_state` reads
    ``CONFLICTING`` on every reading of a contested pair, and
    :attr:`RelationCandidate.is_structurally_contested` is the name for asking.

    :attr:`groups_with_structural_conflict` is therefore a **projection** — a property over
    :attr:`candidates` with no stored copy of its own, so it cannot drift from the verdict and
    cannot be stale after the candidates are persisted and this report is not. That was the real
    cost of the report-only arrangement and it is now gone: a structural conflict recorded only
    here was an invisible disagreement between two rows that looked like ordinary competing
    readings.

    :attr:`structural_conflicts` is the one field that is still a stored tuple rather than a
    projection, and the reason is stated rather than worked around: it elaborates *which* axes
    disagreed, and one of the four axes — ``direction`` — has no candidate field at all.
    ``DirectionHypothesis`` is a reading-side observation (``data-model.md`` part 9 keeps direction
    a derived projection of the slot order and the declared symmetry), and putting it on the
    candidate to make this a projection would be a second source of truth for a value the identity
    subsystem already derives. So the pair list is a projection of the verdict and the axis
    elaboration is this report's own record of what the producers stated; the two are computed in
    one pass, so they cannot disagree about which pairs were contested.
    """

    signal_count: int
    attributed_signal_count: int
    group_count: int
    candidates: tuple[RelationCandidate, ...]
    groups_with_conflict: tuple[str, ...]
    unattributed_signal_ids: tuple[str, ...]
    #: The same disagreements, with the shapes spelled out, so a report says *what* the
    #: producers disagreed about rather than only *that* they did. Sorted, because
    #: constitution VI.
    #:
    #: Report-side elaboration rather than a projection, and
    #: :attr:`groups_with_structural_conflict` is the projection: ``direction`` is a reading-side
    #: observation with no candidate field, so a candidate cannot carry the axis list and making
    #: it do so would be a second source of truth for a derived value. Computed in the same pass
    #: as the verdict, so the two cannot disagree about which pairs were contested.
    structural_conflicts: tuple[tuple[str, str, str, str], ...] = ()

    @property
    def groups_with_structural_conflict(self) -> tuple[str, ...]:
        """``"subject->object"`` for every pair whose readings disagreed on a **structural**
        reading — arity, direction, polarity or role slots.

        **A projection of :attr:`RelationCandidate.assembly_state` and nothing else.** Every pair
        with at least one ``CONFLICTING`` reading appears, sorted and de-duplicated, and a pair
        with none does not — so this is answerable from the candidates alone, with no state of
        this report's own involved. That is the property the previous arrangement could not have:
        the list was a stored field, so the verdict existed in two places and persisting the
        candidates without the report would have left a structural conflict with no record
        (ARBITRATION §3).

        Disjoint from :attr:`groups_with_conflict` in intent though not in membership: a pair can
        be in both, and a caller that only reads :attr:`groups_with_conflict` will learn that
        something was contested without learning what.
        """
        pairs = {
            f"{candidate.subject_mention_ref}->{candidate.object_mention_ref}"
            for candidate in self.candidates
            if candidate.assembly_state is CandidateAssemblyState.CONFLICTING
        }
        return tuple(sorted(pairs))

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
            "groups_with_structural_conflict": list(self.groups_with_structural_conflict),
            "structural_conflicts": [list(entry) for entry in self.structural_conflicts],
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


def role_slots_of(signal: RelationSignal) -> tuple[tuple[str, str, str], ...]:
    """The role slots this signal declared, as a sorted tuple, or ``()``.

    **The fourth structural axis, and what "a role slot" is here.** ``ARBITRATION`` §3 names
    role slots beside arity, direction and polarity as a thing producers disagree about, and
    before Phase 4C that sentence was not implemented: :func:`_roles_of` asked whether a
    reading's members *unanimously* declared role bindings and returned ``()`` whenever they
    did not, so a producer that named the slots and a producer that named nothing produced the
    same candidate and the disagreement was gone. The unanimity test is what this function's
    output now replaces, and it is a **disagreement** test, not a **cooperation** test: two
    signals whose declared role slots differ are two readings, both preserved, and the pair
    carries :attr:`~domain.relation_candidate.CandidateAssemblyState.CONFLICTING`.

    **A binding is ``(role, member_ref, member_class)`` and the whole of it is structural
    here.** The alternative considered and rejected was to key only on *which members* were
    bound and leave the free-text role words out, on the argument that
    :attr:`RelationRoleBinding.role` is free text and free text must not fork an identity. That
    argument is right about ``logical_candidate_id`` — and it is still right here, because
    nothing in this function reaches the candidate's logical material. It does not apply to the
    *reading key*, for two reasons. First, ``domain.relation_identity.logical_material`` already
    puts the role word in the **logical** material of an n-ary *relation*
    (``relation_identity.py:201``), so within this codebase a spelling difference between two
    producers' role names is already treated as a different relation and pretending otherwise at
    the reading key would make assembly the one layer that disagrees with the identity
    subsystem. Second, and more simply: "seller" and "vendor" over the same two mentions are
    two *readings*, and reporting them as one and then dropping the minority's words is the
    defect. What the key never does is decide which word is right — :func:`_roles_of` copies
    the declared set verbatim, and a caller wanting one name for the pair has to choose it
    explicitly.

    **Sorted, and never a set**, because a rendering that depends on declaration order would
    make constitution VI a matter of which producer happened to run first.

    An entry that is not a binding and not a three-element sequence is **refused** with
    ``role_slot_unreadable``, mirroring :func:`_arity_of`'s ``structural_arity_unreadable``.
    The alternative — treating it as "no roles declared" — is the same swallow this function
    exists to end: a malformed declaration would assemble into a candidate with fewer roles
    than the producer wrote down, and no record of what was dropped.
    """
    declared = signal.extra.get("role_bindings")
    if not declared:
        return ()
    built: list[tuple[str, str, str]] = []
    for entry in declared:
        if isinstance(entry, RelationRoleBinding):
            built.append((str(entry.role), str(entry.member_ref), str(entry.member_class)))
            continue
        try:
            role, member, member_class = entry
        except (TypeError, ValueError) as exc:
            raise AssemblyError(
                "role_slot_unreadable",
                f"signal {signal.signal_id} from producer {signal.producer_ref!r} declared a "
                f"role binding of {entry!r}, which is neither a RelationRoleBinding nor a "
                f"(role, member, member_class) triple. A slot that cannot be read is a role "
                "nobody can order, and treating it as 'no role declared' would assemble a "
                "candidate with fewer roles than the producer wrote down and no record of what "
                "was dropped. State the binding as a triple, or omit the declaration entirely",
            ) from exc
        built.append((str(role), str(member), str(member_class)))
    return tuple(sorted(built))


def _render_role_slots(slots: Sequence[tuple[str, str, str]]) -> str:
    """One reading-key component for a declared role-slot set.

    **JSON, and the reason is injectivity rather than taste.** A ``" | "``-joined rendering
    would be readable, and two producers whose role names contained the separator would render
    to the same component - which means their readings would *merge*, and the axis would report
    agreement between two declarations that disagree. ``json.dumps`` of the sorted triples is
    injective over the same data, order-independent because the input is sorted, and still
    legible in :attr:`AssemblyReport.structural_conflicts`, which exists to say *what* the
    producers disagreed about rather than only that they did.
    """
    return json.dumps([list(slot) for slot in slots], separators=(",", ":"))


def reading_key(signal: RelationSignal) -> tuple[str, str, str, str, str, str]:
    """What makes two signals on one pair the *same reading* of it.

    A six-part key, and each part is load-bearing:

    * ``polarity`` - ``asserted``, ``denied`` or ``uncertain``, read from
      :attr:`RelationSignal.polarity`. A denied signal about a pair and a positive
      signal about the same pair are not two readings of one hypothesis; they are opposite
      claims, and merging them would produce a candidate that both asserts and denies the
      relation. Keeping them apart is what makes "Acme did not acquire Beta"
      representable at all - the alternative was dropping the denial or recording the
      acquisition. Phase 4C removed :attr:`SignalKind.NEGATION`, so this is the only place a
      denial can enter the key.
    * ``surface`` - the relation's own words, lowercased. Two producers that saw the same
      phrase are reading the same thing even if only one of them could type it.
    * ``ref`` - the resolved operator, or ``""``. Two signals with different operator types
      are different readings, whatever their surfaces; a table saying "Role" and a sentence
      saying "CEO of" are not competing readings of one predicate, they are two predicates
      somebody must decide between.
    * ``direction`` - ordered, object-to-subject, undirected or ambiguous. A signal that
      could not order its ends is not a reading of an ordered one.
    * ``arity_mode`` - the shape the producer declared, or ``""``. **Added by Phase 4B**,
      and it is the same kind of part as ``direction`` and ``polarity``: a signal that read
      three ends and a signal that read two are not the same reading of a pair, and leaving
      it out of the key is what let :func:`_arity_of` resolve a disagreement by majority
      vote. See the :class:`AssemblyReport` note on what a disagreement now produces.
    * ``role_slots`` - the role bindings the producer declared, or ``""``. **Added by
      Phase 4C**, and the last of the four structural axes ``ARBITRATION`` §3 names. It is
      the same kind of part as ``arity_mode``: a signal that named the slots of its
      configuration and a signal that named none are not the same reading, and leaving it out
      is what let :func:`_roles_of` answer a disagreement with ``()``. See
      :func:`role_slots_of` for what a role slot is here and why the role *word* is inside it.

    Note what is **not** in the key: the producer. Two producers reading the same phrase
    corroborate one reading, and the corroboration is recorded in ``signal_refs`` - if the
    producer were part of the key, corroboration would arrive as a conflict.
    """
    polarity = str(signal.polarity)
    surface = " ".join(signal.relation_surface.split()).lower()
    ref = str(signal.relation_ref) if signal.relation_ref else ""
    slots = role_slots_of(signal)
    return (
        polarity,
        surface,
        ref,
        str(signal.direction),
        str(signal.extra.get("arity_mode") or ""),
        _render_role_slots(slots) if slots else "",
    )


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
    record. **No code path in this module can set
    :attr:`~domain.relation_candidate.CandidateStatus.CONTRADICTED`** - it is a literal
    ``PROPOSE`` on the one construction site - and that is asserted by
    ``test_assembly_never_writes_a_contradicted_status`` rather than left to review.
    """
    ordered = tuple(sorted(signals, key=lambda s: s.signal_id))
    if not ordered:
        return AssemblyReport(0, 0, 0, (), (), ())

    groups: dict[
        tuple[str, str], dict[tuple[str, str, str, str, str, str], list[RelationSignal]]
    ] = {}
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
    structural_detail: list[tuple[str, str, str, str]] = []
    attributed: list[str] = []
    for pair in sorted(groups):
        readings = groups[pair]
        pair_readings = sorted(readings)
        axes: list[tuple[int, str]] = []
        if len(pair_readings) > 1:
            conflicted.append(f"{pair[0]}->{pair[1]}")
            # A disagreement on polarity, direction, arity or role slots is a *structural* one,
            # and the four questions are never collapsed (ARBITRATION §3). Semantic-only
            # disagreement - two surfaces, two operators, one pair - is a conflict about the
            # world and is not structural.
            axes = list(_structural_axes_of(readings))
            for index, axis in axes:
                seen = sorted({key[index] for key in pair_readings})
                structural_detail.append(
                    (f"{pair[0]}->{pair[1]}", axis, "", " | ".join(seen))
                )
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
                    # The verdict, on the candidate (ARBITRATION §3). Every reading of a
                    # contested pair carries it, not just the minority: the disagreement is about
                    # the *configuration*, and sitting on one side of it does not make a reading
                    # consistent. There is no `AMBIGUOUS` here on purpose - see
                    # CandidateAssemblyState, whose docstring says why the semantic axis does
                    # not get a second report from this one.
                    assembly_state=(
                        CandidateAssemblyState.CONFLICTING
                        if axes
                        else CandidateAssemblyState.CONSISTENT
                    ),
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
        structural_conflicts=tuple(sorted(structural_detail)),
    )


#: The **four** reading-key positions that are **structural**, and the name each is reported
#: under. Position 0 is ``polarity``, 3 is ``direction``, 4 is ``arity_mode``, 5 is
#: ``role_slots``; positions 1 (``surface``) and 2 (``ref``) are semantic, because a
#: disagreement about either is a disagreement about the world rather than about the shape of
#: the reading.
#:
#: **``role_slots`` joined in Phase 4C**, and it is the last of the four ``ARBITRATION`` §3
#: names — "producers disagree on arity, direction, polarity or role slots" — so the sentence
#: was three-quarters implemented until now. The three that were already here are the ones a
#: signal carries in a **typed field**; role slots are the one a producer states in
#: :attr:`RelationSignal.extra`, which is why the axis is computed from
#: :func:`role_slots_of` rather than read off an attribute, and why the *key* is the only place
#: the disagreement has to be prevented — see :func:`_roles_of`.
_STRUCTURAL_AXES: frozenset[int] = frozenset({0, 3, 4, 5})
_READING_AXES: Mapping[int, str] = MappingProxyType(
    {0: "polarity", 3: "direction", 4: "arity_mode", 5: "role_slots"}
)


def _structural_axes_of(
    readings: Mapping[tuple[str, str, str, str, str, str], list[RelationSignal]]
) -> Iterator[tuple[int, str]]:
    """``(key position, axis name)`` for each structural axis a pair's readings disagree on.

    Positions rather than names, because the caller needs to index the key to read the values
    and needs the name to report them, and passing one and deriving the other is how the two
    drift apart. Sorted by position, so the report's order is the key's order rather than a
    set's.

    Polarity is included and it is the one that is *also* a denial: "Acme acquired Beta"
    against "Acme did not acquire Beta" is a structural disagreement in the sense that the
    two readings are incompatible, and it is simultaneously the only case that
    :attr:`~domain.relation_candidate.CandidateStatus.CONTRADICTED` is reserved for. Listing
    it here is not a claim that it should become a contradicted candidate - it must not - it
    is the statement that the two readings are incompatible, which is true of all four axes
    and is what the reader needs to know.

    Role slots is listed on the same footing and for the same reason. A signal that named two
    of three slots and a signal that named none are incompatible readings of one
    configuration; neither of them denies the other, and a candidate carrying the disagreement
    says ``PROPOSE`` with ``assembly_state = CONFLICTING`` rather than
    ``candidate_status = CONTRADICTED``.
    """
    for index in sorted(_STRUCTURAL_AXES):
        if len({key[index] for key in readings}) > 1:
            yield index, _READING_AXES[index]


def _candidate_for(
    pair: tuple[str, str],
    members: Sequence[RelationSignal],
    *,
    tenant_id: str,
    context_ref: str,
    semantic_regime_ref: str,
    investigation_id: str,
    recorded_by: str,
    assembly_state: CandidateAssemblyState = CandidateAssemblyState.CONSISTENT,
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

    :attr:`~domain.relation_candidate.RelationCandidate.assembly_state` is **passed in, not
    decided here**, and the division is the point: this function sees one reading's members,
    which agreed by construction, so it cannot know a disagreement exists. The caller sees the
    whole pair and does know. A verdict computed from a member list could only ever be
    ``CONSISTENT`` - which is exactly the false verdict the pre-4B vote produced, at one
    remove.
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
        assembly_state=assembly_state,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        recorded_by=recorded_by,
    ).with_id()


def _arity_of(members: Sequence[RelationSignal]) -> RelationArityMode:
    """The arity mode of a reading, and the agreement is a **precondition, not a vote**.

    ``DIRECTED`` when no member stated one: two participants and no stated role shape is what
    a directed relation is, and defaulting the other way would turn a producer's silence into
    an n-ary claim. That default is a *stated* reading, not a winner - it applies to the case
    where nobody had an opinion.

    **When members disagree, this refuses.** It used to take the majority and break ties
    alphabetically, and both halves of that were wrong in the same direction: a tie between
    two producers saying ``directed`` and two saying ``nary`` is not a tie, it is four
    producers in two camps, and picking ``directed`` because it sorts first is a decision
    made by the collation of a dictionary. Worse, the loser vanished: a producer that read
    three ends had its reading recorded as a binary relation with no trace that it had ever
    said otherwise, and a candidate that claimed two ends would never be compared with one
    claiming three.

    The refusal is the mechanism ``ARBITRATION`` §3 asks for. A structural disagreement is
    **not** a denial, so it must never become
    :attr:`~domain.relation_candidate.CandidateStatus.CONTRADICTED`; and a disagreement the
    assembler resolves is a disagreement nobody was told about. Putting ``arity_mode`` into
    :func:`reading_key` means members *cannot* disagree here in the first place - two
    producers declaring different shapes are two readings of the pair, both preserved, both
    reported, and named in :attr:`AssemblyReport.groups_with_structural_conflict`. So the
    check below is a guard on the key rather than a policy: a producer that reaches it has
    stated two shapes inside one signal, which is not a disagreement between producers but a
    contradiction by one of them.
    """
    stated = {str(s.extra["arity_mode"]) for s in members if s.extra.get("arity_mode")}
    if not stated:
        return RelationArityMode.DIRECTED
    if len(stated) > 1:
        raise AssemblyError(
            "structural_arity_disagreement",
            f"one reading's members declared {sorted(stated)} as the arity mode. Two shapes "
            "in one signal is not a disagreement between producers - the reading key now "
            "separates those - it is a single record contradicting itself, and choosing one "
            "of them (by majority, by sort order, or by first) would record a shape no "
            "producer stated. Split them into separate signals, or state the shape once "
            "(ARBITRATION §3: a structural conflict is not a CandidateStatus)",
        )
    try:
        return RelationArityMode(next(iter(stated)))
    except ValueError as exc:
        raise AssemblyError(
            "structural_arity_unreadable",
            f"a signal declared arity_mode={next(iter(stated))!r}, which is not a "
            f"{RelationArityMode.__name__} member. A producer that cannot state its shape "
            "should state none and let the default apply, rather than a token nothing can "
            "read",
        ) from exc


def _roles_of(members: Sequence[RelationSignal]) -> tuple[Any, ...]:
    """The role bindings of a reading, rebuilt from what the members declared.

    **The Phase 4C decision, recorded here because it is not recoverable from the code.**

    This function used to be *unanimous-only*, and it answered a disagreement by returning
    ``()``:

    .. code-block:: python

        stated = [s.extra.get("role_bindings") for s in members if s.extra.get("role_bindings")]
        if not stated or len(stated) != len(members):
            return ()
        if not all(candidate == first for candidate in stated):
            return ()

    Both of those branches swallowed a **partial set** — a set of declarations covering only
    some of the reading's members — and turned it into "this reading has no roles". That is
    the exact failure ``ARBITRATION`` §3 names when it lists role slots as a
    :attr:`~domain.relation_candidate.CandidateAssemblyState.CONFLICTING` trigger: a producer
    that named the slots of a configuration and a producer that named none produced **one**
    candidate, the naming was lost, and the pair that ARBITRATION says is structurally
    contested reported ``CONSISTENT``. A partial set over one configuration is a finding.

    **So the decision is: a partial set is a reading, not an absence, and the finding lives on
    the candidate rather than in a silent tuple.** The mechanism is that
    :func:`reading_key` now carries the declared role slots, so a partial set cannot reach here
    at all — it was separated into its own reading before the candidate was built, and
    :func:`assemble` marked *both* readings ``CONFLICTING`` and named ``role_slots`` in
    :attr:`AssemblyReport.structural_conflicts`. What survives here is:

    * **nobody declared anything** → ``()``. A reading where no producer had an opinion about
      roles is a *stated silence*, and a silence is not a finding. It is also the ordinary case:
      six of the seven producers say nothing about roles, and refusing that would refuse almost
      every signal on the platform.
    * **the members agree** — which they now agree on *by construction*, since the key carries
      the set — so the bindings are copied verbatim and typed. The disagreement check below is
      a **guard on the key**, exactly like :func:`_arity_of`'s, not a policy: a producer that
      reaches it has stated two role-slot sets inside one signal, which is not a disagreement
      between producers but a record contradicting itself.

    **And the old rationale for the swallow is recorded as the reason it was wrong, because it
    was a real argument.** The docstring used to say: *unanimous-only because a partial set of
    role bindings is a malformed n-ary claim: two members of three roles would let
    :class:`domain.relation_claim.RelationClaim` accept a relation whose third participant was
    never named.* That is true, and it is the reason a partial set must be **visible** rather
    than *dropped* — the malformed claim is precisely what a silently emptied
    ``role_assignments`` produces, and by dropping the set the function was making the
    malformation invisible while citing it as the reason. The claim-level check belongs to the
    claim layer, which has
    :func:`domain.relation_claim.check_role_bindings` and a ``ResolutionDecisionRecord`` behind
    it; the assembler's job is to say what the producers stated, and to say so by splitting the
    reading rather than by deciding.
    """
    declared = [role_slots_of(signal) for signal in members]
    stated = [slots for slots in declared if slots]
    if not stated:
        return ()
    distinct = {slots for slots in stated}
    if len(distinct) > 1:
        raise AssemblyError(
            "role_slot_disagreement",
            f"one reading's members declared {sorted(distinct)} as their role slots. Two role-"
            "slot sets in one signal is not a disagreement between producers - the reading key "
            "now separates those, so they are two readings of the pair and both are preserved - "
            "it is a single record contradicting itself, and choosing one of them (by majority, "
            "by sort order, or by first) would record a role set no producer stated. Split them "
            "into separate signals, or state the roles once (ARBITRATION §3: a structural "
            "conflict is assembly_state = CONFLICTING, never a CandidateStatus)",
        )
    built: list[RelationRoleBinding] = []
    for role, member, member_class in next(iter(distinct)):
        built.append(RelationRoleBinding(role, member, member_class))
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
    "role_slots_of",
]
