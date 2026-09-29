"""Assembly's structural axis: a disagreement is reported, never voted on.

Feature 021, T031–T033; spec FR-032…FR-036; ``repair/ARBITRATION.md`` §3; checklist R090.

**What this file guards.** :func:`semantic_path.assembly._arity_of` used to take a **majority
vote** over the members' declared ``arity_mode`` and break ties **alphabetically**, and the
module's own docstring called the disagreement "impossible in practice" while admitting in the
next clause that the reading key did not include arity and members therefore could disagree.
It was the one place in the assembler that resolved a disagreement rather than reporting it,
and both halves of the resolution were arbitrary: a tie between two producers saying
``directed`` and two saying ``nary`` is not a tie, and ``directed`` did not win because it was
right, it won because ``d`` sorts before ``n``.

**Three distinct things, never collapsed** (``ARBITRATION`` §3):

============================  =============  ==================================================
state                        lives on       means
============================  =============  ==================================================
predicate-level conflict     the hypothesis  two *regimes* mapped one signature incompatibly
``assembly_state = CONFLICTING``  the candidate   producers disagree on the **shape** of one reading
``CandidateStatus.CONTRADICTED``  the candidate   the assertion was **denied**
============================  =============  ==================================================

:func:`test_a_structural_disagreement_never_becomes_a_contradicted_status` asserts the third
is never written by assembly at all, and
:func:`test_restoring_the_majority_vote_fails_this_file` removes the vote from a *copy* of the
module and asserts that the tests below catch it — a guard that has never been observed to
fail has not been shown to guard anything.
:func:`test_writing_the_conflict_as_contradicted_fails_this_file` is the same shape for the other
half of §3: it puts the verdict on the status and asserts the guard notices.

**The verdict is on the candidate now, and the report is a projection of it.**
:attr:`RelationCandidate.assembly_state` exists — ``CandidateAssemblyState`` is declared in
``domain/relation_candidate.py`` and every reading of a structurally contested pair carries
``CONFLICTING`` — so :attr:`~semantic_path.assembly.AssemblyReport.groups_with_structural_conflict`
is a property over :attr:`~semantic_path.assembly.AssemblyReport.candidates` with no stored copy
of its own. :func:`test_the_report_field_is_a_projection_of_the_candidate_verdict` is the proof,
and it is asserted the only way a projection can be: by hand-building a report over a hand-built
candidate set and reading the field back. The tripwire that used to pin the *absence* —
``test_the_verdict_is_on_the_report_because_the_candidate_has_no_such_field`` — asserted
``not hasattr(relation_candidate, "CandidateAssemblyState")`` and said what to do if that ever
failed. It failed, it was obeyed, and it has been **deleted** rather than edited: a tripwire that
has fired is a record, and leaving a green version of it behind would put a second, weaker claim
about the same field on the platform.
"""


from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import fields, replace
from pathlib import Path


import pytest
from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_candidate import CandidateAssemblyState, CandidateStatus
from domain.relation_identity import RelationArityMode

from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis
from extractors.signals import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalKind,
)
from extractors.signals.protocol import ExtractionScope

from semantic_path.assembly import (
    AssemblyError,
    AssemblyReport,
    assemble,
    reading_key,
)


pytestmark = pytest.mark.unit

#: The control-plane app root. ``parents[2]`` because this file is ``tests/unit/<name>.py``,
#: so ``parents[0]`` is ``unit`` and ``parents[1]`` is ``tests``.
APPS = Path(__file__).resolve().parents[2]
_KWARGS = {
    "tenant_id": "T1",
    "context_ref": "CX-1",
    "semantic_regime_ref": "RG-1",
}
_NB = Neighbourhood(
    characters_scanned=64, pairs_considered=0, scope_read="one clause, read left to right"
)


def _mention(index: int) -> str:
    """``MN-A``, ``MN-B``, ... — the ids this suite's assertions read.

    Named rather than generated so the expected pair strings in the assertions below are
    readable, and so a failure says ``MN-A->MN-B`` rather than ``MN-0->MN-1``.
    """
    return f"MN-{chr(ord('A') + index)}"


def _signal(
    *,
    surface: str = "acquired",
    ref: str | None = None,
    arity_mode: str | None = None,
    polarity: Polarity = Polarity.ASSERTED,
    producer: str = "prose/one",
    kind: SignalKind = SignalKind.SYNTAX,
    subject: str = "MN-A",
    obj: str = "MN-B",
    direction: DirectionHypothesis = DirectionHypothesis.SUBJECT_TO_OBJECT,
    participants: int = 2,
    extra: dict | None = None,
) -> RelationSignal:
    del subject, obj
    declared = dict(extra or {})
    if arity_mode is not None:
        declared.setdefault("arity_mode", arity_mode)
    from semantic.contracts import RelationRef

    return RelationSignal(
        participants=tuple(
            RelationParticipant(
                mention_ref=_mention(index),
                slot=ArgumentSlot(index),
                ordinal=index,
            )
            for index in range(participants)
        ),
        kind=kind,
        relation_surface=surface,
        relation_ref=RelationRef(ref) if ref else None,
        basis=SignalBasis.EVENT_FRAME,
        polarity=polarity,
        neighbourhood=_NB,
        direction=direction,
        producer_ref=producer,
        context_ref="CX-1",
        semantic_regime_ref="RG-1",
        tenant_id="T1",
        extra=declared,
    )


# --------------------------------------------------------------------------- #
# The disagreement itself
# --------------------------------------------------------------------------- #


def _nary(
    participants: int = 3, *, roles: int | None = None, producer: str = "prose/quadruple", **over
) -> RelationSignal:
    """A signal whose declared shape is legal for a candidate.

    :class:`RelationCandidate` refuses a ``NARY`` candidate with fewer than two role
    assignments - correctly, because a claim built on it could never be promoted - so a
    disagreement involving ``nary`` has to state the roles, and that is the *agreement* case
    :func:`signal_corpus._expect_nary` already pins. The disagreement tests below therefore
    use ``directed`` against ``undirected``, which are both legal and are the pair of shapes
    a producer is most likely to disagree about.

    ``roles`` narrower than ``participants`` is the **partial set**: a producer that named two
    of three ends. It is legal and it is exactly the shape the deleted unanimity rule used to
    answer with ``()``, so it is the shape the role-slot axis has to be able to hold. Note the
    converse shape is *not* available as a test case: ``nary`` with no role assignments at all
    is refused by :class:`RelationCandidate` (``insufficient_role_assignments``) before
    assembly finishes, which is the candidate contract doing its own job and is why the
    role-slot disagreement has to be built from two sets rather than from a set and a silence.
    """
    over.setdefault("participants", participants)
    over.setdefault("arity_mode", "nary")
    over.setdefault("producer", producer)
    signal = _signal(**over)
    from dataclasses import replace

    return replace(
        signal,
        signal_id="",
        extra={
            **signal.extra,
            "role_bindings": tuple(
                (f"role{index}", _mention(index), "")
                for index in range(participants if roles is None else roles)
            ),
        },
    )


def test_two_producers_disagreeing_on_arity_yield_two_readings_and_a_conflict() -> None:
    """The whole of the fix, in one test: both readings, a report entry, and no winner.

    Two producers describe the same pair in incompatible shapes. Before Phase 4B that was one
    candidate whose shape came from a vote, and the producer that lost had no trace that it
    had ever said otherwise. Now the declared shape is part of the reading key - exactly as
    ``polarity`` and ``direction`` already were - so the disagreement is two readings of the
    pair, both attributed, both preserved, and the pair is named in the report.
    """
    report = assemble(
        [
            _signal(arity_mode="directed", producer="prose/active"),
            _signal(arity_mode="undirected", producer="prose/symmetric"),
        ],
        **_KWARGS,
    )
    assert len(report.candidates) == 2, [c.candidate_id for c in report.candidates]
    assert report.attributed_signal_count == 2
    assert report.complete
    assert report.unattributed_signal_ids == ()
    # Both readings survive, and neither has absorbed the other's signal.
    assert [len(c.signal_refs) for c in report.candidates] == [1, 1]
    assert sorted(c.arity_mode.value for c in report.candidates) == ["directed", "undirected"]
    # And the pair is reported as structurally contested, on both axes of the report.
    assert report.groups_with_structural_conflict == ("MN-A->MN-B",)
    assert report.groups_with_conflict == ("MN-A->MN-B",)
    detail = report.structural_conflicts
    assert len(detail) == 1
    pair, axis, _unused, seen = detail[0]
    assert pair == "MN-A->MN-B"
    assert axis == "arity_mode"
    assert sorted(seen.split(" | ")) == ["directed", "undirected"], seen


def test_a_three_participant_reading_against_a_binary_one_is_two_readings() -> None:
    """The case the vote was hiding: one producer read three ends and another read two.

    Under the old majority vote these were one candidate, and which shape it got depended on
    how many producers backed each. A tie went to whichever token sorted first, so a platform
    could report a **binary** relation that half its own producers had explicitly called
    three-ary, and the reader had no way to find out. Both are now readings of the pair, and
    the report says which pair and on which axis.
    """
    report = assemble(
        [
            _signal(arity_mode="directed", producer="prose/active", participants=2),
            _nary(participants=3),
        ],
        **_KWARGS,
    )
    assert len(report.candidates) == 2
    assert sorted(c.arity_mode.value for c in report.candidates) == ["directed", "nary"]
    assert report.groups_with_structural_conflict == ("MN-A->MN-B",)
    assert report.structural_conflicts[0][1] == "arity_mode"
    assert report.complete and report.attributed_signal_count == 2


def test_the_declared_arity_is_part_of_the_reading_key() -> None:
    """The mechanism, asserted on the function rather than through its effects.

    :func:`reading_key` is where the disagreement is *prevented* rather than resolved, so it
    is the thing to pin. ``arity_mode`` is the fifth of six components; a signal that states
    none and one that states ``directed`` must therefore be different readings, which is the
    property that makes :func:`_arity_of`'s members unanimous by construction. ``role_slots``
    is the sixth, added by Phase 4C, and the same argument applies to it.
    """
    plain = reading_key(_signal())
    directed = reading_key(_signal(arity_mode="directed"))
    nary = reading_key(_signal(arity_mode="nary"))
    assert plain[-2] == ""
    assert directed[-2] == "directed"
    assert nary[-2] == "nary"
    assert len({plain, directed, nary}) == 3
    # The other four components are unchanged, so this did not disturb polarity, surface, ref
    # or direction - a change to those would re-key every stored candidate. The sixth is the
    # role-slot set, empty for all three.
    assert plain[:4] == directed[:4] == nary[:4]
    assert plain[5] == directed[5] == nary[5] == ""


def test_polarity_is_read_from_the_field_and_not_from_the_kind() -> None:
    """M3's first half: the key reads :attr:`RelationSignal.polarity`, and it is the only place.

    Two signals about one pair, identical in every other respect, one denied through the field
    and one asserted through the field. Before, the key asked ``kind is SignalKind.NEGATION``
    and a signal that set ``polarity=Polarity.DENIED`` with any other kind was recorded as an
    *assertion* - which is the specific failure FR-015 exists to prevent: a denial silently
    becoming an assertion. Phase 4C then deleted the member, so there is no second way to say
    it and the field is the whole answer.
    """
    denied = _signal(polarity=Polarity.DENIED, kind=SignalKind.SYNTAX)
    asserted = _signal(polarity=Polarity.ASSERTED, kind=SignalKind.SYNTAX)
    assert reading_key(denied)[0] == "denied"
    assert reading_key(asserted)[0] == "asserted"
    assert reading_key(denied) != reading_key(asserted)
    report = assemble([denied, asserted], **_KWARGS)
    assert len(report.candidates) == 2
    assert {c.predicate_hypothesis is not None for c in report.candidates} == {True}
    assert report.groups_with_structural_conflict == ("MN-A->MN-B",)
    assert report.structural_conflicts[0][1] == "polarity"
    # And the kind no longer exists, so the axis can only be read from the field. Asserted here
    # rather than assumed: the bridge this replaces used to make the member overrule an explicit
    # `asserted`, and a member that has come back would do so again silently.
    assert "NEGATION" not in SignalKind.__members__


def test_a_structural_disagreement_never_becomes_a_contradicted_status() -> None:
    """``ARBITRATION`` §3, and the assertion a reader can check by eye.

    :attr:`CandidateStatus.CONTRADICTED` is reserved for "a positive reading versus an
    explicit denial" — the *assertion* was denied. A structural disagreement is not that: the
    two readings are incompatible in shape, and neither denies the other. So the flag is
    asserted across every shape of disagreement this module can produce, and the module's one
    construction site is asserted to say ``PROPOSE`` and nothing else, so "assembly never
    writes it" is a fact about the code rather than a coincidence of these inputs.
    """
    cases = {
        "arity": (_signal(arity_mode="directed"), _signal(arity_mode="undirected")),
        "direction": (
            _signal(direction=DirectionHypothesis.SUBJECT_TO_OBJECT),
            _signal(direction=DirectionHypothesis.UNDIRECTED),
        ),
        "polarity": (_signal(), _signal(polarity=Polarity.DENIED)),
    }
    for name, pair in cases.items():
        report = assemble(list(pair), **_KWARGS)
        assert len(report.candidates) == 2, name
        assert report.groups_with_structural_conflict == ("MN-A->MN-B",), name
        for candidate in report.candidates:
            assert candidate.candidate_status is CandidateStatus.PROPOSE, (
                f"{name}: assembly set {candidate.candidate_status!r}. A structural conflict "
                "is assembly_state = CONFLICTING, never candidate_status = CONTRADICTED "
                "(ARBITRATION §3)"
            )
    # And the source: one construction site, one literal status, and no other mention of
    # CONTRADICTED anywhere in the module. Read from the AST so a comment naming the member —
    # which is what the docstring above does — does not read as the code using it.
    source = (APPS / "semantic_path" / "assembly.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    statuses = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "CandidateStatus"
    ]
    assert set(statuses) == {"PROPOSE"}, statuses


def test_a_producer_contradicting_itself_is_refused_rather_than_voted_for() -> None:
    """The guard :func:`_arity_of` keeps after the vote was deleted.

    With ``arity_mode`` in the reading key, two *producers* cannot reach the same reading with
    different shapes - so a disagreement here is not four producers in two camps, it is one
    signal saying two things. That is a malformed record, and it is refused by name rather
    than resolved, because resolving it means recording a shape that half the record denies.
    """
    contradictory = RelationSignal(
        participants=tuple(
            RelationParticipant(mention_ref=f"MN-{i}", slot=ArgumentSlot(i), ordinal=i)
            for i in range(2)
        ),
        kind=SignalKind.SYNTAX,
        relation_surface="acquired",
        basis=SignalBasis.EVENT_FRAME,
        neighbourhood=_NB,
        producer_ref="prose/one",
        context_ref="CX-1",
        semantic_regime_ref="RG-1",
        tenant_id="T1",
        # Two shapes in one record's `extra` is not expressible through a producer, so it is
        # built by patching the frozen dataclass's own mapping - which is exactly the kind of
        # call the refusal has to survive.
        extra={"arity_mode": "directed"},
    )
    from dataclasses import replace

    from semantic_path.assembly import _arity_of

    with pytest.raises(AssemblyError) as caught:
        _arity_of([contradictory, replace(contradictory, signal_id="", extra={"arity_mode": "nary"})])
    assert caught.value.code == "structural_arity_disagreement"
    assert "directed" in str(caught.value) and "nary" in str(caught.value)


def test_an_unreadable_arity_is_refused_rather_than_defaulted() -> None:
    """A token no reader can interpret is a refusal, not a silent ``DIRECTED``.

    ``extra`` is the documented place for producer-specific labels, so a producer can put
    anything there - and "anything" includes a shape the platform has no member for. Silently
    treating it as a binary relation would record a shape the producer never stated.
    """
    from semantic_path.assembly import _arity_of

    with pytest.raises(AssemblyError) as caught:
        _arity_of([_signal(arity_mode="ternary-ish")])
    assert caught.value.code == "structural_arity_unreadable"
    assert "ternary-ish" in str(caught.value)
    # And the unstated case is a stated default rather than a guess: two participants and no
    # shape is a directed relation.
    assert _arity_of([_signal()]) is RelationArityMode.DIRECTED
    assert _arity_of([_signal(arity_mode="nary")]) is RelationArityMode.NARY


def test_the_report_field_is_a_projection_of_the_candidate_verdict() -> None:
    """The inversion of the tripwire that used to sit here, and the proof it is a projection.

    ``ARBITRATION`` §3 puts the structural verdict on
    :attr:`RelationCandidate.assembly_state`. The field exists, assembly writes it, and
    :attr:`~semantic_path.assembly.AssemblyReport.groups_with_structural_conflict` is now a
    **property over the candidates** rather than a stored field.

    A projection is proved the only way it can be: by constructing the report's inputs by hand and
    reading the field back. Two constructions here, and each isolates one claim:

    * a report over a **real** assembly must list the contested pair, and every reading of it must
      carry ``CONFLICTING`` — the two cannot be produced independently;
    * a report over a **hand-built candidate set** must answer from that set alone, and must go
      empty when the same candidates' verdicts are flipped to ``CONSISTENT``. A stored field cannot
      do either: it was written when the report was constructed and reads back whatever was put in
      it, so the second case is the one that distinguishes a projection from a copy.
    """
    report = assemble(
        [
            _signal(arity_mode="directed"),
            _signal(arity_mode="undirected", producer="prose/two"),
        ],
        **_KWARGS,
    )
    # Every reading of the contested pair carries the verdict, not only the minority one: the
    # disagreement is about the configuration, and sitting on one side of it does not make a
    # reading consistent.
    assert [c.assembly_state for c in report.candidates] == [
        CandidateAssemblyState.CONFLICTING
    ] * 2
    assert all(c.is_structurally_contested for c in report.candidates)
    assert report.groups_with_structural_conflict == ("MN-A->MN-B",)
    assert report.to_dict()["groups_with_structural_conflict"] == ["MN-A->MN-B"]
    assert report.structural_conflicts, "the axis elaboration is still reported"

    # The field is not a constructor parameter and not a stored attribute, so there is no second
    # copy of the verdict to keep in step.
    assert "groups_with_structural_conflict" not in {
        field.name for field in fields(AssemblyReport)
    }
    assert isinstance(
        AssemblyReport.groups_with_structural_conflict, property
    ), "the report must derive the pair list, not store it"

    # And the projection answers from the candidates: rebuild a report over them directly.
    rebuilt = AssemblyReport(
        signal_count=report.signal_count,
        attributed_signal_count=report.attributed_signal_count,
        group_count=report.group_count,
        candidates=report.candidates,
        groups_with_conflict=report.groups_with_conflict,
        unattributed_signal_ids=report.unattributed_signal_ids,
    )
    assert rebuilt.groups_with_structural_conflict == ("MN-A->MN-B",)

    # Flip the verdict on the candidates and the projection follows them. A stored field would
    # still say MN-A->MN-B here, which is the whole difference. The ids are dropped and
    # re-derived because they are *verified* on construction: a candidate that carried an id its
    # own content no longer addresses to is refused, which is I-1 working.
    agreed = tuple(
        replace(
            c,
            assembly_state=CandidateAssemblyState.CONSISTENT,
            candidate_id="",
            logical_candidate_id="",
        ).with_id()
        for c in report.candidates
    )
    assert AssemblyReport(
        signal_count=0,
        attributed_signal_count=0,
        group_count=0,
        candidates=agreed,
        groups_with_conflict=(),
        unattributed_signal_ids=(),
    ).groups_with_structural_conflict == ()


def test_a_disagreement_on_shape_is_never_written_as_a_denial() -> None:
    """``ARBITRATION`` §3 from the candidate side: the two axes are separate fields.

    Read off the assembled candidates rather than off the report, because the report is a
    projection of them and a test on the projection would pass with two truths underneath. The
    three assertions are one claim: on a structural disagreement the candidate says
    ``assembly_state = CONFLICTING`` and ``candidate_status = PROPOSE``, and it says so for every
    shape of disagreement the module can produce.
    """
    cases = {
        "arity": (_signal(arity_mode="directed"), _signal(arity_mode="undirected")),
        "direction": (
            _signal(direction=DirectionHypothesis.SUBJECT_TO_OBJECT),
            _signal(direction=DirectionHypothesis.UNDIRECTED),
        ),
        "polarity": (_signal(), _signal(polarity=Polarity.DENIED)),
    }
    for name, pair in cases.items():
        report = assemble(list(pair), **_KWARGS)
        assert len(report.candidates) == 2, name
        for candidate in report.candidates:
            assert candidate.assembly_state is CandidateAssemblyState.CONFLICTING, name
            assert candidate.candidate_status is CandidateStatus.PROPOSE, (
                f"{name}: assembly set {candidate.candidate_status!r}. A structural conflict "
                "is assembly_state = CONFLICTING, never candidate_status = CONTRADICTED "
                "(ARBITRATION §3)"
            )
    # And agreement is CONSISTENT, so the default is not a value that merely happens to be
    # written on every conflict.
    agreed = assemble([_signal(producer="prose/a"), _signal(producer="prose/b")], **_KWARGS)
    assert len(agreed.candidates) == 1
    assert agreed.candidates[0].assembly_state is CandidateAssemblyState.CONSISTENT
    assert agreed.candidates[0].is_structurally_contested is False
    assert agreed.groups_with_structural_conflict == ()


def test_the_report_is_serialisable_and_order_independent() -> None:

    """Constitution VI, and the two new fields are not an exception to it.

    The structural fields are derived from a ``set`` comprehension over the readings, so their
    order comes from hash order unless it is pinned. Both are sorted before they are returned,
    and this asserts it by assembling the same signals in two orders and comparing the whole
    ``to_dict`` - not just the candidate ids, which was the weaker check that let the
    unsorted version pass.
    """
    signals = [
        _signal(arity_mode="directed", producer="prose/a"),
        _signal(arity_mode="undirected", producer="prose/b"),
        _nary(participants=3, producer="prose/c"),
    ]
    forwards = assemble(signals, **_KWARGS).to_dict()
    backwards = assemble(list(reversed(signals)), **_KWARGS).to_dict()
    assert forwards == backwards
    assert forwards["structural_conflicts"] == sorted(forwards["structural_conflicts"])


def test_agreement_on_shape_is_still_one_reading() -> None:
    """The other half of putting arity in the key: agreement must not fork.

    A key that separated every signal would be as wrong as a vote that discarded the minority.
    Two producers stating the same shape are corroborating one reading, and FR-034's
    independence count is computed over exactly that.
    """
    report = assemble(
        [
            _nary(participants=3, producer="prose/active"),
            _nary(participants=3, producer="prose/passive"),
        ],
        **_KWARGS,
    )
    assert len(report.candidates) == 1
    assert report.candidates[0].arity_mode is RelationArityMode.NARY
    assert len(report.candidates[0].signal_refs) == 2
    assert report.groups_with_structural_conflict == ()
    assert report.structural_conflicts == ()


# --------------------------------------------------------------------------- #
# C2: role slots, the fourth structural axis
# --------------------------------------------------------------------------- #


def test_two_producers_disagreeing_on_role_slots_yield_two_readings_and_a_conflict() -> None:
    """``ARBITRATION`` §3's fourth axis, and the sentence it had not implemented.

    §3 says a candidate carries ``assembly_state = CONFLICTING`` when "producers disagree on
    arity, direction, polarity **or role slots**". Three of those four were implemented; the
    fourth was answered by :func:`_roles_of` returning ``()``, so a producer that named the
    slots of a configuration and a producer that named none produced **one** candidate and the
    naming was lost. Now: two readings, both attributed, both ``CONFLICTING``, and the pair is
    reported under ``role_slots`` with both declared sets spelled out so a reader can see what
    the disagreement was.
    """
    # ``arity_mode`` and the participant tuple are stated identically on both sides, so the
    # *only* component that can differ is role slots. A test that let the arity differ would
    # pass with the axis still missing.
    partial = _nary(participants=3, roles=2, producer="schema/partial")
    complete = _nary(participants=3, roles=3, producer="schema/complete")
    report = assemble([partial, complete], **_KWARGS)
    assert len(report.candidates) == 2, [c.candidate_id for c in report.candidates]
    assert report.attributed_signal_count == 2
    assert report.complete
    assert [len(c.signal_refs) for c in report.candidates] == [1, 1]
    # Both readings carry the verdict, and both are preserved — the finding is not on one side.
    assert [c.assembly_state for c in report.candidates] == [
        CandidateAssemblyState.CONFLICTING
    ] * 2
    assert report.groups_with_structural_conflict == ("MN-A->MN-B",)
    axes = {axis for _, axis, _, _ in report.structural_conflicts}
    assert axes == {"role_slots"}, report.structural_conflicts
    # The axis entry spells both declarations out, so the report says *what* was disagreed
    # about rather than only that something was.
    _pair, _axis, _unused, seen = report.structural_conflicts[0]
    assert '[["role0","MN-A",""],["role1","MN-B",""]]' in seen, seen
    assert '["role0","MN-A",""],["role1","MN-B",""],["role2","MN-C",""]' in seen, seen
    assert all(c.candidate_status is CandidateStatus.PROPOSE for c in report.candidates)
    # One logical hypothesis, two readings: the verdict is revision material, so putting it on
    # the candidate must not fork the identity the disagreement is about.
    assert len({c.logical_candidate_id for c in report.candidates}) == 1


def test_a_partial_role_set_is_a_finding_and_not_an_empty_tuple() -> None:
    """The specific swallow 4C deletes, asserted from both sides of it.

    Two producers, one pair, the same three ends and the same declared arity: one named the
    role slots of two of the three ends, the other named all three. Before, ``_roles_of``
    answered that with ``()`` — one candidate, no roles, ``CONSISTENT``, and a producer that
    had genuinely read two slots indistinguishable from one that had read none. The partial set
    is now the *named* reading: it carries exactly the two bindings it declared, the other
    carries three, and the pair is ``CONFLICTING`` on ``role_slots``.

    The two middle assertions are the ones the old code got wrong: **a partial set is not the
    same thing as no set**, and it is not a set that may be quietly completed from the other
    producer's reading either.
    """
    partial = _nary(participants=3, roles=2, producer="schema/partial")
    complete = _nary(participants=3, roles=3, producer="schema/complete")
    report = assemble([partial, complete], **_KWARGS)
    two_slots = next(c for c in report.candidates if c.signal_refs == (partial.signal_id,))
    three_slots = next(c for c in report.candidates if c.signal_refs == (complete.signal_id,))
    assert len(two_slots.role_assignments) == 2, two_slots.role_assignments
    assert {b.role for b in two_slots.role_assignments} == {"role0", "role1"}
    assert len(three_slots.role_assignments) == 3
    # Neither reading absorbed the other's third binding: a completed set would be a role
    # assignment no producer stated, and the two readings would stop being two readings.
    assert {b.role for b in three_slots.role_assignments} == {"role0", "role1", "role2"}
    assert all(c.assembly_state is CandidateAssemblyState.CONFLICTING for c in report.candidates)
    assert report.structural_conflicts, "a partial role set is a finding, not a tuple"


def test_a_reading_whose_members_agree_on_roles_is_still_one_reading() -> None:
    """The other half, and the one a key that separated everything would get wrong.

    Two producers naming the *same* role slots are corroborating one reading, and FR-034's
    independence count is computed over exactly that. If role slots in the key could fork a
    pair, corroboration would arrive as a conflict — which is the same failure the arity axis
    had to be checked for.
    """
    report = assemble(
        [
            _nary(participants=3, producer="schema/active"),
            _nary(participants=3, producer="schema/passive"),
        ],
        **_KWARGS,
    )
    assert len(report.candidates) == 1
    assert len(report.candidates[0].signal_refs) == 2
    assert report.candidates[0].role_assignments, "the declared roles did not survive"
    assert report.groups_with_structural_conflict == ()
    assert report.structural_conflicts == ()


def test_nobody_declaring_roles_is_silence_and_not_a_finding() -> None:
    """Six of the seven producers say nothing about roles, and that must stay legal.

    A stated silence is not a disagreement. If an undeclared role set were treated as a finding
    the platform would refuse almost every signal it can currently read, so the empty case is
    pinned here explicitly rather than left as the accidental consequence of a ``return ()``.
    """
    report = assemble(
        [_signal(producer="lexical/a"), _signal(producer="lexical/b")], **_KWARGS
    )
    assert len(report.candidates) == 1
    assert report.candidates[0].role_assignments == ()
    assert report.candidates[0].assembly_state is CandidateAssemblyState.CONSISTENT
    assert report.structural_conflicts == ()


def test_role_slots_are_part_of_the_reading_key_and_are_rendered_injectively() -> None:
    """The mechanism, plus the reason the component is JSON rather than a joined string.

    The key has to separate the declarations, and it has to do so without two *different*
    declarations rendering to the same component — a separator-joined rendering would merge
    them, and the axis would then report agreement between two producers who disagree. The
    adversarial case below is a role name that contains the separator, which is reachable
    because a role is free text.
    """
    from semantic_path.assembly import _render_role_slots, role_slots_of

    plain = _signal(extra={"role_bindings": (("seller", "MN-A", "org"),)})
    named = _signal(
        producer="schema/declared",
        extra={"role_bindings": (("vendor", "MN-A", "org"),)},
    )
    assert reading_key(plain) != reading_key(named)
    assert role_slots_of(plain) == (("seller", "MN-A", "org"),)
    # Injection: a role word containing the separator must not collide with a different set.
    tricky = _signal(extra={"role_bindings": (("a|b", "MN-A", "org"),)})
    other = _signal(extra={"role_bindings": (("a", "b|MN-A", "org"),)})
    assert _render_role_slots(role_slots_of(tricky)) != _render_role_slots(
        role_slots_of(other)
    )
    # Order-independent: a set read in either order is one component.
    forward = _signal(extra={"role_bindings": (("a", "MN-A", ""), ("b", "MN-B", ""))})
    backward = _signal(extra={"role_bindings": (("b", "MN-B", ""), ("a", "MN-A", ""))})
    assert role_slots_of(forward) == role_slots_of(backward)
    assert reading_key(forward) == reading_key(backward)


def test_an_unreadable_role_binding_is_refused_rather_than_treated_as_absent() -> None:
    """The same guard shape as :func:`_arity_of`, and for the same reason.

    A binding that is neither a :class:`~domain.relation_candidate.RelationRoleBinding` nor a
    three-element sequence is a declaration nobody can read. Treating it as "no roles declared"
    is the swallow this phase deletes, in a second costume: the candidate assembles with fewer
    roles than the producer wrote down and nothing anywhere says one was dropped.
    """
    malformed = _signal(extra={"role_bindings": ("seller",)})
    with pytest.raises(AssemblyError) as caught:
        reading_key(malformed)
    assert caught.value.code == "role_slot_unreadable"
    assert malformed.signal_id in str(caught.value)
    assert "seller" in str(caught.value)


def test_a_signal_contradicting_itself_on_roles_is_refused_not_voted_for() -> None:
    """The guard :func:`_roles_of` keeps after the unanimity rule was deleted.

    With role slots in the key, two *producers* cannot reach one reading with different sets —
    so a disagreement here is not two producers in two camps, it is one record saying two
    things. That is a malformed record, and it is refused by name rather than resolved, because
    resolving it means recording a role set the record itself denies.
    """
    from semantic_path.assembly import _roles_of

    self_contradicting = _signal(extra={"role_bindings": (("seller", "MN-A", ""),)})
    with pytest.raises(AssemblyError) as caught:
        _roles_of(
            [
                self_contradicting,
                replace(
                    self_contradicting,
                    signal_id="",
                    extra={"role_bindings": (("vendor", "MN-A", ""),)},
                ),
            ]
        )
    assert caught.value.code == "role_slot_disagreement"
    assert "seller" in str(caught.value) and "vendor" in str(caught.value)
    assert "ARBITRATION" in str(caught.value)


def test_role_slots_is_the_fourth_structural_axis_and_the_axis_set_is_pinned() -> None:
    """``_STRUCTURAL_AXES`` is a constant, so its membership is a claim and is asserted.

    Read from the module rather than restated here, because a test that hard-codes the same
    four positions would keep passing after a fifth axis was added and the reader would never
    learn that ``ARBITRATION`` §3 had grown a name. Positions 1 and 2 must stay *semantic*:
    two surfaces and two operators are two claims about the world, not two shapes of one claim.
    """
    from semantic_path import assembly

    assert set(assembly._READING_AXES) == {0, 3, 4, 5}
    assert set(assembly._READING_AXES.values()) == {
        "polarity",
        "direction",
        "arity_mode",
        "role_slots",
    }
    assert assembly._STRUCTURAL_AXES == frozenset({0, 3, 4, 5})
    # And the semantic positions are excluded, named by their index rather than by absence.
    assert assembly._READING_AXES.get(1) is None
    assert assembly._READING_AXES.get(2) is None
    # A semantic-only disagreement is a conflict about the world and is not structural.
    semantic_only = assemble(
        [
            _signal(surface="CEO of", ref="works_for", producer="lexical/1"),
            _signal(surface="founder of", ref="founded", producer="table/1"),
        ],
        **_KWARGS,
    )
    assert len(semantic_only.candidates) == 2
    assert semantic_only.groups_with_conflict == ("MN-A->MN-B",)
    assert semantic_only.structural_conflicts == (), semantic_only.structural_conflicts
    assert semantic_only.candidates[0].assembly_state is CandidateAssemblyState.CONSISTENT


# --------------------------------------------------------------------------- #
# The mutation tests: restore each half of the defect and the guard must notice
# --------------------------------------------------------------------------- #

_MUTATION_SCRIPT = """
import sys
sys.path.insert(0, ".")
from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_candidate import CandidateStatus
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis
from extractors.signals import DirectionHypothesis, Neighbourhood, RelationSignal, SignalKind
from semantic_path.assembly import assemble, AssemblyReport

nb = Neighbourhood(characters_scanned=64, pairs_considered=0, scope_read="one clause")


def signal(arity, producer="prose/one", polarity=Polarity.ASSERTED):
    return RelationSignal(
        participants=tuple(
            RelationParticipant(mention_ref=f"MN-{chr(ord('A') + i)}", slot=ArgumentSlot(i), ordinal=i)
            for i in range(2)
        ),
        kind=SignalKind.SYNTAX, relation_surface="acquired", basis=SignalBasis.EVENT_FRAME,
        polarity=polarity, neighbourhood=nb, direction=DirectionHypothesis.SUBJECT_TO_OBJECT,
        producer_ref=producer, context_ref="CX-1", semantic_regime_ref="RG-1", tenant_id="T1",
        extra={"arity_mode": arity},
    )


kw = dict(tenant_id="T1", context_ref="CX-1", semantic_regime_ref="RG-1")
report = assemble([signal("directed"), signal("undirected")], **kw)
print("CANDIDATES", len(report.candidates))
print("ATTRIBUTED", report.attributed_signal_count)
print("STRUCTURAL", report.groups_with_structural_conflict)
print("SHAPES", sorted(c.arity_mode.value for c in report.candidates))
print("STATUSES", sorted(str(c.candidate_status) for c in report.candidates))
print("ASSEMBLY", sorted(str(c.assembly_state) for c in report.candidates))
# The guard from test_a_structural_disagreement_never_becomes_a_contradicted_status, restated
# so the mutated child can be compared against the unmutated one rather than against a claim.
print("GUARD", all(c.candidate_status is CandidateStatus.PROPOSE for c in report.candidates))
print("REPORT_PROJECTION", "groups_with_structural_conflict" not in {
    field for field in AssemblyReport.__dataclass_fields__
})
"""



def _mutated_module(*edits: tuple[str, str]) -> Path:
    """A throwaway copy of the four packages with Phase 4B's two edits in ``assembly.py`` undone.

    Flat, because one ``PYTHONPATH`` entry is the only thing a child interpreter needs. The
    repository is never written to: the same discipline
    :mod:`test_constitution_has_teeth` uses, for the same reason. Several edits are taken in
    order, and each is anchored, so a mutation that no longer finds its target fails loudly
    rather than silently producing a module that differs in some other way.
    """
    root = Path(tempfile.mkdtemp(prefix="assembly-mutation-"))
    for package in ("domain", "semantic", "extractors", "semantic_path"):
        source = APPS / package
        if source.is_dir():
            shutil.copytree(
                source, root / source.name, ignore=shutil.ignore_patterns("__pycache__")
            )
    target = (root / "semantic_path" / "assembly.py").resolve()
    text = target.read_text(encoding="utf-8")
    for find, replacement in edits:
        assert find in text, f"mutation anchor not found in assembly.py: {find[:80]!r}"
        text = text.replace(find, replacement, 1)
    target.write_text(text, encoding="utf-8")
    return root



def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return _run_script(root, _MUTATION_SCRIPT)


def _run_script(root: Path, script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
        check=False,
    )


def test_restoring_the_majority_vote_fails_this_file() -> None:
    """The mutation, and the reason it is worth the subprocess.

    **Both** halves of the Phase 4B fix are undone, because they are one fix. The declared
    shape leaves the reading key - which is what made the two producers' readings *the same*
    reading - and the tally plus the alphabetical tie-break go back into :func:`_arity_of`.
    Undoing only the first would leave the guard in place and the child would raise
    ``structural_arity_disagreement``, which is a louder failure but not the *defect*: the
    pre-4B behaviour was one candidate whose shape came out of a sort order, and reproducing
    that is what makes the difference a demonstration rather than an illustration.

    A child interpreter reports what the unmutated contract does and what the mutated one does,
    and the difference is asserted in both directions. Without the mutation, "the two
    producers' disagreement is now two readings" is a claim about code nobody ran twice.
    """
    unmutated = _run(APPS)
    assert unmutated.returncode == 0, unmutated.stderr[-2000:]
    assert "CANDIDATES 2" in unmutated.stdout, unmutated.stdout
    assert "SHAPES ['directed', 'undirected']" in unmutated.stdout, unmutated.stdout
    assert "STRUCTURAL ('MN-A->MN-B',)" in unmutated.stdout, unmutated.stdout
    assert "ASSEMBLY ['conflicting', 'conflicting']" in unmutated.stdout, unmutated.stdout
    assert "GUARD True" in unmutated.stdout, unmutated.stdout
    assert "REPORT_PROJECTION True" in unmutated.stdout, unmutated.stdout

    root = _mutated_module(
        (
            '        str(signal.extra.get("arity_mode") or ""),\n',
            "",
        ),
        (
            """    if len(stated) > 1:
        raise AssemblyError(
            "structural_arity_disagreement",""",
            """    if False:
        raise AssemblyError(
            "structural_arity_disagreement",""",
        ),
        (
            """    try:
        return RelationArityMode(next(iter(stated)))""",
            """    counts: dict[str, int] = {}
    for mode in stated:
        counts[mode] = counts.get(mode, 0) + 1
    winner = min(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    try:
        return RelationArityMode(winner)""",
        ),
    )
    try:
        mutated = _run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert mutated.returncode == 0, mutated.stderr[-2000:]
    assert "CANDIDATES 1" in mutated.stdout, (
        "restoring the majority vote did NOT collapse the two readings, so the guard this "
        f"file exists for is fixing itself by something else: {mutated.stdout!r}"
    )
    assert "STRUCTURAL ()" in mutated.stdout, mutated.stdout
    assert "SHAPES ['directed']" in mutated.stdout, (
        "with the vote restored the winner must be the alphabetically-first token, because "
        "that is precisely the defect: a shape chosen by a dictionary's collation"
    )
    assert "ATTRIBUTED 2" in mutated.stdout, (
        mutated.stdout,
        (
            "the losing signal must still be attributed - the vote merged the readings, it "
            "did not drop an observation, and a vote that also lost a signal would be two "
            "defects"
        ),
    )
    # And the collapse is a *structural* disagreement going missing, not just a shape changing:
    # the mutated child has one reading, so it agrees with itself and carries CONSISTENT. That
    # is the defect named in one line - a disagreement the platform cannot see is a disagreement
    # nobody was told about.
    assert "ASSEMBLY ['consistent']" in mutated.stdout, mutated.stdout


def test_writing_the_conflict_as_contradicted_fails_this_file() -> None:
    """The second mutation, and the other half of ``ARBITRATION`` §3.

    The first mutation restores the *vote*. This one restores the *collapse of the two axes*: the
    construction site's status literal is changed from ``PROPOSE`` to ``CONTRADICTED``, which is
    precisely what A6 was forbidden from doing and precisely what the ``assembly_state`` field
    exists so nobody has to.

    It is the same harness for the same reason — an in-process assertion that a string is absent
    from a source file cannot show that the absence is what makes the guard pass, whereas running
    the mutated module and watching the guard's own condition come back ``False`` can. The status
    is also left as a *label* rather than a state change, so the child still runs: this is the
    shape the defect takes in practice, a reading that looks checked and failed because the
    assembler labelled it that way.
    """
    unmutated = _run(APPS)
    assert unmutated.returncode == 0, unmutated.stderr[-2000:]
    assert "STATUSES ['propose', 'propose']" in unmutated.stdout, unmutated.stdout
    assert "GUARD True" in unmutated.stdout, unmutated.stdout

    root = _mutated_module(
        (
            "        candidate_status=CandidateStatus.PROPOSE,",
            "        candidate_status=CandidateStatus.CONTRADICTED,",
        ),
    )
    try:
        mutated = _run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert mutated.returncode == 0, mutated.stderr[-2000:]
    assert "STATUSES ['contradicted', 'contradicted']" in mutated.stdout, mutated.stdout
    assert "GUARD False" in mutated.stdout, (
        "putting the structural conflict on CandidateStatus.CONTRADICTED did NOT trip the guard, "
        f"so the guard is not guarding: {mutated.stdout!r}"
    )
    # And the structural verdict itself is unaffected, which is the point: the two axes are
    # separate, so breaking one leaves the other intact and the guard above is what notices.
    assert "ASSEMBLY ['conflicting', 'conflicting']" in mutated.stdout, mutated.stdout



def test_the_arity_vote_and_its_alphabetical_tiebreak_are_gone_from_the_source() -> None:
    """The deletion, asserted on the source, because a vote is easy to reintroduce by accident.

    Two things must not come back: the tally, and the ``min(counts.items(), key=...)`` that
    broke its ties. The tie-break is the more dangerous of the two, because it *looks*
    deterministic - constitution VI is satisfied, two processes agree, the result is stable -
    and the thing it is deterministic about is a dictionary's collation. Read from the AST so
    a docstring naming the vote does not read as the vote being present.
    """
    source = (APPS / "semantic_path" / "assembly.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "min" and node.keywords:
            offender = [k for k in node.keywords if k.arg == "key"]
            assert not offender, (
                f"assembly.py:{node.lineno} uses min(..., key=...) - a lexicographic tie-break. "
                "A disagreement resolved by collation is a disagreement resolved by a "
                "dictionary, whatever constitution VI says about determinism"
            )
    # And the counts dictionary the tally used is gone with it.
    assert 'counts: dict[str, int]' not in source
    assert "item: (-item[1], item[0])" not in source
    # The return annotation is the platform's own enum, not `Any`, so a caller gets the type
    # and a future mismatch is caught by a checker rather than by a reader.
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_arity_of"
    )
    assert ast.unparse(function.returns) == "RelationArityMode", ast.unparse(function.returns)


def test_restoring_the_role_slot_unanimity_rule_fails_this_file() -> None:
    """The Phase 4C mutation: put the partial set back, and the guards must notice.

    **Both** halves of the C2 fix are undone, because they are one fix and only the second half
    is visible. The declared role slots leave the reading key — so the two producers' readings
    are *the same* reading again — and :func:`_roles_of` goes back to answering a disagreement
    with ``()``.

    **The mutation does not produce "one candidate with no roles". It produces a crash, and the
    crash is the finding.** :class:`RelationCandidate` refuses a ``NARY`` candidate with fewer
    than two role assignments (``insufficient_role_assignments``), so swallowing the partial
    set does not merely lose the disagreement — it hands the candidate contract a ``nary``
    reading with nothing in ``role_assignments`` and the **whole batch fails to assemble**. One
    producer that named two of three slots used to take every other signal on the pair down with
    it, and the error a caller saw named role assignments rather than the producer or the pair.

    So this mutation is asserted as a *failure*, and the failure is checked by name: the point
    is not that the count is smaller, it is that the disagreement is no longer survivable.
    """
    script = """
from domain.predicate_signature import ArgumentSlot
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis
from extractors.signals import DirectionHypothesis, Neighbourhood, RelationSignal, SignalKind
from semantic_path.assembly import assemble

nb = Neighbourhood(characters_scanned=64, pairs_considered=0, scope_read="one clause")


def signal(producer, roles):
    def end(i):
        return RelationParticipant(
            mention_ref=f"MN-{chr(ord('A') + i)}", slot=ArgumentSlot(i), ordinal=i
        )

    return RelationSignal(
        participants=tuple(end(i) for i in range(3)),
        kind=SignalKind.SYNTAX, relation_surface="acquired", basis=SignalBasis.EVENT_FRAME,
        neighbourhood=nb,
        producer_ref=producer, context_ref="CX-1", semantic_regime_ref="RG-1", tenant_id="T1",
        extra={"arity_mode": "nary",
               "role_bindings": tuple((f"role{i}", f"MN-{chr(ord('A') + i)}", "") for i in range(roles))},
    )


report = assemble(
    [signal("p/partial", 2), signal("p/complete", 3)],
    tenant_id="T1", context_ref="CX-1", semantic_regime_ref="RG-1",
)
print("CANDIDATES", len(report.candidates))
print("STRUCTURAL", report.groups_with_structural_conflict)
print("AXES", sorted({axis for _p, axis, _u, _s in report.structural_conflicts}))
print("ROLES", sorted(len(c.role_assignments) for c in report.candidates))
print("ASSEMBLY", sorted(str(c.assembly_state) for c in report.candidates))
print("ATTRIBUTED", report.attributed_signal_count)
"""
    unmutated = _run_script(APPS, script)
    assert unmutated.returncode == 0, unmutated.stderr[-2000:]
    assert "CANDIDATES 2" in unmutated.stdout, unmutated.stdout
    assert "STRUCTURAL ('MN-A->MN-B',)" in unmutated.stdout, unmutated.stdout
    assert "AXES ['role_slots']" in unmutated.stdout, unmutated.stdout
    assert "ROLES [2, 3]" in unmutated.stdout, unmutated.stdout
    assert "ASSEMBLY ['conflicting', 'conflicting']" in unmutated.stdout, unmutated.stdout
    assert "ATTRIBUTED 2" in unmutated.stdout, unmutated.stdout

    root = _mutated_module(
        (
            "    slots = role_slots_of(signal)\n",
            "    slots = ()\n",
        ),
        (
            """    distinct = {slots for slots in stated}
    if len(distinct) > 1:""",
            """    distinct = {slots for slots in stated}
    if len(distinct) != 1:
        return ()
    if False:""",
        ),
    )
    try:
        mutated = _run_script(root, script)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert mutated.returncode != 0, (
        "restoring the unanimity rule did NOT break the batch, so the guards in this file are "
        f"not guarding the partial-set swallow: {mutated.stdout!r}"
    )
    assert "an nary candidate needs at least two role assignments, got 0" in mutated.stderr, (
        f"the batch failed, but not for the reason the swallow predicts — if it failed some "
        f"other way the swallow may not be what broke it: {mutated.stderr[-2000:]}"
    )


# --------------------------------------------------------------------------- #
# The scope has to exist, or the refusals above are testing a fiction
# --------------------------------------------------------------------------- #


def test_the_extraction_scope_still_requires_a_frame_and_a_regime() -> None:
    """One line, and it is here because every test above builds a scope.

    Assembly's requirement that a frame and a regime be supplied rather than defaulted belongs
    to the same family as this file's subject: a decision somebody else made must not be
    substituted. If a default were reintroduced, the ids above would be computed under a frame
    nobody chose, and nothing else here would notice.
    """
    from extractors.signals.signal import SignalContractError

    with pytest.raises(SignalContractError) as caught:
        ExtractionScope(tenant_id="T1", context_ref="", semantic_regime_ref="RG-1")
    assert caught.value.code == "extraction_scope_reference_required"




