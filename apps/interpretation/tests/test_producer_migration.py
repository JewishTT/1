"""Phase 4B: the seven producers on the native contract, and the five tripwires that hold them.

Feature 021, FR-008, FR-014, FR-015, FR-020, FR-041…FR-043, FR-093, FR-094, FR-095.

**What this file is.** Phase 4A added the fields and Phase 4B migrated the callers. The
interesting question is not "does each producer now pass ``participants=``" - a source scan
answers that, and the scan is the first test here - but whether the migration *changed what
the producers say*, because a producer that was moved onto the new contract with the same
fabrications it had before has been rewritten and not fixed.

So the file is five tripwires and the per-producer cases that feed them:

1. :func:`test_no_producer_module_synthesises_a_participant_reference` - a **source scan**.
   Zero synthetic prefixes across the producer package, so a new one fails at the module, not
   at a downstream assertion nobody traced back.
2. One named positive case and every refusal path, per producer.
3. :func:`test_assert_bounded_trips_on_a_real_violation` - a real ceiling with a real
   violation behind it, because a bound nobody can trip is a comment.
4. :func:`test_a_dangling_term_is_reported_and_not_dropped` - FR-095, and the pairing ``zip``
   that used to discard it.
5. :func:`test_one_hyperlink_is_one_signal_and_one_independence_unit` - FR-034, and the
   double-count the link producer used to create.

**On the sweep and the one prefix it does not ban.** ``surface:`` is in the
:data:`SYNTHETIC_PARTICIPANT_PREFIXES` list Phase 4B was given, and it is *not* banned here.
The reason is a pinned test in the other direction:
``test_the_mention_reference_is_a_deferred_slot_address_and_not_a_minted_mention_id``
(``test_syntactic_producer.py``) asserts that the syntactic producer's references **are**
``surface:``-prefixed and asserts they are **not** ``MN-``-prefixed, citing brief §25 — "no
producer may invent a mention identity from text" - and FR-019, which reserves ``MN-`` to the
mention layer. :class:`~domain.relation_participant.RelationParticipant.mention_ref` says the
same thing on the type: "a deferred reference into the mention index, **never** a minted
mention id (FR-016, FR-019, constitution Invariant 2)".

So a producer below the mention layer addresses a *deferred occurrence*, and ``surface:`` is
the platform's own form for one — the form the syntactic producer's parser, :mod:`parsers.shallow`,
mints, and the one :class:`~semantic.blocking.RelationRole` and the HTML element names are read
out of. The eleven other prefixes in the list are all fabrications of a different kind, and they
are all banned with no exception: a URL, a column *label*, a *field name*, a *property name*, a
*document placeholder*, and a truncated string - each one putting something that is not a
thing the document contains where a participant goes (FR-094).

What the sweep does about ``surface:`` is not to ignore it. It pins the **count**: exactly one
module may hold the literal, and that module must be :mod:`extractors.signals.mentions`, the one
place a deferred reference is minted. A second minter fails the test, which is the property that
matters - one minting rule, or a return to five namespaces.

**The count used to be two, and the second one cost a collision.** :mod:`parsers.shallow` was
exempted because it built ``f"surface:{label}:{surface}"`` itself, and its labels are dependency
arcs — ``nmod:of``, ``nmod:in``, ``nmod:by``, ``nsubj:pass`` — several of which contain the ``:``
the grammar split on, so ``surface:nmod:of:acme`` was minted and read back as the label ``nmod``
and the surface ``of:acme``. Two distinct addresses, one string. The encoding is now injective by
construction (the fields are the platform's ``canonical_material``), and the parser mints through
:func:`domain.mention_occurrence_index.mint_occurrence_address` with it, so the exemption is gone
rather than narrowed. The tripwire that used to *record* that defect is now
``test_the_parser_addresses_its_arguments_through_the_one_minter`` in
``test_mention_binding_seam.py``.
"""


from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest
from domain.predicate_signature import ArgumentSlot, Polarity
from domain.signal_basis import SignalBasis

from extractors.signals import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
    assert_bounded,
)
from extractors.signals.lexical import (
    DOCUMENT_TOO_LONG_CODE,
    LexicalCueExtractor,
    lexical_signals,
)
from extractors.signals.lexical import (
    MAX_PAIRS_CONSIDERED as LEXICAL_CEILING,
)
from extractors.signals.links import (
    ANCHOR_LABEL,
    TARGET_LABEL,
    HyperlinkExtractor,
    is_informative,
    link_signals,
)
from extractors.signals.mentions import (
    DEFERRED_CAPTURE_PREFIX,
    DEFERRED_OCCURRENCE_PREFIX,
    deferred_capture,
    deferred_occurrence,
    read_occurrence,
)
from extractors.signals.metadata import (
    NO_CAPTURE_REF_CODE,
    VALUE_LABEL,
    MetadataExtractor,
    meta_entries,
    metadata_signals,
)
from extractors.signals.protocol import ExtractionScope, ProducerDeclaration
from extractors.signals.signal import PRECISION_EXHAUSTIVE
from extractors.signals.tables import (
    CELL_LABEL,
    HEADER_LABEL,
    PRECISION_HEURISTIC,
    ListExtractor,
    TableExtractor,
    list_signals,
    table_signals,
)

pytestmark = pytest.mark.unit

_TENANT = "tenant-a"
_PACKAGE = Path(__file__).resolve().parents[1] / "extractors" / "signals"

#: The single producer-side module permitted to hold a deferred-address prefix literal. Named
#: rather than globbed, because "every module except this one" is the property and a glob would
#: let the exemption grow when somebody adds a second file.
#:
#: **This list used to have a second entry.** :mod:`parsers.shallow` was exempted, because the
#: syntactic producer's parser built ``f"surface:{label}:{surface}"`` itself rather than calling
#: the helper — and its labels are dependency arcs that contain the ``:`` the grammar split on, so
#: ``surface:nmod:of:acme`` was an address of ``of:acme``. The exemption is gone because the
#: parser now imports :func:`domain.mention_occurrence_index.mint_occurrence_address` and the
#: literal with it. A second minter is not a tidiness problem here: it is the defect class.
_DEFERRED_MINTER = "mentions.py"

#: The parser the syntactic producer drives. Asserted to hold **no** prefix literal and to reach
#: the grammar by import — the direction the second entry above used to permit.
_PARSER = "shallow.py"



def _scope(**over: str) -> ExtractionScope:
    base = {
        "tenant_id": _TENANT,
        "context_ref": "ctx-1",
        "semantic_regime_ref": "regime-1",
        "document_ref": "CAP-1",
    }
    return ExtractionScope(**{**base, **over})


# --------------------------------------------------------------------------- #
# 1. The sweep: a source scan, so a new fabrication fails at its own module
# --------------------------------------------------------------------------- #

#: Every prefix Phase 4B removed, with the one thing each was standing in for. The
#: ``surface:`` prefix is in this list and is **not** banned; see the module docstring for why
#: a pinned test requires it and what replaces the ban.
SYNTHETIC_PARTICIPANT_PREFIXES: dict[str, str] = {
    "anchor:": "a URL's anchor text handed over as a mention of a thing in the world",
    "href:": "a URL handed over as a mention of a thing in the world",
    "header:": "a column LABEL posing as the column's referent",
    "cell:": "a cell value lowercased into a synthetic namespace",
    "document:": "a document placeholder posing as a retrieval",
    "meta:": "a meta tag's own KEY posing as a thing in the world",
    "byline:": "a truncated byline posing as a mention",
    "attribute:": "a FIELD NAME posing as a thing in the world",
    "value:": "a truncated VALUE posing as a mention",
    "jsonld:": "a schema.org PROPERTY NAME posing as a thing in the world",
    "jsonld-value:": "a truncated JSON-LD value posing as a mention",
    "surface:role:": "a label this producer chose about the world rather than one it read",
}

#: The banned subset, and the test scans the whole producer package plus the parser package
#: for it. ``surface:`` is excluded because it is the platform's blessed deferred-occurrence
#: form; the second entry is excluded because a *test* elsewhere in the repository requires
#: producers to emit exactly the opposite - see the module docstring.
_BANNED_PREFIXES: tuple[str, ...] = tuple(SYNTHETIC_PARTICIPANT_PREFIXES)


def _producer_modules() -> list[Path]:
    """Every module in the producer package, plus the parser the syntactic one drives.

    Both directories, and not just the ones that construct a signal today: a producer that
    delegates its references to a helper is the normal shape, and a helper that mints them is
    exactly where a fabrication would be reintroduced.
    """
    modules = sorted(_PACKAGE.glob("*.py"))
    modules.extend(sorted((_PACKAGE.parents[1] / "parsers").glob("*.py")))
    return [module for module in modules if module.is_file()]


def _docstrings(tree: ast.Module) -> set[str]:
    """Every module, class and function docstring in ``tree``, by value.

    Collected so the scan can exempt exactly them. The exemption is deliberate and narrow: a
    docstring is prose and is *supposed* to name what was removed - the twelve prefixes in
    :data:`SYNTHETIC_PARTICIPANT_PREFIXES` are the whole subject of the docstrings this
    migration rewrote - while a string literal that is **built** is a value the module
    constructs, and one of them containing ``href:`` is a fabrication. Scanning raw text would
    have to be told which lines to skip, and a scanner with a skip list is a scanner that
    eventually learns to skip too much.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            text = ast.get_docstring(node, clean=False)
            if text is not None:
                found.add(text)
    return found


def test_no_producer_module_synthesises_a_participant_reference() -> None:
    """**The sweep.** Zero fabrications across the producer package, as a source scan.

    A source scan rather than a runtime assertion, and the reason is that a runtime assertion
    can only see the references one particular input produced. A producer that fabricates
    ``href:`` only on an anchor with an uninformative text would pass every behavioural test
    in this file and ship a URL posing as a mention. Reading the source closes that: a
    ``f"href:{...}"`` is a fabrication whether or not this suite happened to run it.

    The prefixes are looked for in every **string literal** the module contains - including
    the fragments of an f-string, so ``f"href:{href}"`` is caught as the ``"href:"`` it is
    built from - and docstrings are exempted, per :func:`_docstrings`.
    """
    offenders: list[str] = []
    for module in _producer_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        docstrings = _docstrings(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            text = node.value
            if text in docstrings:
                continue
            for prefix in _BANNED_PREFIXES:
                if prefix in text:
                    offenders.append(
                        f"{module.name}:{node.lineno} builds {text!r} containing {prefix!r}"
                        f" — {SYNTHETIC_PARTICIPANT_PREFIXES[prefix]}"
                    )
    assert not offenders, (
        "a producer module synthesises a participant reference (FR-094):\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_the_deferred_prefix_has_exactly_one_minter() -> None:
    """The half of the sweep that concerns ``surface:``, which cannot be banned outright.

    One module may hold the literal, and the exemption is written out rather than globbed:
    :mod:`extractors.signals.mentions`, the rule - one function, one namespace. Every other
    producer module must reach a deferred reference by *calling* the helper, and so must
    :mod:`parsers.shallow`, which **used to be the second exemption** because it built
    ``f"surface:{label}:{surface}"`` itself. That is the case the whole encoding change is about:
    the parser's labels are dependency arcs, several contain the ``:`` the grammar split on, and
    ``surface:nmod:of:acme`` therefore addressed ``of:acme``. So the assertion now covers the
    parser too, and the parser reaches the grammar by importing the one minter.

    The second assertion is the one with teeth: it walks each producer module's AST and fails on
    a call to the helper's private name, which is what would reintroduce a second way to build
    the same string inside a producer.
    """
    exempt = {_DEFERRED_MINTER}
    offenders: list[str] = []
    for module in _producer_modules():
        if module.name in exempt:
            continue
        # Read from the AST with the docstrings exempted, per :func:`_docstrings` and for the same
        # reason as :func:`test_no_producer_module_synthesises_a_participant_reference`: prose is
        # *supposed* to name the form it replaced — several of these modules spend paragraphs on
        # it — while a literal a module **builds** is a second namespace. A raw-text scan cannot
        # tell those apart, and a scanner with a skip list is a scanner that learns to skip too
        # much. The f-string fragments come along as constants, so ``f"surface:{x}"`` is caught as
        # the ``"surface:"`` it is assembled from.
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        docstrings = _docstrings(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value not in docstrings
                and any(
                    f"{prefix}:" in node.value
                    for prefix in (DEFERRED_OCCURRENCE_PREFIX, DEFERRED_CAPTURE_PREFIX)
                )
            ):
                offenders.append(f"{module.name}:{node.lineno} builds {node.value!r}")
    assert not offenders, (
        f"{DEFERRED_OCCURRENCE_PREFIX}: / {DEFERRED_CAPTURE_PREFIX}: may only be built in "
        f"{sorted(exempt)}; a producer that builds one has reintroduced its own namespace:\n  "
        + "\n  ".join(sorted(offenders))
    )
    # And the producers that need one call the helper rather than building it.
    callers = {
        module.name
        for module in _producer_modules()
        if module.name not in exempt
        and "deferred_occurrence(" in module.read_text(encoding="utf-8")
    }
    assert callers == {"lexical.py", "links.py", "tables.py", "metadata.py"}, sorted(callers)
    # The parser is not a caller of the producer-side contract and is not a minter: it sits below
    # the extraction layer, so importing ``extractors.signals.mentions`` from it would take the
    # edge parser -> producer and invert the layering. It reaches the *domain* minter instead,
    # which is strictly below both, and the grammar has exactly one home either way.
    parser = next(module for module in _producer_modules() if module.name == _PARSER)
    tree = ast.parse(parser.read_text(encoding="utf-8"), filename=str(parser))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 0
    }
    assert "domain.mention_occurrence_index" in imported, sorted(imported)
    assert not any(name.startswith("extractors") for name in imported), (
        "the parser must not import the extraction layer: it sits below it"
    )
    assert "mint_occurrence_address" in parser.read_text(encoding="utf-8")
    assert "parse_deferred_address" not in parser.read_text(encoding="utf-8"), (
        "the parser reads no occurrence address; a second parse in the layer that mints them is "
        "how the retired collision went unnoticed"
    )



def test_a_refusal_always_precedes_a_synthetic_prefix() -> None:
    """A blank end is refused, never filled with a placeholder.

    The direct check on the *behaviour* the sweep cannot reach: there is no code path that
    turns "I could not determine this end" into a string. The old code had three of them -
    ``document:current``, an empty surface addressed anyway, and a 64-character cut - and
    each returned a plausible-looking reference rather than a refusal, which is why the
    sweep has to be a source scan and not only a test.
    """
    with pytest.raises(SignalContractError) as blank_surface:
        deferred_occurrence(label=VALUE_LABEL, surface="   ")
    assert blank_surface.value.code == "participant_surface_required"

    with pytest.raises(SignalContractError) as blank_label:
        deferred_occurrence(label="", surface="CTO")
    assert blank_label.value.code == "participant_label_required"

    with pytest.raises(SignalContractError) as blank_capture:
        deferred_capture(capture_ref="")
    assert blank_capture.value.code == "participant_capture_ref_required"
    assert "current" in str(blank_capture.value), (
        "the refusal has to name what it replaced, or a reader cannot tell whether the "
        "placeholder is gone or merely undocumented"
    )

    with pytest.raises(SignalContractError) as half_a_span:
        deferred_occurrence(label=VALUE_LABEL, surface="CTO", start=4)
    assert half_a_span.value.code == "participant_occurrence_span_invalid"


# --------------------------------------------------------------------------- #
# 2. Per producer: one named positive case, and every refusal path
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Case:
    """One producer's named positive case, and what must be true of the signal it emits."""

    name: str
    signals: tuple[RelationSignal, ...]
    surface: str
    basis: SignalBasis
    participants: tuple[str, str]


def _only(signals: tuple[RelationSignal, ...], name: str) -> RelationSignal:
    assert len(signals) == 1, f"{name} emitted {len(signals)} signals, expected one"
    return signals[0]


def test_read_occurrence_is_the_inverse_of_the_minter() -> None:
    """The address is a published interface, so the parse lives in one place and is tested.

    Round-tripped over the surfaces these producers actually produce, and the interesting cases
    are the ones containing a separator: an email address, a URL, an ``@``-handle, a colon, a
    pipe. Two arrangements have now been wrong. An earlier one put the span last, so
    ``surface:meta_value:jane@acme.example@35-52`` carried two ``@``s and could only be read by
    guessing which one was the separator. The next put the span first but still split the fields on
    ``:``, so a label containing one — and the syntactic producer's dependency arcs do — was read
    as a different label and a different surface. The fields are the platform's own
    ``canonical_material`` now, so the payload is self-delimiting and nothing in a surface can be
    mistaken for anything. The full adversarial table, including the empty string and a surface
    that is itself a JSON array, is in
    ``apps/shared/tests/unit/test_mention_occurrence_index.py``.
    """
    for label, surface, span in (
        (VALUE_LABEL, "CTO", (12, 15)),
        (VALUE_LABEL, "jane@acme.example", (35, 52)),
        (TARGET_LABEL, "https://acme.example/team?ref=a@b", (16, 48)),
        (TARGET_LABEL, "@handle", (0, 7)),
        (VALUE_LABEL, "a:b:c", (1, 6)),
        (VALUE_LABEL, "a|b", (0, 3)),
    ):
        reference = deferred_occurrence(
            label=label, surface=surface, start=span[0], end=span[1]
        )
        assert read_occurrence(reference) == (label, surface, span), reference
    # And the unpositioned form, which is the one :mod:`parsers.shallow` mints, round-trips with
    # no span and keeps the shape the syntactic tripwire pins. Asserted through the *published
    # parser* rather than against a hand-spelled string: a test that built the address itself
    # would be a second answer to "what does an address look like", and it would have gone on
    # passing through the encoding change that removed the collision.
    unpositioned = deferred_occurrence(label="nsubj", surface="company")
    assert read_occurrence(unpositioned) == ("nsubj", "company", None)
    assert unpositioned.startswith(f"{DEFERRED_OCCURRENCE_PREFIX}:")
    assert not unpositioned.startswith("surface:@")
    # A label that contains the separator the retired grammar split on, and a surface that does.
    # Under the retired grammar these two minted the same string.
    arc = deferred_occurrence(label="nmod:of", surface="acme")
    lookalike = deferred_occurrence(label="nmod", surface="of:acme")
    assert arc != lookalike, "the encoding is not injective, so two occurrences share one address"
    assert read_occurrence(arc) == ("nmod:of", "acme", None)
    assert read_occurrence(lookalike) == ("nmod", "of:acme", None)



def test_lexical_produces_a_native_two_participant_signal_over_the_cue() -> None:
    """``John Smith became CEO of Acme`` — one cue, two addressed occurrences, ``A0``/``A1``.

    The two ends are the cue pattern's own two named groups - the role phrase and the object
    - and both are addressed at their real positions in the input. The record must be
    checkable against the document rather than merely well formed, which is the whole
    difference between an occurrence's address and a string match.
    """
    text = "John Smith became CEO of Acme."
    signals = lexical_signals([text], scope=_scope())
    signal = _only(signals, "lexical")
    assert signal.relation_surface == "CEO of"
    assert signal.basis is SignalBasis.PREDICATE_TEXT
    assert signal.polarity is Polarity.ASSERTED
    assert [p.slot for p in signal.participants] == [ArgumentSlot(0), ArgumentSlot(1)]
    for participant in signal.participants:
        _label, surface, span = read_occurrence(participant.mention_ref)
        assert span is not None
        assert text[span[0] : span[1]] == surface
    # And no address carries the producer's own invented role word: the label comes from the
    # platform's `RelationRole`, not from the cue table's own group name. Read back through the
    # published parser — a test that split the address on ``:`` would be the second parse this
    # grammar exists to have one of, and it is the exact split that used to misread a label.
    assert [read_occurrence(p.mention_ref)[0] for p in signal.participants] == [
        "subject",
        "object",
    ]
    assert f"{DEFERRED_OCCURRENCE_PREFIX}:role:" not in signal.subject_mention_ref

    assert signal.subject_mention_ref == signal.participants[0].mention_ref
    assert "CEO" in signal.subject_mention_ref and "Acme" in signal.object_mention_ref


def test_lexical_refuses_a_document_longer_than_its_own_sweep_ceiling() -> None:
    """FR-093's ceiling is live, and it refuses rather than sweeping half a page.

    Before Phase 4B the constant existed in the declaration and the neighbourhood reported a
    hard-coded ``0``, so the ceiling was a number and a bound on nothing. Now the sweep
    refuses a record it cannot read whole, with a code, rather than reporting the cues it
    happened to find under a document-scoped ``capture_ref``.
    """
    oversized = "John became CEO of Acme. " * 600
    assert len(oversized) > LEXICAL_CEILING
    with pytest.raises(SignalContractError) as caught:
        lexical_signals([oversized], scope=_scope())
    assert caught.value.code == DOCUMENT_TOO_LONG_CODE
    assert str(LEXICAL_CEILING) in str(caught.value)
    # And the boundary itself is not a tripwire that fires on ordinary input: one character
    # under the ceiling is read.
    at_ceiling = "x" * (LEXICAL_CEILING - 1)
    assert lexical_signals([at_ceiling], scope=_scope()) == ()


def test_link_produces_one_signal_per_anchor_with_two_real_ends() -> None:
    """One hyperlink, one observation, and both ends at their own positions."""
    markup = '<p>See <a href="https://acme.example/team">the team</a>.</p>'
    signals = link_signals([markup], scope=_scope())
    signal = _only(signals, "link")
    for participant in signal.participants:
        _label, surface, span = read_occurrence(participant.mention_ref)
        assert span is not None
        assert markup[span[0] : span[1]] == surface
    assert signal.kind is SignalKind.LINK
    assert signal.basis is SignalBasis.HYPERLINK
    assert signal.relation_surface == "the team"
    assert signal.direction is DirectionHypothesis.UNDIRECTED
    assert signal.relation_ref is None
    assert signal.participants[0].role_hypothesis == ANCHOR_LABEL
    assert signal.participants[1].role_hypothesis == TARGET_LABEL
    # The target end is a deferred pointer and the record says so: no mention of the target
    # exists in this document, and a later layer that resolved it as though one did would be
    # resolving a URL.
    assert signal.extra["target_is_deferred_pointer"] is True
    assert "deferred pointer" in signal.notes
    assert "no target was fetched" in signal.neighbourhood.scope_read


def test_link_reports_a_real_pair_count_rather_than_an_invented_one() -> None:
    """FR-093: ``scanned // 16`` is gone, and the honest count is a stated ``0``.

    The old value was ``max(1, scanned // 16)``. Sixteen was a divisor with no unit, so no
    reader could say what it divided, and on a 200-character element it reported 12 pairs
    when the producer had compared none. This producer enumerates no mention pair at all -
    it walks one element's anchors in document order - so the count is 0 and the extent it
    really has is the anchor count in ``scope_read``.
    """
    markup = '<p><a href="/a">a</a> and <a href="/b">b</a></p>'
    signals = link_signals([markup], scope=_scope())
    assert signals
    for signal in signals:
        assert signal.neighbourhood.pairs_considered == 0
        assert signal.neighbourhood.characters_scanned == len(markup)
    assert HyperlinkExtractor().declares().max_pairs_considered >= 1


def test_link_refuses_the_three_anchors_that_name_nothing() -> None:
    """Three named refusals, and the shared property: no signal, not a fabricated one.

    An anchor with no ``href`` is a target, a button or a scripted control, not a link
    outward. An ``href`` of ``#section`` points inside the same document, so it is a
    containment fact about one artefact and reporting it would put a document in a relation
    with itself. An empty anchor has no surface, so there is nothing to address as the first
    end. All three yield **no signal** rather than a signal with a missing or invented end.
    """
    for markup, why in (
        ('<p><a name="anchor">target</a></p>', "no href: a target, not a link outward"),
        ('<p><a href="#section">jump</a></p>', "in-page: containment, not a connection"),
        ('<p><a href="https://acme.example/x"><b></b></a></p>', "no anchor text"),
        ("", "empty input"),
    ):
        assert link_signals([markup], scope=_scope()) == (), why
    # And the uninformative-text anchor is *not* a refusal - the document chose not to name
    # the target, and the record keeps the silence rather than recovering a name from the URL.
    quiet = link_signals(['<a href="https://acme.example/team">click here</a>'], scope=_scope())
    assert len(quiet) == 1
    assert quiet[0].relation_surface == "click here"
    assert quiet[0].extra["anchor_informative"] is False
    assert is_informative("click here") is False
    assert is_informative("the team") is True


def test_table_produces_one_signal_per_cell_addressed_by_its_own_text() -> None:
    """``| Name | Role |`` with ``| Jane | CEO |`` — two signals, two ends each, and no
    column label anywhere in the participant tuple."""
    markup = (
        "<table><tr><th>Name</th><th>Role</th></tr>"
        "<tr><td>Jane Doe</td><td>CEO</td></tr></table>"
    )
    signals = table_signals([markup], scope=_scope())
    assert len(signals) == 2
    assert {s.relation_surface for s in signals} == {"Name", "Role"}
    for signal in signals:
        assert signal.kind is SignalKind.TABLE
        assert signal.basis is SignalBasis.TABLE_SLOT
        assert signal.direction is DirectionHypothesis.AMBIGUOUS
        assert signal.relation_ref is None
        assert [p.slot for p in signal.participants] == [ArgumentSlot(0), ArgumentSlot(1)]
        assert [p.role_hypothesis for p in signal.participants] == [HEADER_LABEL, CELL_LABEL]
        # Both ends are the cells' own visible text at their own positions, and the header
        # end is a *cell in the document* rather than the column's name in a namespace. The
        # address resolving to itself is the whole claim: a ``header:``-prefixed reference
        # would not resolve to anything, because the string after it was never in the file.
        for participant in signal.participants:
            _label, surface, span = read_occurrence(participant.mention_ref)
            assert span is not None
            assert markup[span[0] : span[1]] == surface
        assert read_occurrence(signal.participants[0].mention_ref)[1] == signal.relation_surface
    assert signals[0].extra["column_header"] == "Name"
    assert signals[0].extra["cell_value"] == "Jane Doe"


def test_table_publishes_a_heuristic_as_a_heuristic() -> None:
    """The header row is a guess, and ``precision`` no longer opens with ``exact``.

    The old string was ``"exact; header row chosen by most <th> cells (a heuristic)"``. It
    opened with the word ``exact`` and put the admission in a parenthetical, so a reader
    skimming the record - and :attr:`Neighbourhood.is_exhaustive`, which was a substring test
    over the whole sentence - saw a claim of exactness about a table whose header row was
    picked by counting tags.
    """
    signals = table_signals(
        ["<table><tr><th>Name</th><th>Role</th></tr><tr><td>Jane</td><td>CEO</td></tr></table>"],
        scope=_scope(),
    )
    assert signals
    for signal in signals:
        precision = signal.neighbourhood.precision
        assert precision.startswith(PRECISION_HEURISTIC)
        assert not precision.startswith("exact")
        assert signal.neighbourhood.is_exhaustive is False
    # And the substring test itself is gone, so a sentence that merely *mentions* exhaustiveness
    # cannot make a producer's findings into absence claims.
    said_it = Neighbourhood(
        characters_scanned=1,
        pairs_considered=1,
        scope_read="s",
        precision=f"exact; checked the {PRECISION_EXHAUSTIVE} header row only",
    )
    assert said_it.is_exhaustive is False
    assert Neighbourhood(
        characters_scanned=1, pairs_considered=1, scope_read="s", precision=PRECISION_EXHAUSTIVE
    ).is_exhaustive is True


def test_a_ragged_row_is_reported_and_never_mispaired() -> None:
    """FR-095, and the two halves asserted together because either alone is weak.

    The pairing ``zip`` is ``strict=True`` **and** the width is compared before the loop.
    Removing the comparison alone would let a short row into the loop, where ``strict=True``
    now refuses it; removing ``strict=True`` alone would let a long row be truncated inside
    the loop. Neither failure is the other, so both mechanisms are asserted: the row is not
    mispaired, and it is *reported* rather than dropped with no trace.
    """
    ragged = (
        "<table><tr><th>Name</th><th>Role</th><th>Since</th></tr>"
        "<tr><td>Jane Doe</td><td>CEO</td></tr>"
        "<tr><td>John Roe</td><td>CFO</td><td>2021</td></tr></table>"
    )
    signals = table_signals([ragged], scope=_scope())
    assert {s.extra["row_index"] for s in signals} == {2}
    for signal in signals:
        assert signal.extra["ragged_row_indexes"] == [1]
        assert "row 1 carried 2 cells where the header declared 3" in signal.extra["ragged_rows"][0]
        assert "not paired" in signal.neighbourhood.notes
    # A well-formed table reports nothing, so the field carries information rather than noise.
    clean = table_signals(
        ["<table><tr><th>Name</th><th>Role</th></tr><tr><td>Jane</td><td>CEO</td></tr></table>"],
        scope=_scope(),
    )
    assert clean and all(s.extra["ragged_row_indexes"] == [] for s in clean)


def test_a_dangling_term_is_reported_and_not_dropped() -> None:
    """``zip(..., strict=False)`` discarded the extra ``<dt>``; now it is named.

    A definition list with three terms and two definitions is a document that said something
    the producer could not pair. Before, the odd term vanished and the output was
    indistinguishable from a well-formed list of two - which is the failure FR-095 is about:
    a loss with no trace. The signal is still only emitted for the two pairs that completed,
    because a signal needs two ends; what changed is that the *unpaired* term travels in the
    record.
    """
    signals = list_signals(
        ["<dl><dt>Role</dt><dd>CTO</dd><dt>Employer</dt><dd>Acme</dd><dt>Dangling</dt></dl>"],
        scope=_scope(),
    )
    assert len(signals) == 2
    for signal in signals:
        assert signal.kind is SignalKind.LIST
        assert signal.basis is SignalBasis.ATTRIBUTE_KEY
        assert signal.extra["unpaired_term_indexes"] == [2]
        described = signal.extra["unpaired_terms"]
        assert len(described) == 1
        assert "term 2" in described[0]
        assert "Dangling" in described[0]
        assert "carried no definition" in signal.neighbourhood.notes
    # A balanced list reports nothing, and pairing is still positional and strict.
    balanced = list_signals(["<dl><dt>Role</dt><dd>CTO</dd></dl>"], scope=_scope())
    assert len(balanced) == 1
    assert balanced[0].extra["unpaired_term_indexes"] == []


def test_metadata_puts_the_retrieval_and_the_values_own_text_on_the_two_ends() -> None:
    """FR-094's worst case, and the shape that replaced it.

    A ``<meta>`` tag, a visible ``Role: CTO`` and a JSON-LD scalar all read. The document end
    is the **real** capture ref and the value end is the **value's own text, whole, at its own
    offset**. The field name and the property name are still read and are still the signal's
    ``relation_surface`` - a fact about the markup - but neither is a participant, and the
    literal ``document:current`` and the 64-character cut are gone.
    """
    head = (
        '<head><meta name="author" content="jane@acme.example"></head>'
        "<p>By: Jane Doe</p><p>Role: CTO</p>"
    )
    signals = metadata_signals([head], scope=_scope())
    surfaces = {s.relation_surface for s in signals}
    assert {"author", "by", "Role"} <= surfaces, surfaces
    for signal in signals:
        assert signal.participants[0].mention_ref == f"{DEFERRED_CAPTURE_PREFIX}:CAP-1"
        # The value end carries the document's own words, whole.
        assert signal.participants[0].mention_ref != signal.participants[1].mention_ref
        assert signal.basis in (SignalBasis.METADATA_FIELD, SignalBasis.ATTRIBUTE_KEY)
        assert signal.polarity is Polarity.ASSERTED
        assert signal.direction is DirectionHypothesis.UNDIRECTED
        assert signal.neighbourhood.pairs_considered == 0
        assert "current" not in signal.participants[0].mention_ref
    # And each value resolves to itself at the offset the record claims.
    author = next(s for s in signals if s.relation_surface == "author")
    surface, span = read_occurrence(author.participants[1].mention_ref)[1:]
    assert span is not None
    assert head[span[0] : span[1]] == surface == "jane@acme.example"
    assert author.extra["meta_content"] == "jane@acme.example"
    role = next(s for s in signals if s.relation_surface == "Role")
    surface, span = read_occurrence(role.participants[1].mention_ref)[1:]
    assert span is not None
    assert head[span[0] : span[1]] == surface == "CTO"


def test_metadata_refuses_a_document_with_no_retrieval_behind_it() -> None:
    """The ``document:current`` fallback, replaced by a named refusal.

    ``document:current`` named no retrieval, so two documents' self-descriptions addressed one
    participant and a corpus of ten thousand pages shared one document end. The producer is
    scoped to one document's head and "which document" is the caller's to answer, so a record
    with no ``document_ref`` is refused rather than described under a placeholder that
    resolves against no capture (I-3).
    """
    with pytest.raises(SignalContractError) as caught:
        metadata_signals(
            ['<head><meta name="author" content="jane@acme.example"></head>'],
            scope=_scope(document_ref=""),
        )
    assert caught.value.code == NO_CAPTURE_REF_CODE
    assert "current" in str(caught.value)
    # And an empty head is an answer, not a refusal: there was nothing to describe.
    assert metadata_signals(["   "], scope=_scope()) == ()


def test_metadata_still_reads_what_it_has_no_reading_for() -> None:
    """CD-7 survives the migration: an unrecognised key is reported, not dropped."""
    head = '<meta name="x-custom-thing" content="kept anyway">'
    entries = meta_entries(head)
    assert len(entries) == 1
    assert entries[0][1] == "x-custom-thing"
    assert entries[0][3] == "", "reported as unrecognised rather than dropped"
    signals = metadata_signals([head], scope=_scope())
    assert [s.relation_surface for s in signals] == ["x-custom-thing"]
    assert signals[0].extra["entry_kind"] == "unrecognised"
    assert "CD-7" in signals[0].notes


def test_metadata_does_not_truncate_a_long_value() -> None:
    """**Both** truncations, asserted on a value each of them would have cut.

    There were two, and the second was invisible behind the first. The obvious one cut the
    addressed string at 64 characters. The other was in the *pattern*:
    ``(?P<value>[^<\\n]{0,80})`` stopped a visible ``Key: value`` after 81 characters, so a
    94-character value was cut by the regex and nothing in the record said so. Under the old
    code the two values below were also one participant - they share an 80-character prefix -
    so the corpus reported one fact about a document that stated two.
    """
    stem = "contact" + "x" * 90
    document = f"<p>First: {stem}one</p><p>Second: {stem}two</p>"
    signals = metadata_signals([document], scope=_scope())
    assert len(signals) == 2, signals
    values = [s.participants[1].mention_ref for s in signals]
    assert len(set(values)) == 2, values
    for reference, tail in zip(values, ("one", "two"), strict=True):
        # Whole, not shortened at 64 or at 80.
        assert stem + tail in reference
        _label, surface, span = read_occurrence(reference)
        assert span is not None
        assert surface == stem + tail
        assert document[span[0] : span[1]] == surface
    # And the value-length bound that used to be in the regex is not there any more: a value
    # of 81+ characters is read whole rather than cut.
    assert max(len(s.extra["attribute_value"]) for s in signals) > 80


def test_metadata_says_which_path_it_read_a_field_by() -> None:
    """Three read paths, two bases, and the distinction is not cosmetic.

    A ``<meta>`` tag is the document describing *itself*; a visible ``Key: value`` and a
    JSON-LD scalar are a key/value pair. Filing a schema.org property as a "metadata field"
    is how an external vocabulary gets to describe the internal one, so the basis is passed
    per path rather than defaulted once for the producer.
    """
    signals = metadata_signals(
        [
            (
                '<head><meta name="author" content="jane@acme.example"></head>'
                "<p>Role: CTO</p>"
                '<script type="application/ld+json">{"name": "Acme Holdings"}</script>'
            )
        ],
        scope=_scope(),
    )
    by_kind = {s.kind: s for s in signals}
    assert by_kind[SignalKind.METADATA].basis is SignalBasis.METADATA_FIELD
    assert by_kind[SignalKind.ATTRIBUTE].basis is SignalBasis.ATTRIBUTE_KEY
    assert by_kind[SignalKind.SCHEMA].basis is SignalBasis.ATTRIBUTE_KEY
    # The JSON-LD property name is the surface, and the value is the participant.
    schema = by_kind[SignalKind.SCHEMA]
    assert schema.relation_surface == "name"
    assert read_occurrence(schema.participants[1].mention_ref)[1] == "Acme Holdings"



# --------------------------------------------------------------------------- #
# 3. `assert_bounded`: a real ceiling that a real violation trips
# --------------------------------------------------------------------------- #


def test_assert_bounded_trips_on_a_real_violation() -> None:
    """FR-041…FR-043: a bound nobody can trip is a comment.

    The check is per signal against a stated ceiling, so the test builds a signal whose
    ``pairs_considered`` genuinely exceeds one and asserts the refusal *names the producer
    and the count*. Both halves matter: a bound that does not say which producer reached too
    far tells an operator nothing about which producer to narrow, and one that does not say
    the numbers is a bound nobody can check against the document.
    """
    over = RelationSignal(
        participants=(
            _participant("MN-A", 0),
            _participant("MN-B", 1),
        ),
        kind=SignalKind.CO_OCCURRENCE,
        relation_surface="adjacent",
        basis=SignalBasis.PROXIMITY,
        neighbourhood=Neighbourhood(
            characters_scanned=90_000,
            pairs_considered=12_000,
            scope_read="every pair in the document",
        ),
        producer_ref="exhaustive/co-mention",
        context_ref="ctx-1",
        semantic_regime_ref="regime-1",
        tenant_id=_TENANT,
    )
    # Under the ceiling: nothing happens, so the gate is not a gate that fires on ordinary
    # input - a gate like that teaches people to ignore gates.
    assert_bounded([over], max_pairs_considered=12_000)
    assert_bounded([over], max_pairs_considered=50_000)
    # One under it: refused, by name, with the numbers in the message.
    with pytest.raises(SignalContractError) as caught:
        assert_bounded([over], max_pairs_considered=11_999)
    assert caught.value.code == "signal_neighborhood_unbounded"
    message = str(caught.value)
    assert "exhaustive/co-mention" in message
    assert "12000" in message and "11999" in message
    assert over.signal_id in message
    # And the check is per signal, not per batch: one runaway producer cannot hide behind
    # many cheap ones, which is the averaging the docstring rules out.
    cheap = replace_pairs(over, 3)
    with pytest.raises(SignalContractError):
        assert_bounded([cheap, cheap, cheap, over], max_pairs_considered=11_999)


def test_every_declared_ceiling_is_a_number_the_producer_can_be_checked_against() -> None:
    """Each producer's ``max_pairs_considered`` is positive, and its own report is under it.

    A declaration of zero is refused by :class:`ProducerDeclaration`, and a ceiling larger
    than any number the producer reports is a ceiling nothing reaches. Asserting both ends
    over all five producers is the cheapest way to say the gate is wired up, and it is what
    caught the lexical producer's dead 10,000 before Phase 4B gave it something to measure.
    """
    for producer, sample in (
        (LexicalCueExtractor(), "John became CEO of Acme."),
        (HyperlinkExtractor(), '<a href="/a">a</a>'),
        (TableExtractor(), "<table><tr><th>A</th></tr><tr><td>b</td></tr></table>"),
        (ListExtractor(), "<dl><dt>A</dt><dd>b</dd></dl>"),
        (
            MetadataExtractor(),
            '<head><meta name="author" content="jane@acme.example"></head>',
        ),
    ):
        declaration = producer.declares()
        assert isinstance(declaration, ProducerDeclaration)
        assert declaration.max_pairs_considered >= 1
        signals = producer.extract(sample, scope=_scope())
        assert signals, f"{declaration.producer_ref} found nothing in {sample!r}"
        assert_bounded(
            signals, max_pairs_considered=declaration.max_pairs_considered
        )


# --------------------------------------------------------------------------- #
# 4. FR-034: one hyperlink, one independence unit
# --------------------------------------------------------------------------- #


def test_one_hyperlink_is_one_signal_and_one_independence_unit() -> None:
    """The double-count the link producer used to create, asserted from both sides.

    Two signals per anchor - a ``LINK`` and a ``REFERENCE``, from the same two references and
    with the same surface - were two records of one observation. FR-034 counts independent
    *sources*, so a page with three anchors was read as six and reported twice the
    corroboration in it. The two halves of the test are what make it a guard rather than a
    count: the producer emits one signal per anchor, **and** the two anchors on a page share
    one ``producer_ref`` and one independence family, so even a page of five links is one
    source.
    """
    markup = (
        '<p><a href="https://acme.example/a">first</a> and '
        '<a href="https://acme.example/b">second</a></p>'
    )
    signals = link_signals([markup], scope=_scope())
    assert len(signals) == 2, [s.signal_id for s in signals]
    assert len({s.signal_id for s in signals}) == 2
    assert {s.producer_ref for s in signals} == {HyperlinkExtractor().declares().producer_ref}
    declaration = HyperlinkExtractor().declares()
    assert declaration.independence_family
    assert all(s.producer_ref == declaration.producer_ref for s in signals)
    # And the pair is distinct per anchor, so two anchors are two observations rather than one
    # observation and its own echo - which is what the old second signal produced, since it
    # carried the same two references and the same surface.
    assert signals[0].participants != signals[1].participants
    assert len({(s.subject_mention_ref, s.object_mention_ref) for s in signals}) == 2
    # The same anchor read twice on one page is two occurrences at two positions, not one
    # end corroborating itself.
    repeated = link_signals(['<a href="/x">same</a><a href="/x">same</a>'], scope=_scope())
    assert len(repeated) == 2
    assert len({s.participants[0].mention_ref for s in repeated}) == 2


# --------------------------------------------------------------------------- #
# 5. Constitution Domain Invariant 12: replay is a fixed point
# --------------------------------------------------------------------------- #


def _corpus() -> dict[str, tuple[object, ...]]:
    """One record per producer, so the replay test covers all five rather than one."""
    return {
        "lexical": ("John Smith became CEO of Acme.",),
        "links": (
            (
                '<p><a href="https://acme.example/a">first</a> '
                '<a href="https://acme.example/a">first again</a></p>'
            ),
        ),
        "tables": (
            (
                "<table><tr><th>Name</th><th>Role</th><th>Since</th></tr>"
                "<tr><td>Jane Doe</td><td>CEO</td></tr>"
                "<tr><td>John Roe</td><td>CFO</td><td>2021</td></tr></table>"
            ),
            "<dl><dt>Role</dt><dd>CTO</dd><dt>Dangling</dt></dl>",
        ),
        "metadata": (
            (
                '<head><meta name="author" content="jane@acme.example"></head>'
                "<p>By: Jane Doe</p><p>Role: CTO</p>"
            ),
        ),
        "syntactic": ("John acquired Acme.", "John is not the CEO of Acme."),
    }


def test_replay_is_a_fixed_point_for_every_producer() -> None:
    """Domain Invariant 12, and the property Phase 4B could most easily have broken.

    The participants now carry **character offsets**, which is new: an address that resolved by
    string alone was idempotent by construction, and one that resolves by position is only
    idempotent if the position is derived from the input rather than from a counter, a clock or
    a set's iteration order. A producer that numbered its cells, or that reached for a global,
    would produce a different address on every run - a signal store that re-reads a document
    would fill with what it had already seen, and FR-034's independence count would climb with
    the number of passes.

    So the whole corpus is assembled twice in-process and the ids are compared, **and** the
    duplicate-anchored link is checked separately: the same anchor text and the same href twice
    on one page must be two observations (two positions), not one observation counted twice.
    """
    from extractors.signals.syntactic import syntactic_signals

    def run_once() -> dict[str, tuple[str, ...]]:
        out: dict[str, tuple[str, ...]] = {}
        for name, records in _corpus().items():
            scope = _scope()
            if name == "lexical":
                signals = lexical_signals(records, scope=scope)
            elif name == "links":
                signals = link_signals(records, scope=scope)
            elif name == "tables":
                signals = table_signals(records[:1], scope=scope) + list_signals(
                    records[1:], scope=scope
                )
            elif name == "metadata":
                signals = metadata_signals(records, scope=scope)
            else:
                signals = syntactic_signals(records, scope=scope).signals
            out[name] = tuple(signal.signal_id for signal in signals)
        return out

    first = run_once()
    second = run_once()
    assert first == second
    assert all(first.values()), "the corpus must actually produce signals"
    # And a second *pass over the same records* is one observation, not two, which is what
    # ``dedupe_by_content`` can only do if two runs address alike.
    duplicated = lexical_signals(
        ["John Smith became CEO of Acme."] * 3, scope=_scope()
    )
    assert len(duplicated) == 1, [s.signal_id for s in duplicated]
    tables = table_signals(
        ["<table><tr><th>Name</th></tr><tr><td>Jane</td></tr></table>"] * 2, scope=_scope()
    )
    assert len({s.signal_id for s in tables}) == 1, [s.signal_id for s in tables]


def test_the_ceiling_can_actually_be_reached_by_a_table_too_wide_to_sweep() -> None:
    """FR-041…FR-043 read from the other side: a producer that reads too much is refused.

    The table producer's pair count is a real enumeration - every header against every data
    row - so a table wide enough to exceed the declared ceiling is a real violation rather
    than a contrived one, and the registry catches it on the way out. The test asserts both
    halves: the refusal names the producer and the numbers, and a table just under the ceiling
    passes. A gate that fires on ordinary input is a gate people learn to switch off.
    """
    from extractors.signals.tables import MAX_PAIRS_CONSIDERED as TABLE_CEILING

    columns = 20
    header = "".join(f"<th>C{index}</th>" for index in range(columns))
    wide = (
        f"<table><tr>{header}</tr>"
        + "".join(
            "<tr>" + "".join(f"<td>v{row}c{column}</td>" for column in range(columns)) + "</tr>"
            for row in range(TABLE_CEILING // columns + 2)
        )
        + "</table>"
    )
    with pytest.raises(SignalContractError) as caught:
        table_signals([wide], scope=_scope())
    assert caught.value.code == "signal_neighborhood_unbounded"
    assert "structural/table" in str(caught.value)
    # And a table that fits is read, so the ceiling is a bound rather than a blanket refusal.
    narrow = (
        f"<table><tr>{header}</tr>"
        + "".join(
            "<tr>" + "".join(f"<td>v{row}c{column}</td>" for column in range(columns)) + "</tr>"
            for row in range(TABLE_CEILING // columns - 1)
        )
        + "</table>"
    )
    assert table_signals([narrow], scope=_scope())


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _participant(mention_ref: str, index: int):
    from domain.relation_participant import RelationParticipant

    return RelationParticipant(
        mention_ref=mention_ref, slot=ArgumentSlot(index), ordinal=index
    )


def replace_pairs(signal: RelationSignal, pairs: int) -> RelationSignal:
    from dataclasses import replace

    return replace(
        signal,
        signal_id="",
        neighbourhood=replace(
            signal.neighbourhood,
            characters_scanned=signal.neighbourhood.characters_scanned,
            pairs_considered=pairs,
            scope_read=signal.neighbourhood.scope_read,
            precision=signal.neighbourhood.precision,
            notes=signal.neighbourhood.notes,
        ),
    )



