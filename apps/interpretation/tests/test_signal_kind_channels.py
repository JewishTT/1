"""Phase 4C / C1: ``SignalKind`` carries observation channels and nothing else.

Feature 021, spec FR-011, FR-012, FR-013, FR-015, FR-152; brief §15, §16, §31, §39, §42;
``repair/ARBITRATION.md`` §4 and §5; ``repair/A7-migration-021.md`` D3.

**What this file is.** 4A added ``RelationSignal.polarity``, ``basis`` and ``participants``, and
4B migrated the seven producers onto them. What those two phases made *redundant* is this
phase's subject, and the redundancy is exactly three enum members:

=========================================  ====================================================
deleted member                             the field that already carried what it carried
=========================================  ====================================================
``NEGATION``   (a polarity)                :attr:`RelationSignal.polarity` = ``Polarity.DENIED``
``QUANTITY``   (an aspect)                 :attr:`RelationParticipant.argument_shape` = ``"value"``
``COREFERENCE`` (never a channel at all)   nothing — it is a *relation between two mentions*,
                                           and deciding that is coreference with a
                                           ``ResolutionDecisionRecord`` behind it
=========================================  ====================================================

**The measurement that made the deletion safe, and it is a measurement rather than an
assumption.** ``rg 'SignalKind.(NEGATION|QUANTITY|COREFERENCE)' apps`` reached docstrings and
three tests and **no construction site**: no producer declared, emitted or keyed on any of the
three. :func:`test_no_production_code_path_references_a_deleted_member` turns that into a
mechanical check over the AST, so the claim is re-runnable rather than a memory, and so the
first producer that reaches for a deleted member fails here rather than shipping a kind the
migration `021` whitelist is about to stop accepting.

**``TEMPORAL`` is kept, and this file says why it is the one member a cleanup phase may not
"fix".** ``ARBITRATION`` §4 is explicit and overrides the Phase-0 instruction to leave it out:
a channel and a container are different things, ``TEMPORAL`` states *provenance channel* and the
temporal facts live in :class:`domain.temporal_observation.SourceTemporalObservation`.
:func:`test_temporal_is_a_channel_and_carries_no_temporal_payload` is the mechanical form of
that: the member exists, the facts are not in it, and deleting it would have been the
deletion this phase exists to avoid.

**The additions, and what 4C does *not* settle.** ``STRUCTURAL`` (brief §31), ``EVENT``
(brief §39), ``SEMANTIC`` (brief §42) and ``TEMPORAL`` (brief §15) are all mandated by FR-011
and all four were absent. They are added here. What is **not** decided here is which of
``STRUCTURAL``/``HIERARCHY`` and ``SEMANTIC``/``SCHEMA`` a producer may file under:
``repair/A7-migration-021.md`` §5 disagreement 7 already recorded those pairs as near-synonyms
whose split is "**my** definition, not the brief's, and needs the brief owner", and this phase
does not have that authority. :func:`test_the_undecided_overlap_is_recorded_rather_than_guessed`
pins that the overlap is *declared* in the enum's own docstring, so it stays a named open
question instead of becoming two names for one observation.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis

from extractors.signals.links import link_signals
from extractors.signals.protocol import ExtractionScope
from extractors.signals.signal import (
    STRUCTURAL_SIGNAL_KINDS,
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
)
from extractors.signals.syntactic import syntactic_signals

pytestmark = pytest.mark.unit

#: ``apps/`` — the root the service packages hang off.
APPS = Path(__file__).resolve().parents[2]
INTERPRETATION = APPS / "interpretation"
#: Everything a mutated child run has to import. ``extractors`` needs ``domain`` and
#: ``parsers``; ``domain`` needs ``semantic``.
_COPIED = (
    ("interpretation", ("extractors", "parsers", "semantic", "contracts.py")),
    ("shared", ("domain",)),
)

_DELETED = ("NEGATION", "QUANTITY", "COREFERENCE")
_ADDED = ("STRUCTURAL", "EVENT", "SEMANTIC", "TEMPORAL")

_NB = Neighbourhood(characters_scanned=64, pairs_considered=0, scope_read="one clause")


def _scope() -> ExtractionScope:
    return ExtractionScope(
        tenant_id="tenant-a",
        context_ref="CTX-1",
        semantic_regime_ref="RG-1",
        document_ref="CAP-1",
    )


def _signal(**over) -> RelationSignal:
    base = {
        "kind": SignalKind.SYNTAX,
        "relation_surface": "sold to",
        "neighbourhood": _NB,
        "participants": (
            RelationParticipant(mention_ref="MN-A", slot=ArgumentSlot(0), ordinal=0),
            RelationParticipant(mention_ref="MN-B", slot=ArgumentSlot(1), ordinal=1),
        ),
        "basis": SignalBasis.EVENT_FRAME,
        "producer_ref": "syntactic/pinned",
        "context_ref": "CTX-1",
        "semantic_regime_ref": "RG-1",
        "tenant_id": "tenant-a",
    }
    return RelationSignal(**{**base, **over})


# --------------------------------------------------------------------------- #
# The three deletions, and the fact that nothing reached for them
# --------------------------------------------------------------------------- #


def test_the_three_aspect_members_are_gone_and_the_four_channels_are_present() -> None:
    """The deletion and the addition in one place, because they are one change.

    FR-011's ``MUST`` is that the enum "MUST contain at least" fourteen named channels and
    "MUST NOT contain a member naming an orthogonal aspect". Both halves are checked against
    the live enum rather than against a restatement of it, because a test that reads a constant
    this module also wrote would pass if the constant were wrong.
    """
    members = SignalKind.__members__
    for name in _DELETED:
        assert name not in members, f"{name} is still a channel"
    for name in _ADDED:
        assert name in members, f"{name} is mandated by FR-011 and absent"
    # The literals are refused, not silently coerced, so a stored 020-era row carrying one of
    # them is told the truth about why it will not load rather than arriving as a different kind.
    for literal in ("negation", "quantity", "coreference"):
        with pytest.raises(ValueError):
            SignalKind(literal)
    # And `CO_OCCURRENCE` stays: it becomes representable *surface-less* once `basis` exists,
    # which is the whole of what 4A bought for it, and deleting it would delete a capability
    # rather than a redundancy.
    assert "CO_OCCURRENCE" in members


def test_no_production_code_path_references_a_deleted_member() -> None:
    """The measurement behind the deletion, as a check rather than a claim.

    Read from the **AST** of every production module under ``extractors/``, ``parsers/`` and
    ``domain/``, and it looks for three shapes: a ``SignalKind.<deleted>`` attribute access, a
    string literal equal to a deleted member's value, and a bare ``<deleted>`` name. Docstrings
    are excluded, and deliberately: this file and the enum's own docstring name all three
    constantly, because a deletion whose reason is not written down gets relitigated within a
    month, and a source scan that counted prose would have to be given an exception list that
    would then become the only thing anyone reads.
    """
    roots = (INTERPRETATION / "extractors", INTERPRETATION / "parsers", APPS / "shared" / "domain")
    deleted_values = {"NEGATION": "negation", "QUANTITY": "quantity", "COREFERENCE": "coreference"}
    offenders: list[str] = []
    for root in roots:
        for module in sorted(root.rglob("*.py")):
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "SignalKind"
                    and node.attr in _DELETED
                ):
                    offenders.append(f"{module.name}:{node.lineno} SignalKind.{node.attr}")
                elif isinstance(node, ast.Name) and node.id in _DELETED:
                    offenders.append(f"{module.name}:{node.lineno} {node.id}")
                elif isinstance(node, ast.Constant) and node.value in deleted_values.values():
                    offenders.append(
                        f"{module.name}:{node.lineno} literal {node.value!r}"
                    )
    assert not offenders, (
        "production code still reaches for a deleted SignalKind member, so the deletion is not "
        "yet redundant:\n  " + "\n  ".join(sorted(offenders))
    )


def test_a_negated_clause_reaches_polarity_denied_through_the_field_alone() -> None:
    """``NEGATION``'s landing place, end to end through the producer that reads negators.

    This is the assertion that makes the deletion safe rather than lossy. Before 4A the only way
    to record "John is not the CEO of Acme" was a kind, and with no kind the sentence is either
    dropped — losing an observed fact — or recorded as an acquisition, which is a lie with a
    schema. The field exists (4A), the syntactic producer threads the parser's own polarity into
    it (4B), and 4C removed the second way of saying it. All three halves, on a real sentence.
    """
    extraction = syntactic_signals(["John is not the CEO of Acme."], scope=_scope())
    assert extraction.refusals == ()
    assert len(extraction.signals) == 1
    denied = extraction.signals[0]
    assert denied.polarity is Polarity.DENIED
    assert denied.is_denied
    assert denied.kind is SignalKind.SYNTAX
    positive = syntactic_signals(["John is the CEO of Acme."], scope=_scope()).signals[0]
    assert positive.polarity is Polarity.ASSERTED
    # Opposite claims, so two addresses: an address that could not tell them apart would make a
    # denial and an assertion the same row.
    assert denied.signal_id != positive.signal_id
    assert {s.polarity for s in extraction.signals} == {Polarity.DENIED}


def test_a_quantity_reaches_argument_shape_value_and_does_not_re_key() -> None:
    """``QUANTITY``'s landing place, and the one property that makes it a safe home.

    FR-012's mapping is ``QUANTITY → RelationParticipant.argument_shape = "value"``, so with
    the kind gone that attribute is the whole of the mapping. The link producer is the real
    producer that reaches it: a hyperlink's target is a pointer rather than an occurrence of a
    thing in this document, so it says so.

    The second half is the reason :attr:`RelationParticipant.to_identity` omits
    ``argument_shape``, and it is the half that makes the deletion a cleanup rather than a
    regression: a type-layer reclassification of one end must not fork a relational identity.
    """
    found = link_signals(
        ['<p>See <a href="https://acme.example/team">the team</a>.</p>'], scope=_scope()
    )
    assert found, "the link producer found nothing in a document with a link"
    target = found[0].participants[1]
    assert target.argument_shape == "value", target.argument_shape
    # Recorded, not merely derivable: the record a reader opens has to carry it, or a round trip
    # would silently drop a producer's reading of each end's shape.
    assert found[0].to_dict()["participants"][1]["argument_shape"] == "value"
    assert RelationSignal.from_dict(found[0].to_dict()) == found[0]
    # And it is excluded from the address, so reclassifying the end is not a new observation.
    assert "argument_shape" not in target.to_identity()
    reclassified = RelationParticipant(
        mention_ref=target.mention_ref,
        slot=target.slot,
        ordinal=target.ordinal,
        argument_shape="entity",
    )
    assert reclassified.to_identity() == target.to_identity()
    assert reclassified != target, "the record must still say the shape changed"


def test_a_co_occurrence_with_no_predicate_words_is_still_constructible() -> None:
    """``CO_OCCURRENCE`` kept, and the form 4A made representable.

    A surface-less proximity observation is the one thing the old
    ``relation_surface <> '' OR relation_ref IS NOT NULL`` invariant forbade, and dropping the
    kind instead would have dropped the capability with it. The narrowing that replaced the
    invariant is what this asserts: a basis says how it was seen, and only
    :attr:`SignalBasis.PREDICATE_TEXT` still obliges words.
    """
    adjacent = _signal(
        kind=SignalKind.CO_OCCURRENCE,
        relation_surface="",
        basis=SignalBasis.PROXIMITY,
    )
    assert adjacent.relation_surface == ""
    assert adjacent.basis is SignalBasis.PROXIMITY
    assert adjacent.arity == 2
    # And the one basis that obliges words is still refused without them, so the narrowing did
    # not become a hole.
    with pytest.raises(SignalContractError) as caught:
        _signal(kind=SignalKind.CO_OCCURRENCE, relation_surface="", basis=SignalBasis.PREDICATE_TEXT)
    assert caught.value.code == "signal_predicate_text_basis_requires_words"


# --------------------------------------------------------------------------- #
# TEMPORAL: kept, and a channel rather than a container
# --------------------------------------------------------------------------- #


def test_temporal_is_a_channel_and_carries_no_temporal_payload() -> None:
    """``ARBITRATION`` §4, mechanically.

    §4's whole claim is a division: ``SignalKind.TEMPORAL`` means "this signal is based on a
    temporal observation" — the *channel* — and the temporal facts live in
    :class:`domain.temporal_observation.SourceTemporalObservation` and in the signal's
    :attr:`RelationSignal.stated_axes`. A member that carried a time of its own would make the
    enum the place temporal payloads are duplicated, which is the "unstructured dumping ground"
    §15 forbids and the reason §4 overrides the Phase-0 instruction to leave the member out.
    """
    assert "TEMPORAL" in SignalKind.__members__
    assert SignalKind("temporal") is SignalKind.TEMPORAL
    # The channel is declared by the kind and nothing else: no payload field exists on the
    # signal for a time, and the two carriers the facts *do* have are the ones §4 names.
    assert "stated_axes" in {f for f in RelationSignal.__dataclass_fields__}
    assert not any(
        "temporal" in name and name != "stated_axes"
        for name in RelationSignal.__dataclass_fields__
    )
    # A temporal signal is a *channel* and carries no obligation to be a container: it is legal
    # with no surface and no predicate words, exactly like any other non-word basis.
    windowed = _signal(kind=SignalKind.TEMPORAL, relation_surface="", basis=SignalBasis.PROXIMITY)
    assert windowed.kind is SignalKind.TEMPORAL
    assert windowed.is_structural is False, (
        "a temporal channel is not a document structure; it is the provenance of a reading, "
        "and putting it in STRUCTURAL_SIGNAL_KINDS would make that view answer a different "
        "question from the one it declares"
    )


def test_the_new_members_are_in_the_structural_view_only_where_they_are_structure() -> None:
    """``STRUCTURAL_SIGNAL_KINDS`` is a view with a stated subject, so its membership is a claim.

    The view answers "was the document's own structure the observation", and
    :attr:`SignalKind.SYNTAX` was already in it — a parsed frame counts. So
    :attr:`SignalKind.STRUCTURAL` (brief §31, DOM and section structure) and
    :attr:`SignalKind.EVENT` (brief §39, a parsed n-ary frame) join on the same footing, and
    :attr:`SignalKind.SEMANTIC` (a reading taken *over* a schema) and
    :attr:`SignalKind.TEMPORAL` (a temporal channel) do not. Asserted member by member so a
    later addition cannot join by default.
    """
    assert {SignalKind.STRUCTURAL, SignalKind.EVENT} <= STRUCTURAL_SIGNAL_KINDS
    assert {SignalKind.SEMANTIC, SignalKind.TEMPORAL}.isdisjoint(STRUCTURAL_SIGNAL_KINDS)
    # The view is a `frozenset` of *members* and not of tokens, so a later addition cannot join
    # it by a spelling match.
    assert all(isinstance(kind, SignalKind) for kind in STRUCTURAL_SIGNAL_KINDS)


def test_the_undecided_overlap_is_recorded_rather_than_guessed() -> None:
    """The named open question, asserted to still be named.

    ``STRUCTURAL``/``HIERARCHY`` and ``SEMANTIC``/``SCHEMA`` are near-synonyms at this
    revision. FR-011's ``MUST`` is satisfied by the members being present; **which** of each
    pair a producer may file under is a different question, and one this phase does not have the
    authority to answer — A7 already recorded it as needing the brief owner. The honest form is
    to say so where a reader of the enum will see it, which is what this asserts.
    """
    doc = SignalKind.__doc__ or ""
    for pair in ("STRUCTURAL", "HIERARCHY", "SEMANTIC", "SCHEMA"):
        assert f":attr:`{pair}`" in doc, pair
    assert "records rather than resolves" in doc, (
        "the enum docstring no longer says the overlap is unresolved, so a later reader will "
        "assume it was settled and file a producer under whichever name sorts first"
    )


# --------------------------------------------------------------------------- #
# Mutation tests: re-add each deleted member and a test must fail
# --------------------------------------------------------------------------- #

#: The guard, as a script. Three checks per deleted member, and the third is the behavioural one
#: rather than a membership test: it is there so a member that came back *with* its old
#: behaviour is caught by the same guard as one that came back bare.
_ENUM_GUARD_SCRIPT = """
from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis
from extractors.signals.signal import (
    Neighbourhood, RelationSignal, SignalKind, SignalContractError,
)

DELAYED = ("NEGATION", "QUANTITY", "COREFERENCE")
failures = []

for name in DELAYED:
    if name in SignalKind.__members__:
        failures.append(f"{name} is back in the enum")
for literal in ("negation", "quantity", "coreference"):
    try:
        SignalKind(literal)
    except ValueError:
        pass
    else:
        failures.append(f"{literal!r} resolves again")

nb = Neighbourhood(characters_scanned=64, pairs_considered=0, scope_read="one clause")


def signal(**over):
    base = dict(
        kind=SignalKind.SYNTAX, relation_surface="did not acquire", neighbourhood=nb,
        participants=(
            RelationParticipant(mention_ref="MN-A", slot=ArgumentSlot(0), ordinal=0),
            RelationParticipant(mention_ref="MN-B", slot=ArgumentSlot(1), ordinal=1),
        ),
        basis=SignalBasis.EVENT_FRAME, producer_ref="p/1", context_ref="C1",
        semantic_regime_ref="R1", tenant_id="t",
    )
    return RelationSignal(**{**base, **over})


# The behavioural half: the polarity field is the only authority, so an explicit `asserted`
# stays `asserted` and gains no note. A member that came back with the phase-4A bridge would
# overrule this.
explicit = signal(polarity=Polarity.ASSERTED)
if explicit.polarity is not Polarity.ASSERTED:
    failures.append("an explicit asserted polarity was overruled")
if "kind=negation" in explicit.notes:
    failures.append(f"the phase-4A overrule note is back: {explicit.notes!r}")

# The sharper half, and the one that separates a member restored *bare* from one restored with
# the behaviour it used to have. A bare member is caught by the membership checks above; a
# member that also overrules the field is caught here, and it is the state the code was in for
# one whole phase.
if "NEGATION" in SignalKind.__members__:
    overruled = signal(kind=SignalKind("negation"), polarity=Polarity.ASSERTED)
    if overruled.polarity is Polarity.DENIED:
        failures.append("a kind overrule replaced the polarity field's authority")
    if "kind=negation" in overruled.notes:
        failures.append(f"the overrule note reached the record: {overruled.notes!r}")

denied = signal(polarity=Polarity.DENIED)
if not denied.is_denied:
    failures.append("a denial is no longer recordable")
if denied.signal_id == explicit.signal_id:
    failures.append("a denial and an assertion share an address")

print("GUARD_OK" if not failures else "GUARD_FAIL " + "; ".join(failures))
raise SystemExit(0 if not failures else 1)
"""


def _mutated_signal_module(find: str, replace_with: str) -> Path:
    """A throwaway copy of the four packages with one edit applied to ``signal.py``.

    Flat, because one ``PYTHONPATH`` entry is the only thing a child interpreter needs, and the
    repository is never written to. Same discipline as the other mutation harnesses here, for
    the same reason: a mutation applied in place is a change nobody can review afterwards.
    """
    root = Path(tempfile.mkdtemp(prefix="signal-kind-mutation-"))
    for package, members in _COPIED:
        for member in members:
            source = APPS / package / member
            if source.is_dir():
                shutil.copytree(
                    source, root / source.name, ignore=shutil.ignore_patterns("__pycache__")
                )
            elif source.exists():
                shutil.copy2(source, root / source.name)
    target = (root / "extractors" / "signals" / "signal.py").resolve()
    text = target.read_text(encoding="utf-8")
    assert find in text, f"mutation anchor not found in signal.py: {find[:70]!r}"
    target.write_text(text.replace(find, replace_with, 1), encoding="utf-8")
    return root


def _child_env(root: Path) -> dict[str, str]:
    """The current environment with only ``PYTHONPATH`` redirected.

    Inherited rather than hand-built, because on Windows a hand-built ``PATH`` without
    ``System32`` is not a smaller environment, it is a broken one, and every child fails with a
    Winsock error that reads as a test failure.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    return env


def test_the_unmutated_enum_satisfies_the_guard() -> None:
    """The other half of every mutation below, and the half that is easy to skip.

    If the guard already failed on the unmutated source, "the mutation broke it" would prove
    nothing. Same script, same interpreter, repository source.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _ENUM_GUARD_SCRIPT],
        capture_output=True,
        text=True,
        cwd=str(INTERPRETATION),
        env=_child_env(INTERPRETATION),
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr[-2000:]
    assert "GUARD_OK" in completed.stdout, completed.stdout


@pytest.mark.parametrize("member,literal", list(zip(_DELETED, ("negation", "quantity", "coreference"))))
def test_readding_each_deleted_member_fails_the_guard(member: str, literal: str) -> None:
    """The mutation, once per deletion.

    Phase 4C's claim is that three members are redundant with fields that already exist. A
    deletion nobody has observed to be load-bearing is indistinguishable from a deletion nobody
    needed, so each member is put back into a copy of the enum and the guard is run against it:
    the member is present again, its literal resolves again, and the guard exits non-zero saying
    so. The guard is the behaviour above, not a restatement of the enum — the third check, that
    an explicit ``polarity=asserted`` is neither overruled nor annotated, is the one that fails
    if a member returns *with* the phase-4A bridge rather than bare.
    """
    root = _mutated_signal_module(
        '    CO_OCCURRENCE = "co_occurrence"\n',
        f'    CO_OCCURRENCE = "co_occurrence"\n    {member} = "{literal}"\n',
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _ENUM_GUARD_SCRIPT],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            check=False,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode != 0, (
        f"re-adding {member} did NOT fail the guard, so this file is not guarding the "
        f"deletion: {completed.stdout!r}"
    )
    assert f"{member} is back in the enum" in completed.stdout, completed.stdout
    assert f"{literal!r} resolves again" in completed.stdout, completed.stdout


def test_readding_negation_with_its_phase_4a_bridge_fails_the_guard() -> None:
    """The same deletion, restored *whole* — member **and** the overrule it used to perform.

    Re-adding a bare member is the easy case and the guard's membership checks catch it. The
    arrangement 4A actually had to live with was worse than the member: the member overrule an
    explicit ``polarity``, so a producer that denied in one field and asserted in another was
    recorded as whichever the kind said, and the disagreement was buried in ``notes``. Restoring
    both halves shows the behavioural half of the guard is live rather than decorative.
    """
    root = _mutated_signal_module(
        "        object.__setattr__(self, \"polarity\", polarity)\n",
        "        if self.kind is SignalKind.NEGATION and polarity is not Polarity.DENIED:\n"
        "            object.__setattr__(\n"
        "                self,\n"
        "                \"notes\",\n"
        "                f\"{self.notes} kind=negation with polarity={polarity.value}\".strip(),\n"
        "            )\n"
        "            polarity = Polarity.DENIED\n"
        "        object.__setattr__(self, \"polarity\", polarity)\n",
    )
    try:
        # The member has to come back too, or the bridge is unreachable and the test would pass
        # for the wrong reason.
        target = (root / "extractors" / "signals" / "signal.py").resolve()
        text = target.read_text(encoding="utf-8")
        anchor = '    CO_OCCURRENCE = "co_occurrence"\n'
        assert anchor in text
        target.write_text(
            text.replace(anchor, anchor + '    NEGATION = "negation"\n', 1), encoding="utf-8"
        )
        completed = subprocess.run(
            [sys.executable, "-c", _ENUM_GUARD_SCRIPT],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            check=False,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode != 0, completed.stdout
    assert "replaced the polarity field" in completed.stdout, (
        f"the overrule bridge is back but the guard did not notice it: {completed.stdout!r}"
    )
    assert "overrule note reached the record" in completed.stdout, (
        f"the overrule is silent rather than recorded, which is a different defect: "
        f"{completed.stdout!r}"
    )
