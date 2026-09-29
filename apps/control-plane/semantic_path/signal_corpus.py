"""The signal corpus: what producers see, and what assembly makes of it.

Feature 019, T039. The golden corpus in :mod:`semantic_path.corpus` drives the *whole*
semantic path, and every case in it needs a resolution universe built for its own sentence -
which is correct, and also means it cannot cheaply cover a producer that has not been
resolved yet. This corpus covers the layer 019 actually added: producers → signals →
candidates, which runs **before** resolution and therefore needs no universe at all.

**The ten scenarios are the ones T039 names**, and each exists because the behaviour it
covers is a decision somebody made rather than a mechanism that followed:

1. ``active_passive`` - one relation, two grammatical realisations, distinguishable
   surface evidence. T035's finding, pinned as a case: one logical candidate, two readings.
2. ``nary_event`` - a three-participant event. The only place role bindings appear, and
   where a partial set would be a malformed claim.
3. ``unknown_relation`` - a relation the vocabulary has no entry for. CD-6 end to end.
4. ``link`` - a hyperlink, untyped and undirected.
5. ``table`` - a table header the platform cannot type, which is FR-028 in one case.
6. ``metadata`` - a document stating an author, with the four-way byline ambiguity intact.
7. ``text_vs_table`` - the same relation seen two ways, disagreeing. Two candidates.
8. ``triple_corroboration`` - three producers on one pair. One candidate, three signal refs,
   and FR-034's independence count has three sources to count.
9. ``attribute_value`` - a key/value field, which is neither prose nor markup.
10. ``document_hierarchy`` - containment by position, which is a relation and not a
    typographic detail.

Each case is a ``(name, input, expectations)`` triple rather than a class, so the table below
is the corpus and reading it is reading the specification. The expectations are *derived* from
the run and compared to a **recorded digest**, so a change in any id, in the grouping, or in
the number of candidates shows up as a diff rather than as a silently different graph.

Replay is a fixed point: assembling the same signals twice gives the same candidates, and
re-running the whole corpus gives the same total. That is SC-I at this layer, and it holds
without a store because every id here is content-addressed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_candidate import CandidateAssemblyState
from domain.relation_identity import canonical_material, digest128
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis
from extractors.signals import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalKind,
)
from extractors.signals.links import link_signals
from extractors.signals.metadata import metadata_signals
from extractors.signals.tables import list_signals, table_signals
from semantic.contracts import RelationRef

from semantic_path.assembly import assemble
from semantic_path.execution import ExtractionScope

SCOPE = ExtractionScope(
    tenant_id="T1", context_ref="CX-corpus", semantic_regime_ref="RG-corpus", document_ref="CAP-corpus"
)
ASSEMBLE_KW = {
    "tenant_id": "T1", "context_ref": "CX-corpus", "semantic_regime_ref": "RG-corpus"
}


@dataclass(frozen=True)
class SignalCase:
    """One scenario: what the producers were given, and what must come out."""

    name: str
    #: What a producer is handed. A string for prose and markup alike, because that is what
    #: :func:`extractors.signals.lexical.lexical_signals` takes, and the producers that
    #: accept a mapping take one.
    input: str
    #: ``(producer name, callable taking (input, scope))``.
    producers: tuple[tuple[str, Callable[[str, Any], tuple[RelationSignal, ...]]], ...]
    #: What the case must satisfy, checked as assertions over the report *and* the signals
    #: that produced it, and returning a mapping of **what it actually verified**.
    #:
    #: The return value is what makes a case's digest worth recording. Four of these cases
    #: exercise the assembler directly rather than through a producer, so their own run has
    #: no signals and an identical empty digest to each other - a corpus that cannot say
    #: which case changed is not a baseline. Having the expectation report the ids it
    #: asserted on means every case's digest covers the thing it is about.
    expect: Callable[[Any, tuple[RelationSignal, ...]], Mapping[str, Any]]
    #: Free text, so the table of cases reads as a specification.
    rationale: str = ""
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class SignalCaseRun:
    """One case, run: its signals, its candidates, and its digest."""

    name: str
    signals: tuple[RelationSignal, ...]
    report: Any
    digest: str
    rationale: str = ""
    labels: tuple[str, ...] = ()
    detail: Mapping[str, Any] = field(default_factory=dict)


def _declared(
    subject: str,
    obj: str,
    surface: str,
    *,
    ref: str | None = None,
    producer: str = "request/declaration",
    kind: SignalKind = SignalKind.SCHEMA,
    direction: DirectionHypothesis = DirectionHypothesis.SUBJECT_TO_OBJECT,
    basis: SignalBasis = SignalBasis.EVENT_FRAME,
    polarity: Polarity = Polarity.ASSERTED,
    extra: Mapping[str, Any] | None = None,
) -> RelationSignal:
    """A declared or synthetic signal, for the cases that need one the producers cannot make.

    **On the native participant path.** Phase 4B built this on
    ``participants=(...)`` with the two ends in slots ``A0``/``A1`` and took the
    ``subject_mention_ref=``/``object_mention_ref=`` constructor parameters away, so the
    corpus cannot keep producing signals on a construction path the seven producers no
    longer use - which is the point of removing it. ``basis`` and ``polarity`` are
    **parameters with stated defaults rather than omitted**, because a corpus case that
    declared neither was exercising a signal the platform cannot construct honestly: a
    signal with no basis and a surface is legal, but it is a signal that has not said how
    it saw anything, and a corpus is exactly where that should not go unexamined.

    The default basis is :attr:`~domain.signal_basis.SignalBasis.EVENT_FRAME` because that
    is the honest answer for a hand-declared reading: the case asserted it, from a parse or
    a statement, rather than reporting an adjacency. ``EVENT_FRAME`` rather than
    ``PREDICATE_TEXT`` because these cases carry a surface that is an operator's name, not
    words the document used between two mentions.
    """
    return RelationSignal(
        participants=(
            RelationParticipant(
                mention_ref=subject,
                slot=ArgumentSlot(0),
                role_hypothesis="A0",
                ordinal=0,
                confidence=1.0,
            ),
            RelationParticipant(
                mention_ref=obj,
                slot=ArgumentSlot(1),
                role_hypothesis="A1",
                ordinal=1,
                confidence=1.0,
            ),
        ),
        kind=kind,
        relation_surface=surface,
        relation_ref=RelationRef(ref) if ref else None,
        basis=basis,
        polarity=polarity,
        neighbourhood=Neighbourhood(
            characters_scanned=0, pairs_considered=0, scope_read="the corpus case, by hand"
        ),
        direction=direction,
        producer_ref=producer,
        context_ref=SCOPE.context_ref,
        semantic_regime_ref=SCOPE.semantic_regime_ref,
        capture_ref=SCOPE.document_ref,
        tenant_id=SCOPE.tenant_id,
        extra=extra or {},
    )


def _producers() -> Mapping[str, Callable[[str, Any], tuple[RelationSignal, ...]]]:
    return {
        "links": lambda text, scope: link_signals([text], scope=scope),
        "tables": lambda text, scope: table_signals([text], scope=scope),
        "lists": lambda text, scope: list_signals([text], scope=scope),
        "metadata": lambda text, scope: metadata_signals([text], scope=scope),
    }


PRODUCERS = _producers()


# --- expectations, one per case ------------------------------------------------


def _expect_active_passive(report, signals) -> dict:
    """One relation, two realisations, one hypothesis, and the two of them **one** hypothesis.

    T035's finding pinned as a case: identity is keyed on the relation's own words, so the
    two *surfaces* below are two **readings** of one claim. The grammar-form claim holds where
    the surface is shared, and this case asserts both halves of that: shared surface collapses
    to one candidate, different surfaces are two candidates of one ``logical_candidate_id``.

    The second half was asserting two *logical* ids from two different surfaces, and that was
    already false before Phase 4B: ``logical_candidate_material`` does not key on
    ``relation_surface`` (``data-model.md`` part 7.1 - a vocabulary swap must not re-key a
    stored observation), so two surfaces over the same pair with no operator type are one
    hypothesis with two names. The old assertion was a stale expectation in a case no test
    ran, and it is corrected here rather than left in place, because a case that cannot run
    cannot document anything.
    """
    same_surface = assemble(
        [
            _declared("MN-A", "MN-B", "CEO of", producer="prose/active"),
            _declared("MN-A", "MN-B", "CEO of", producer="prose/passive"),
        ],
        **ASSEMBLE_KW,
    )
    assert len(same_surface.candidates) == 1, same_surface.candidates
    assert len(same_surface.candidates[0].signal_refs) == 2
    assert "prose/active" in same_surface.candidates[0].extraction_rule_id
    assert "prose/passive" in same_surface.candidates[0].extraction_rule_id

    different = assemble(
        [
            _declared("MN-A", "MN-B", "is the CEO of Acme", producer="prose/active"),
            _declared("MN-A", "MN-B", "The CEO of Acme is", producer="prose/passive"),
        ],
        **ASSEMBLE_KW,
    )
    # Two readings, because the surface is part of the reading key.
    assert len(different.candidates) == 2, "different surfaces are two readings of one claim"
    # ... and one hypothesis, because the surface is NOT part of the logical identity.
    assert len({c.logical_candidate_id for c in different.candidates}) == 1, (
        "two surfaces over one pair with no operator type are one hypothesis with two names; "
        "if this ever becomes 2, the identity layer has started keying on the observation's "
        "wording, and a vocabulary swap would re-key every stored candidate "
        "(data-model.md part 7.1)"
    )
    assert len(different.competing()) == 1, different.competing()
    return {
        "same_surface_logical": same_surface.candidates[0].logical_candidate_id,
        "same_surface_readings": len(same_surface.candidates[0].signal_refs),
        "different_surface_logicals": sorted(
            c.logical_candidate_id for c in different.candidates
        ),
        "different_surface_readings": len(different.candidates),
    }


def _expect_nary(report, signals) -> dict:
    """Three participants and a full set of role bindings, carried through untouched.

    The case has to state ``arity_mode`` **as well as** the bindings, and that coupling is
    the point rather than an inconvenience. A signal that named three roles without saying
    the relation was n-ary would assemble into a ``DIRECTED`` candidate carrying role
    assignments, and :class:`~domain.relation_candidate.RelationCandidate` refuses that shape
    - correctly, because a claim built on it could never be promoted. The refusal is the
    mechanism working: a caller cannot hand over role assignments and have the platform
    guess the arity they imply.

    **Phase 4C added the second half of this case, and it is why the case's digest moved.**
    The first signal below names the role slots of two of three ends and a second producer
    names all three. That is a *partial set over one configuration*, and before 4C
    :func:`~semantic_path.assembly._roles_of` answered it with ``()``: one candidate, no role
    assignments, ``CONSISTENT``, and a producer that had genuinely read two slots
    indistinguishable from one that had read none. ``ARBITRATION`` §3 names role slots as a
    ``CONFLICTING`` trigger, so the pair is now two readings, both preserved, both
    ``CONFLICTING``, and the axis is reported with both declared sets spelled out.

    **The mutation recorded with it is that the old behaviour was not a wrong candidate but a
    failed batch.** ``RelationCandidate`` refuses a ``NARY`` candidate with fewer than two role
    assignments, so swallowing the partial set handed it a ``nary`` reading with nothing in
    ``role_assignments`` and the whole assembly raised ``insufficient_role_assignments``. One
    producer naming two of three slots took every other signal on the pair down with it. This
    case now asserts the survivable half, and
    ``test_restoring_the_role_slot_unanimity_rule_fails_this_file`` asserts the other half by
    reproducing it.
    """
    roles = (
        ("actor", "MN-A", ""),
        ("target", "MN-B", ""),
        ("instrument", "MN-C", ""),
    )
    report_ = assemble(
        [
            _declared(
                "MN-A", "MN-B", "acquired", ref="acquired",
                extra={"role_bindings": roles, "arity_mode": "nary"},
            )
        ],
        **ASSEMBLE_KW,
    )
    candidate = report_.candidates[0]
    assert candidate.arity_mode.value == "nary", candidate.arity_mode
    assert len(candidate.role_assignments) == 3, candidate.role_assignments
    assert {r.role for r in candidate.role_assignments} == {"actor", "target", "instrument"}

    # And the refusal, because the pair above is only meaningful if the gap is closed.
    from domain.relation_candidate import CandidateContractError

    try:
        assemble(
            [_declared("MN-A", "MN-B", "acquired", ref="acquired", extra={"role_bindings": roles})],
            **ASSEMBLE_KW,
        )
    except CandidateContractError as exc:
        assert exc.code == "role_assignment_on_directed", exc.code
    else:
        raise AssertionError(
            "role assignments without a stated arity assembled into a directed candidate, "
            "which is a shape no claim can be built from"
        )

    # The partial set: one producer names two of three slots, the other names all three, and
    # both readings survive with the slots each of them actually declared.
    partial = assemble(
        [
            _declared(
                "MN-A", "MN-B", "acquired", ref="acquired", producer="schema/partial",
                extra={"role_bindings": roles[:2], "arity_mode": "nary"},
            ),
            _declared(
                "MN-A", "MN-B", "acquired", ref="acquired", producer="schema/complete",
                extra={"role_bindings": roles, "arity_mode": "nary"},
            ),
        ],
        **ASSEMBLE_KW,
    )
    assert len(partial.candidates) == 2, partial.candidates
    assert sorted(len(c.role_assignments) for c in partial.candidates) == [2, 3], partial.candidates
    assert all(
        c.assembly_state is CandidateAssemblyState.CONFLICTING for c in partial.candidates
    ), [c.assembly_state for c in partial.candidates]
    assert partial.groups_with_structural_conflict == ("MN-A->MN-B",)
    assert {axis for _p, axis, _u, _s in partial.structural_conflicts} == {"role_slots"}
    # One hypothesis, two readings: the verdict is revision material and does not fork identity.
    assert len({c.logical_candidate_id for c in partial.candidates}) == 1
    return {
        "arity": str(candidate.arity_mode),
        "roles": sorted(f"{r.role}={r.member_ref}" for r in candidate.role_assignments),
        "refused_without_arity": True,
        "partial_role_slots": sorted(
            str(c.assembly_state) for c in partial.candidates
        ),
        "partial_role_counts": sorted(len(c.role_assignments) for c in partial.candidates),
        "partial_axes": sorted({axis for _p, axis, _u, _s in partial.structural_conflicts}),
    }


def _expect_unknown_relation(report, signals) -> dict:
    """CD-6: a relation the vocabulary has no entry for is stored with its words."""
    untyped = assemble(
        [_declared("MN-A", "MN-B", "Role", ref=None, producer="table/header-row")],
        **ASSEMBLE_KW,
    )
    candidate = untyped.candidates[0]
    assert candidate.relation_ref is None
    assert candidate.relation_surface == "Role"
    assert candidate.predicate_hypothesis.resolution_state.value == "unknown"
    return {
        "surface": candidate.relation_surface,
        "state": str(candidate.predicate_hypothesis.resolution_state),
        "candidate_id": candidate.candidate_id,
    }


def _expect_link(report, signals) -> dict:
    """A hyperlink is a document structure: untyped, undirected, and fetched nothing."""
    assert signals, "the link producer found nothing in a document with a link"
    assert all(s.relation_ref is None for s in signals)
    assert all(s.direction is DirectionHypothesis.UNDIRECTED for s in signals)
    assert all("no target was fetched" in s.neighbourhood.scope_read for s in signals)
    return {
        "kinds": sorted(str(s.kind) for s in signals),
        "surfaces": sorted(s.relation_surface for s in signals),
        "untyped": all(s.relation_ref is None for s in signals),
    }


def _expect_table(report, signals) -> dict:
    """FR-028: the header is the surface and the platform types nothing."""
    assert signals
    assert {s.relation_surface for s in signals} >= {"Name", "Role"}
    assert all(s.relation_ref is None for s in signals)
    assert all(s.kind is SignalKind.TABLE for s in signals)
    return {
        "surfaces": sorted(s.relation_surface for s in signals),
        "cells": sorted(s.extra["cell_value"] for s in signals),
        "untyped": all(s.relation_ref is None for s in signals),
    }


def _expect_metadata(report, signals) -> dict:
    """A document states an author; the producer reports the field, not a reading."""
    surfaces = {s.relation_surface for s in signals}
    assert "author" in surfaces, surfaces
    author = next(s for s in signals if s.relation_surface == "author")
    # The field name is reported and no operator type is invented. What the producer
    # *cannot* tell - a person from a newsroom from a robot - lives in its declaration
    # rather than on the signal, so what the signal must get right is that it carries the
    # document's own text and no reading of it.
    assert author.relation_ref is None
    assert author.extra["meta_content"] == "jane@acme.example"
    byline = [s for s in signals if s.relation_surface == "by"]
    if byline:
        assert "CMS default" in byline[0].notes, byline[0].notes
    return {
        "surfaces": sorted(s.relation_surface for s in signals),
        "author_content": author.extra["meta_content"],
        "byline_kept_its_ambiguity": bool(byline),
    }


def _expect_text_vs_table(report, signals) -> dict:
    """The same relation read two ways is two candidates and no signal lost."""
    conflicting = assemble(
        [
            _declared("MN-A", "MN-B", "CEO of", ref="works_for", producer="lexical/1"),
            _declared(
                "MN-A", "MN-B", "founder of", ref="founded", producer="table/1",
                kind=SignalKind.TABLE,
            ),
        ],
        **ASSEMBLE_KW,
    )
    assert len(conflicting.candidates) == 2
    assert conflicting.attributed_signal_count == 2
    assert conflicting.complete
    assert len(conflicting.groups_with_conflict) == 1
    return {
        "candidates": sorted(c.candidate_id for c in conflicting.candidates),
        "surfaces": sorted(c.relation_surface for c in conflicting.candidates),
        "attributed": conflicting.attributed_signal_count,
        "groups_with_conflict": list(conflicting.groups_with_conflict),
    }


def _expect_triple_corroboration(report, signals) -> dict:
    """Three producers, one pair, one reading - and three sources for FR-034 to count."""
    corroborated = assemble(
        [
            _declared("MN-A", "MN-B", "CEO of", ref="works_for", producer="lexical/1"),
            _declared("MN-A", "MN-B", "CEO of", ref="works_for", producer="table/1",
                      kind=SignalKind.TABLE),
            _declared("MN-A", "MN-B", "CEO of", ref="works_for", producer="metadata/1",
                      kind=SignalKind.METADATA),
        ],
        **ASSEMBLE_KW,
    )
    assert len(corroborated.candidates) == 1
    candidate = corroborated.candidates[0]
    assert len(candidate.signal_refs) == 3, candidate.signal_refs
    assert candidate.extraction_rule_id.count("|") == 2, candidate.extraction_rule_id
    return {
        "candidates": len(corroborated.candidates),
        "signal_refs": len(candidate.signal_refs),
        "producers": sorted(candidate.extraction_rule_id.split("|")),
    }


def _expect_attribute(report, signals) -> dict:
    """A key/value field is neither prose nor markup, and is read as itself."""
    assert signals
    assert any(s.kind is SignalKind.ATTRIBUTE for s in signals)
    assert all(s.relation_ref is None for s in signals)
    return {
        "keys": sorted(s.extra["attribute_key"] for s in signals),
        "values": sorted(s.extra["attribute_value"] for s in signals),
    }


def _expect_hierarchy(report, signals) -> dict:
    """Containment by position is a relation, and reported as one."""
    assert any(s.kind is SignalKind.HIERARCHY for s in signals)
    assert all(s.relation_ref is None for s in signals)
    return {
        "surfaces": sorted(s.relation_surface for s in signals),
        "kinds": sorted(str(s.kind) for s in signals),
    }


# --- the corpus ----------------------------------------------------------------


CASES: tuple[SignalCase, ...] = (
    SignalCase(
        name="active_passive",
        input="",
        producers=(),
        expect=_expect_active_passive,
        rationale="one relation, two grammatical forms: one hypothesis, two readings",
        labels=("grammar", "identity"),
    ),
    SignalCase(
        name="nary_event",
        input="",
        producers=(),
        expect=_expect_nary,
        rationale="three participants and a full set of role bindings survive assembly",
        labels=("arity",),
    ),
    SignalCase(
        name="unknown_relation",
        input="",
        producers=(),
        expect=_expect_unknown_relation,
        rationale="CD-6: no operator type, and the words are kept",
        labels=("cd-6", "open-world"),
    ),
    SignalCase(
        name="link",
        input='<p>See <a href="https://acme.example/team">the team</a>.</p>',
        producers=(("links", PRODUCERS["links"]),),
        expect=_expect_link,
        rationale="a hyperlink is a document structure, not a world relation",
        labels=("structural",),
    ),
    SignalCase(
        name="table",
        input=(
            "<table><tr><th>Name</th><th>Role</th></tr>"
            "<tr><td>Jane Doe</td><td>CEO</td></tr></table>"
        ),
        producers=(("tables", PRODUCERS["tables"]),),
        expect=_expect_table,
        rationale="FR-028: the header reaches the substrate and nothing interprets it",
        labels=("structural", "fr-028"),
    ),
    SignalCase(
        name="metadata",
        input=(
            '<head><meta name="author" content="jane@acme.example"></head>'
            "<p>By: Jane Doe</p>"
        ),
        producers=(("metadata", PRODUCERS["metadata"]),),
        expect=_expect_metadata,
        rationale="a byline reports the field; the four readings are not chosen between",
        labels=("structural", "self-description"),
    ),
    SignalCase(
        name="text_vs_table",
        input="",
        producers=(),
        expect=_expect_text_vs_table,
        rationale="one relation read two ways is two candidates and no signal lost",
        labels=("conflict",),
    ),
    SignalCase(
        name="triple_corroboration",
        input="",
        producers=(),
        expect=_expect_triple_corroboration,
        rationale="three producers corroborate one reading; FR-034 has three sources",
        labels=("fr-034", "independence"),
    ),
    SignalCase(
        name="attribute_value",
        input='<p>Role: CTO</p>',
        producers=(("metadata", PRODUCERS["metadata"]),),
        expect=_expect_attribute,
        rationale="a key/value field is read as itself",
        labels=("structural",),
    ),
    SignalCase(
        name="document_hierarchy",
        input='<head><meta property="og:article:section" content="Markets"></head>',
        producers=(("metadata", PRODUCERS["metadata"]),),
        expect=_expect_hierarchy,
        rationale="containment by position is a relation",
        labels=("structural",),
    ),
)


def run_case(case: SignalCase) -> SignalCaseRun:
    """One case, run: its signals, its assembled report and its digest."""
    signals: list[RelationSignal] = []
    for _, produce in case.producers:
        signals.extend(produce(case.input, SCOPE))
    report = assemble(tuple(signals), **ASSEMBLE_KW) if signals else assemble([], **ASSEMBLE_KW)
    verified = case.expect(report, tuple(signals))
    detail = {
        "signal_ids": sorted(s.signal_id for s in signals),
        "kinds": sorted({str(s.kind) for s in signals}),
        "candidate_ids": [c.candidate_id for c in report.candidates],
        "logical_candidate_ids": [c.logical_candidate_id for c in report.candidates],
        "groups_with_conflict": list(report.groups_with_conflict),
        "complete": report.complete,
        # What the case's own assertions ran over, so a case that exercises the assembler
        # directly still has a digest that changes when the thing it checks changes.
        "verified": {str(k): v for k, v in dict(verified).items()},
    }
    return SignalCaseRun(
        name=case.name,
        signals=tuple(signals),
        report=report,
        digest=digest128(canonical_material(detail)),
        rationale=case.rationale,
        labels=case.labels,
        detail=detail,
    )


def run_corpus(cases: tuple[SignalCase, ...] = CASES) -> dict[str, SignalCaseRun]:
    return {case.name: run_case(case) for case in cases}


def corpus_digest(runs: Mapping[str, SignalCaseRun]) -> str:
    """One digest over the whole corpus, for the recorded baseline (T040)."""
    return digest128(
        canonical_material({name: run.digest for name, run in sorted(runs.items())})
    )


def compare(left: Mapping[str, SignalCaseRun], right: Mapping[str, SignalCaseRun]) -> dict[str, Any]:
    """Field-by-field difference between two runs. Empty means SC-H holds at this layer."""
    differences: list[str] = []
    for name in sorted(set(left) | set(right)):
        a, b = left.get(name), right.get(name)
        if a is None or b is None:
            differences.append(f"{name}: present in one run only")
            continue
        for field_name in sorted(set(a.detail) | set(b.detail)):
            if a.detail.get(field_name) != b.detail.get(field_name):
                differences.append(f"{name}.{field_name}")
    return {"identical": not differences, "differences": differences}


def as_json(runs: Mapping[str, SignalCaseRun]) -> str:
    return json.dumps(
        {name: {"digest": run.digest, **run.detail} for name, run in sorted(runs.items())},
        indent=2,
        sort_keys=True,
    )


__all__ = [
    "ASSEMBLE_KW",
    "CASES",
    "SCOPE",
    "SignalCase",
    "SignalCaseRun",
    "as_json",
    "compare",
    "corpus_digest",
    "run_case",
    "run_corpus",
]
