"""``MentionOccurrenceIndex``: the one ``MN-`` minter, and the inverse it publishes.

Feature 021, brief §25 and §26, spec FR-016, FR-018, FR-019, FR-094;
``repair/ARBITRATION.md`` §8; ``data-model.md`` part 10.1.

**What this file guards.** Phase 4B moved the seven producers off fabricated participant references
and onto deferred occurrence addresses, and left the other half of the job undone: a producer mints
``surface@<start>-<end>:<label>:<surface>``, and the platform had nothing that could turn one into a
mention id. FR-016 calls ``participant.mention_ref`` "a reference *into the mention index*" and no
mention index existed — which is a phrase pointing at nothing, and a producer addressing an
occurrence nothing holds is a participant that corroborates nothing.

So this file is the index, and it is organised around the four properties the rest of the platform
depends on:

1. **One id per five-key tuple.** The mint is a pure function of ``(capture, segment, span,
   normalised surface, extractor occurrence)`` and of nothing else, so the address is recomputable
   from the record and idempotent across replays.
2. **The capture key is not optional.** :func:`test_two_captures_of_one_segment_are_two_mentions`
   and the mutation at the bottom of this file are the same test twice: once asserting the
   property, once demonstrating that removing the key breaks it. An earlier design of this id keyed
   on ``(segment, kind, value, start, end, extractor)`` with no capture, and two retrievals of one
   document addressed to **one** mention — at which point "which fetch saw this mention" is
   unanswerable and FR-034's independence count counts a document against itself.
3. **The published inverse, fail-closed.**
   :func:`test_a_deferred_address_resolves` and
   :func:`test_an_unresolvable_address_is_refused_by_name`
   are the two halves: a producer's address resolves to a real ``MN-``, and one that does not is
   refused with a code that says *which* of the four ways it failed.
4. **The address encoding is injective.** Phase 4B's grammar was
   ``surface[:@<start>-<end>:]<label>:<surface>`` and the label was the text up to the *first*
   ``:``, so the syntactic producer's dependency-arc labels — ``nmod:of``, ``nsubj:pass`` — made
   ``surface:nmod:of:acme`` an address of ``of:acme``. Two distinct occurrences, one string, and
   nothing downstream could tell the misparse from a surface that genuinely contains a colon.
   :func:`test_the_address_round_trips_over_every_adversarial_input` and
   :func:`test_the_address_encoding_is_injective_so_no_two_occurrences_share_one_string` are the
   property and the defect class;
   :func:`test_an_address_written_under_the_retired_grammar_is_refused_by_name` is requirement
   five, and :func:`test_dropping_the_self_delimiting_payload_brings_the_collision_back` removes
   the guard and shows the collision returning.
5. **Determinism under replay (constitution Domain Invariant 12).** No clock, no randomness, no
   dict-order dependence — :func:`test_replay_in_a_second_process_mints_identical_ids` and the
   source scan in :func:`test_the_index_has_no_clock_and_no_randomness`.


**Where it lives, and the inversion it avoids.** ``apps/shared/domain/``. The only other ``MN-``
minter was ``semantic_path.execution.mention_id_for``, and that module imports
:mod:`extractors.registry` and :mod:`graph.relation_store` — it is the composition root, wired to
``apps/interpretation`` and ``apps/projection``. A producer importing it would take the edge
producer → composition root and pull the graph package into extraction. ``domain`` sits strictly
below both, so both can reach it and neither is reached.
:func:`test_nothing_outside_the_index_mints_a_mention_id`
is the source scan that keeps it that way.
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

from domain.mention_occurrence_index import (
    DEFERRED_ADDRESS_VERSION,
    DEFERRED_CAPTURE_PREFIX,
    DEFERRED_OCCURRENCE_PREFIX,
    MENTION_ID_PREFIX,
    MENTION_OCCURRENCE_KEY_COUNT,
    DeferredCaptureAddress,
    DeferredOccurrenceAddress,
    MentionBindingError,
    MentionOccurrence,
    MentionOccurrenceIndex,
    MentionOccurrenceKey,
    mint_capture_address,
    mint_mention_id,
    mint_occurrence_address,
    parse_deferred_address,
)
from domain.predicate_signature import normalize_surface_for_fingerprint
from domain.relation_identity import canonical_material, digest128

pytestmark = pytest.mark.unit

#: ``apps/shared``, so the source scan can read the two modules that matter.
SHARED = Path(__file__).resolve().parents[2]
INDEX_SOURCE = SHARED / "domain" / "mention_occurrence_index.py"

_SCOPE = {
    "capture_ref": "CAP-1",
    "segment_ref": "SEG-1",
    "extractor_ref": "deterministic-extractor-set",
}
_ACME = (0, 4, "Acme")
_MICROSOFT = (5, 14, "Microsoft")


def _key(
    *, start: int | None = None, end: int | None = None, surface: str | None = None, **over: str
) -> MentionOccurrenceKey:
    """A mint key for one occurrence, with the scope's three keys defaulted."""
    default_start, default_end, default_surface = _ACME
    return MentionOccurrenceKey.of(
        start=default_start if start is None else start,
        end=default_end if end is None else end,
        surface=default_surface if surface is None else surface,
        **{**_SCOPE, **over},
    )


def _occurrence(start: int, end: int, surface: str, kind: str = "org") -> MentionOccurrence:
    return MentionOccurrence(kind=kind, surface=surface, start=start, end=end)


def _index(*occurrences: MentionOccurrence, **over: str) -> MentionOccurrenceIndex:
    return MentionOccurrenceIndex(occurrences=occurrences, **{**_SCOPE, **over})


def _address(
    label: str = "object", surface: str = "Acme", span: tuple[int, int] | None = (0, 4)
) -> str:
    """An address, **through the one minter** — never assembled here.

    A test that spelled the string out would be a second answer to "what does an address look
    like", and it would keep passing if the minter changed. Everything below reaches the grammar
    the way a producer does.
    """
    return mint_occurrence_address(
        label=label,
        surface=surface,
        start=None if span is None else span[0],
        end=None if span is None else span[1],
    )


# --------------------------------------------------------------------------- #
# The five keys, and the mint
# --------------------------------------------------------------------------- #


def test_the_mint_tuple_is_exactly_the_five_keys_fr018_names() -> None:
    """Five, in the order ``data-model.md`` part 10.1 and FR-018 name them.

    Asserted three ways so a key cannot be quietly added or dropped: the arity of
    :attr:`MentionOccurrenceKey.as_tuple`, its contents, and
    :data:`MENTION_OCCURRENCE_KEY_COUNT` — which exists only so the spec's "five" is checkable
    against something rather than being a claim in a docstring.
    """
    keys = _key().as_tuple()
    assert len(keys) == MENTION_OCCURRENCE_KEY_COUNT == 5
    assert keys == ("CAP-1", "SEG-1", (0, 4), "acme", "deterministic-extractor-set")
    # The offsets are **one** key carrying two, which is why the tuple is five wide and not six.
    assert isinstance(keys[2], tuple) and len(keys[2]) == 2
    # And the surface is the platform's own normalisation, not a second one written here.
    assert keys[3] == normalize_surface_for_fingerprint("  Acme ") == "acme"


def test_one_five_key_tuple_mints_exactly_one_id() -> None:
    """Idempotency, and the address is recomputable from the record alone.

    FR-005/I-11: identical content yields an identical id, so a re-run does not fill a store with
    what it has already seen. The second half matters as much — a caller handed an ``MN-`` must be
    able to check it against the occurrence, and that is only possible if the mint is a public pure
    function of the key rather than something the index does in private.
    """
    key = _key()
    assert mint_mention_id(key) == mint_mention_id(key)
    assert mint_mention_id(key).startswith(MENTION_ID_PREFIX)
    assert len(mint_mention_id(key)) == len(MENTION_ID_PREFIX) + 32
    # Recomputed from the record, with no index in sight: the platform's own primitive, so a
    # backend, a replay and this test cannot disagree.
    assert mint_mention_id(key) == MENTION_ID_PREFIX + digest128(
        canonical_material(["CAP-1", "SEG-1", [0, 4], "acme", "deterministic-extractor-set"])
    )


def test_each_of_the_five_keys_moves_the_id() -> None:
    """Five fixtures, one per key, because "five keys" that four of them are not would still pass.

    ``kind`` is the one thing that must **not** move it, and it is asserted too: a producer's
    classification of an occurrence is evidence about a mention rather than part of its identity.
    """
    base = mint_mention_id(_key())
    for over in (
        {"capture_ref": "CAP-2"},
        {"segment_ref": "SEG-2"},
        {"extractor_ref": "other-extractor"},
    ):
        assert mint_mention_id(_key(**over)) != base, over
    assert mint_mention_id(_key(start=1)) != base, "the start offset is a key"
    assert mint_mention_id(_key(end=5)) != base, "the end offset is a key"
    # Surface, through the shared normalisation: ``"Acme"`` and ``" acme "`` are one mention.
    assert mint_mention_id(_key(surface=" acme ")) == base
    assert mint_mention_id(_key(surface="Acme Corp")) != base
    # And the kind is evidence, not identity - it is refused at bind time, not folded in here.
    index = _index(_occurrence(0, 4, "Acme", kind="org"))
    assert mint_mention_id(_key()) == index.mention_id_for(_occurrence(0, 4, "Acme", kind="person"))


def test_two_captures_of_one_segment_are_two_mentions() -> None:
    """The collision this key was added to prevent, and the test that is asserted twice.

    A segment is a *document region* and a capture is a *retrieval*, so one segment legitimately
    exists in two captures: the same page fetched twice, a crawl replay, a re-index. The mint tuple
    that omits the capture addresses both to **one** mention id, and everything downstream then
    fails quietly rather than loudly: the platform cannot say which fetch saw the mention, and
    FR-034's independence count counts a document against itself.

    Asserted from both sides — the two ids differ, **and** the two indexes disagree about nothing
    else, so the capture really is the only thing separating them.
    """
    first = _index(_occurrence(*_ACME), capture_ref="CAP-1")
    second = _index(_occurrence(*_ACME), capture_ref="CAP-2")
    assert first.mention_id_for(_occurrence(*_ACME)) != second.mention_id_for(_occurrence(*_ACME))
    # Everything else identical, and the difference is attributable.
    assert [key.as_tuple()[1:] for key in first.keys] == [key.as_tuple()[1:] for key in second.keys]
    assert [key.as_tuple()[0] for key in first.keys] == ["CAP-1"]
    assert [key.as_tuple()[0] for key in second.keys] == ["CAP-2"]
    # And each address resolves only in its own capture's index - a lookup that could straddle
    # captures would be the same collision wearing a hat.
    address = _address()
    assert first.require_occurrence(address).mention_id == first.mention_id_for(
        _occurrence(*_ACME)
    )
    assert second.read_occurrence(address) is not None
    assert first.keys[0].capture_ref != second.keys[0].capture_ref


# --------------------------------------------------------------------------- #
# The inverse
# --------------------------------------------------------------------------- #


def test_a_deferred_address_resolves() -> None:
    """The seam, working: a producer's address becomes a real ``MN-``, with its key intact.

    The whole reason the module exists. Before it, this address was a string no table could answer
    for, and the signal carrying it went into assembly looking like a participant and behaving
    like one.
    """
    index = _index(_occurrence(*_ACME), _occurrence(*_MICROSOFT))
    address = _address()
    resolved = index.require_occurrence(address)
    assert resolved.mention_id == mint_mention_id(_key())
    assert resolved.label == "object"
    assert resolved.address == address
    assert resolved.key == _key()
    assert resolved.occurrence == _occurrence(*_ACME)
    # And the resolution is checkable from the value alone, which is what makes it evidence.
    assert mint_mention_id(resolved.key) == resolved.mention_id
    assert resolved.to_dict()["mention_id"] == resolved.mention_id

    # Surfaces that contain the separators still round-trip, because the position is the first
    # component and the surface is the whole remainder.
    for surface, span in (
        ("jane@acme.example", (35, 52)),
        ("https://acme.example/team?ref=a@b", (16, 48)),
        ("a:b:c", (1, 6)),
    ):
        address = _address(label="value", surface=surface, span=span)
        assert parse_deferred_address(address) == DeferredOccurrenceAddress("value", surface, span)
        scoped = _index(_occurrence(span[0], span[1], surface))
        assert scoped.require_occurrence(address).mention_id.startswith(MENTION_ID_PREFIX)


def test_an_unresolvable_address_is_refused_by_name() -> None:
    """Four refusals, four codes, and each names a different operator's bug.

    A single "could not resolve" message would hide three of them: an address that is not an
    address at all is a producer bug, an occurrence the index does not hold is a coverage gap, an
    unpositioned address matching several occurrences is a producer that stated no position, and a
    capture is a fetch event rather than a mention. Only the second is "unresolved" in the sense a
    reader would guess, and the first would be reported as unresolved forever.
    """
    index = _index(_occurrence(*_ACME))
    with pytest.raises(MentionBindingError) as unreadable:
        index.require_occurrence("entity:42")
    assert unreadable.value.code == "mention_address_unreadable"

    with pytest.raises(MentionBindingError) as capture:
        index.require_occurrence(f"{DEFERRED_CAPTURE_PREFIX}:CAP-1")
    assert capture.value.code == "mention_capture_is_not_a_mention"
    assert "STOP" in str(capture.value)
    # ...and the retrieval end is still readable, because a ``CAP-`` id needs no mention.
    assert index.read_capture(f"{DEFERRED_CAPTURE_PREFIX}:CAP-1") == "CAP-1"
    assert index.read_capture(_address()) is None

    with pytest.raises(MentionBindingError) as unresolved:
        index.require_occurrence(_address(label="object", surface="Microsoft", span=(5, 14)))
    assert unresolved.value.code == "mention_occurrence_unresolved"
    assert "STOP" in str(unresolved.value)

    # Ambiguity is refused rather than resolved: an unpositioned address that names two
    # occurrences of one surface, where picking one would invent a position nobody stated.
    twice = _index(_occurrence(0, 4, "Acme"), _occurrence(20, 24, "Acme"))
    unpositioned = _address(span=None)
    assert twice.read_occurrence(unpositioned) is None
    with pytest.raises(MentionBindingError) as ambiguous:
        twice.require_occurrence(unpositioned)
    assert ambiguous.value.code == "mention_occurrence_ambiguous"
    assert "do not take the first match" in str(ambiguous.value)
    # One occurrence is not ambiguous, so the syntactic producer's unpositioned form still works.
    assert index.require_occurrence(unpositioned)


def test_the_index_scope_is_required_and_never_defaulted() -> None:
    """Three required components, and a blank one is refused.

    The scope supplies three of the five mint keys, so defaulting any of them is a silent
    substitution of one retrieval, document or instrument for another — the same reason
    :class:`extractors.signals.protocol.ExtractionScope` requires a frame and a regime. ``""`` is a
    legal *value* for an extractor that did not name itself; it is refused as a *key*, so the
    scope cannot collapse into an index that mints ids nobody can trace.
    """
    for blank in ("capture_ref", "segment_ref", "extractor_ref"):
        with pytest.raises(MentionBindingError) as caught:
            MentionOccurrenceIndex(**{**_SCOPE, blank: "  "})
        assert caught.value.code == "mention_index_scope_required", blank
    with pytest.raises(MentionBindingError) as caught:
        _key(capture_ref="")
    assert caught.value.code == "mention_occurrence_key_incomplete"


def test_a_disagreement_about_one_occurrence_is_refused_rather_than_merged() -> None:
    """Two records contradicting each other at one address, both refused by name.

    Neither case is resolvable here and both would be silently *decided* by anything that picked a
    winner: which surface the offsets hold, and which kind the occurrence is. A kind disagreement in
    particular is the interesting one — a producer's classification is evidence, so it must not
    fork the address, and it must not be dropped either.
    """
    index = _index(_occurrence(0, 4, "Acme", kind="org"))
    with pytest.raises(MentionBindingError) as surface:
        index.bind(_occurrence(0, 4, "Acme Corp", kind="org"))
    assert surface.value.code == "mention_span_disagreement"
    with pytest.raises(MentionBindingError) as kind:
        index.bind(_occurrence(0, 4, "Acme", kind="person"))
    assert kind.value.code == "mention_kind_disagreement"
    # Binding the same occurrence again is idempotent, not a conflict.
    assert index.bind(_occurrence(0, 4, "Acme", kind="org")).mention_id == index.bind(
        _occurrence(0, 4, "Acme", kind="org")
    ).mention_id
    assert len(index) == 1


# --------------------------------------------------------------------------- #
# The grammar has one home
# --------------------------------------------------------------------------- #


def test_the_deferred_grammar_is_defined_once_and_the_producer_re_exports_it() -> None:
    """Two consumers, one definition — because a format with two homes drifts silently.

    :mod:`domain.mention_occurrence_index` is the only place the prefixes are *defined* (the index
    has to read what the producer wrote) and the only place the parse *exists*; the producer-side
    :mod:`extractors.signals.mentions` imports and re-exports them so the contract keeps its name,
    its location and its refusals. Read from the AST so a docstring *naming* the prefixes — which
    both modules' do, at length — cannot read as a second definition.

    The test is here rather than in ``apps/interpretation`` because the thing being pinned is that
    :mod:`domain` does not import upward, and a test inside the app that imports the producer could
    not see the dependency edge it is asserting is absent.
    """
    producer = (
        SHARED.parent / "interpretation" / "extractors" / "signals" / "mentions.py"
    ).resolve()
    assert producer.is_file(), producer

    def definitions(path: Path) -> list[str]:
        """Names assigned one of the two prefixes as a **literal**, docstrings excluded."""
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found: list[str] = []
        for node in ast.walk(tree):
            targets = ()
            value = None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign):
                targets, value = (node.target,), node.value
            if not isinstance(value, ast.Constant) or value.value not in {
                DEFERRED_OCCURRENCE_PREFIX,
                DEFERRED_CAPTURE_PREFIX,
            }:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    found.append(target.id)
        return found

    assert definitions(INDEX_SOURCE) == [
        "DEFERRED_OCCURRENCE_PREFIX",
        "DEFERRED_CAPTURE_PREFIX",
    ]
    assert definitions(producer) == [], (
        "extractors/signals/mentions.py assigns one of the two prefix literals, so the grammar "
        "has a second home; it must import them from domain.mention_occurrence_index"
    )
    # And the parse exists in exactly one module, for the same reason.
    assert [
        path.name
        for path in (INDEX_SOURCE, producer)
        if "def parse_deferred_address" in path.read_text(encoding="utf-8")
    ] == [INDEX_SOURCE.name]
    # The producer reaches the vocabulary by import, so the two modules agree by construction.
    assert "from domain.mention_occurrence_index import" in producer.read_text(encoding="utf-8")


def test_the_grammar_refuses_the_blanks_it_used_to_admit() -> None:
    """Every string the retired grammar could spell, plus the malformed ones, is unreadable.

    These are well-formed *looking* strings that name no occurrence, and the retired grammar could
    not tell an empty label from a missing field — ``surface::Acme`` and ``surface:object:`` were
    both "the label is blank" as a **string**, so the parser had to refuse the string. The current
    grammar states all four fields whether or not they are blank, so the blank is a value and
    round-trips (:func:`test_the_address_round_trips_over_every_adversarial_input`); what is
    refused here is what is genuinely unreadable — the retired form, an inverted or
    non-canonical span, a blank capture ref, and nothing at all.
    """
    for unreadable in (
        # The retired grammar, in both shapes. Refused, never decoded into a wrong pair.
        f"{DEFERRED_OCCURRENCE_PREFIX}::Acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}:object:",
        f"{DEFERRED_OCCURRENCE_PREFIX}@0-4:object:",
        f"{DEFERRED_OCCURRENCE_PREFIX}@0-4:object:Acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}:object:Acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}:nmod:of:acme",
        # Malformed spans, including the two ``int`` would have accepted.
        f"{DEFERRED_OCCURRENCE_PREFIX}@4-0:object:Acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}@-1-4:object:Acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}@x-y:object:Acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}@1_0-11:object:Acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}@00-04:object:Acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}@0-4:object",
        f"{DEFERRED_CAPTURE_PREFIX}:",
        "",
    ):
        assert parse_deferred_address(unreadable) is None, unreadable
    assert isinstance(
        parse_deferred_address(mint_capture_address("CAP-1")), DeferredCaptureAddress
    )


# --------------------------------------------------------------------------- #
# The address encoding is injective, and the retired grammar fails loudly
# --------------------------------------------------------------------------- #


#: The adversarial inputs, chosen because each one broke or would break a naive encoding.
#:
#: * ``nmod:of`` / ``nmod`` with ``of:acme`` — **the collision that existed.** A syntactic
#:   producer's labels are dependency arcs and several contain the separator, so the retired
#:   grammar minted ``surface:nmod:of:acme`` and read it as ``nmod`` / ``of:acme``. Both rows are
#:   here so the property is checked over the *pair*, not over one member of it.
#: * ``:``, ``|``, ``@``, a newline and a tab — every character a separator might plausibly be,
#:   and the reason "pick a rarer separator" is not a fix.
#: * ``Café Holdings — 日本 🙂`` — non-ASCII, including an astral-plane code point, because an
#:   encoding that counts bytes rather than characters is a different encoding.
#: * ``["a",1,null]`` — a surface that is *itself* the text of the payload format.
#: * ``""`` and a blank label — the empty string, which the old grammar could not express at all
#:   and the new one states as a value.
#: * a whole v1 address used as a surface — the payload must not be able to impersonate its own
#:   frame.
_ADVERSARIAL_ADDRESSES: tuple[tuple[str, str, tuple[int, int] | None], ...] = (
    ("object", "Acme", (0, 4)),
    ("nmod:of", "acme", None),
    ("nmod", "of:acme", None),
    ("nsubj:pass", "the company", (0, 11)),
    ("value", "a:b:c", (1, 6)),
    ("value", "jane@acme.example", (35, 52)),
    ("value", "https://acme.example/team?ref=a@b", (16, 48)),
    ("value", "a|b", None),
    ("value", "line one\nline two\ttabbed", (0, 24)),
    ("value", "Café Holdings — 日本 🙂", None),
    ("value", '["a",1,null]', None),
    ("value", "", (0, 0)),
    ("", "Acme", None),
    ("obj", f"{DEFERRED_OCCURRENCE_PREFIX}:1:{'0' * 32}:x", None),
    ("value", "Acme", (0, 0)),
)


def _mint(label: str, surface: str, span: tuple[int, int] | None) -> str:
    return mint_occurrence_address(
        label=label,
        surface=surface,
        start=None if span is None else span[0],
        end=None if span is None else span[1],
    )


def test_the_address_round_trips_over_every_adversarial_input() -> None:
    """The property the fix exists for: ``decode(encode(x)) == x`` for **every** ``x``.

    Not for the inputs the platform happens to produce today — for the ones that broke the
    retired encoding, plus the ones that break naive replacements of it. Each row is asserted in
    both directions: the string reads back as the exact triple, and the triple mints exactly one
    string. ``_ADVERSARIAL_ADDRESSES`` carries the reasoning per row; what is asserted here is
    that the grammar makes none of it matter.
    """
    for label, surface, span in _ADVERSARIAL_ADDRESSES:
        address = _mint(label, surface, span)
        parsed = parse_deferred_address(address)
        assert isinstance(parsed, DeferredOccurrenceAddress), (label, surface, span, address)
        assert (parsed.label, parsed.surface, parsed.span) == (label, surface, span), address
        assert parsed.positioned is (span is not None), address
        # And the mint is pure: the same triple twice is the same string, in any order of the
        # keyword arguments. An address is a join key, so an address that moved would be a
        # duplicate of itself.
        assert _mint(label, surface, span) == address
    # The capture end too, and it is a different class of string: one field, the whole remainder.
    for ref in ("CAP-1", "capture:CAP-1:inside", "  spaced  ", ""):
        address = mint_capture_address(ref)
        parsed = parse_deferred_address(address)
        if not ref.strip():
            assert parsed is None, address
        else:
            assert isinstance(parsed, DeferredCaptureAddress), address
            assert parsed.capture_ref == ref.strip(), address


def test_the_address_encoding_is_injective_so_no_two_occurrences_share_one_string() -> None:
    """**The defect class itself**, asserted as a property of the encoder rather than a case.

    The retired grammar was not injective: ``("nmod:of", "acme")`` and ``("nmod", "of:acme")``
    both produced ``surface:nmod:of:acme``. One string, two occurrences, and nothing downstream
    could tell them apart. The fix is not "this pair no longer collides" — it is that **no** pair
    does — so the assertion is pairwise distinctness over the whole adversarial table, and the
    specific collision is called out separately so the failure names the case that regressed.
    """
    minted = {
        _mint(label, surface, span): (label, surface, span)
        for label, surface, span in _ADVERSARIAL_ADDRESSES
    }
    assert len(minted) == len(_ADVERSARIAL_ADDRESSES), (
        "two distinct occurrences minted one address, so the encoding is not injective: "
        f"{sorted((t, [k for k, v in minted.items() if v == t]) for t in minted.values())}"
    )

    def _parsed(label: str, surface: str, span: tuple[int, int] | None):
        parsed = parse_deferred_address(_mint(label, surface, span))
        assert isinstance(parsed, DeferredOccurrenceAddress)
        return parsed.label, parsed.surface, parsed.span

    # The case the parser used to break, from both sides. The syntactic producer's dependency-arc
    # labels are ``nmod:of``, ``nmod:in``, ``nmod:by`` and ``nsubj:pass``; each is a real label
    # and each reads back as itself.
    for arc in ("nmod:of", "nmod:in", "nmod:by", "nsubj:pass", "obl:tmod"):
        assert _parsed(arc, "acme", None) == (arc, "acme", None), arc
        assert _parsed(arc, "Acme", (0, 4)) == (arc, "Acme", (0, 4)), arc
    # ... and it is a *different address* from the one the retired grammar read out of the very
    # same string, which is the whole claim.
    assert _mint("nmod:of", "acme", None) != _mint("nmod", "of:acme", None)
    assert _parsed("nmod", "of:acme", None) == ("nmod", "of:acme", None)


def test_the_parser_verifies_the_address_instead_of_interpreting_it() -> None:
    """Every component is checked, so a mangled string is refused rather than best-read.

    The content address is what makes this possible and is why the address is a *content* address
    rather than a format: the payload's own digest is recomputed, the span in the prefix must be
    the span in the payload, the version must be the version, and the span must be canonical. A
    string this module did not write cannot be read — which is what "never guess" has to mean for
    an identifier.
    """
    address = _mint("nmod:of", "acme", (3, 7))
    _frame, version, digest, _payload = address.split(":", 3)
    for mangled in (
        # A future version. Silent acceptance here is how a v2 gets read as a v1.
        address.replace(f":{version}:", ":2:", 1),
        address.replace(f":{version}:", "::", 1),
        # A digest that is not this payload's. One character is enough.
        address.replace(digest, "0" * 32, 1),
        address.replace(digest, digest[:-1], 1),
        # A payload that is not this digest's.
        address.replace('"acme"', '"acm"', 1),
        address.replace('"acme"', '"acme "', 1),
        # The prefix span disagreeing with the payload's, in both directions.
        address.replace("surface@3-7:", "surface@7-7:", 1),
        address.replace("surface@3-7:", "surface@0-0:", 1),
        # The positioned form with the span stripped, and the unpositioned form with one added.
        address.replace("surface@3-7:", f"{DEFERRED_OCCURRENCE_PREFIX}:", 1),
        f"{DEFERRED_OCCURRENCE_PREFIX}@" + address.split(":", 1)[1],
        # Truncated and over-long.
        address[:-1],
        address + "x",
        "",
    ):
        assert parse_deferred_address(mangled) is None, mangled
    # The one that is not a mangled address: a payload that happens to be valid JSON but not the
    # payload the mint writes. Refused on arity or on type, never half-read.
    for payload in ('["l","acme"]', '["l","acme",null,null,"extra"]', '{"l":"acme"}', "null"):
        candidate = ":".join([DEFERRED_ADDRESS_VERSION, digest128(payload), payload])
        assert parse_deferred_address(f"{DEFERRED_OCCURRENCE_PREFIX}:{candidate}") is None, payload


def test_an_address_written_under_the_retired_grammar_is_refused_by_name() -> None:
    """Requirement five, on the strings a pre-change store actually holds.

    The old encoding is not decoded, in any of its shapes and with any of the labels that made it
    collide. A corpus or a store written before the change produces
    ``mention_address_unreadable`` — a refusal an operator can act on — and never a decode into a
    label and a surface its writer never meant. The message names the retired form for that
    reason: ``surface:nmod:of:acme`` is the single most confusing string a reader of an old store
    will meet, and saying "not an address" without saying which addresses exist would send them
    looking for a parser bug instead of at the version.
    """
    index = _index(_occurrence(0, 4, "acme"))
    for retired in (
        f"{DEFERRED_OCCURRENCE_PREFIX}:nmod:of:acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}:nsubj:pass:john smith",
        f"{DEFERRED_OCCURRENCE_PREFIX}:obj:of:acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}@0-4:object:Acme",
        f"{DEFERRED_OCCURRENCE_PREFIX}@0-4:nmod:of:acme",
    ):
        assert parse_deferred_address(retired) is None, retired
        assert index.read_occurrence(retired) is None, retired
        with pytest.raises(MentionBindingError) as refused:
            index.require_occurrence(retired)
        assert refused.value.code == "mention_address_unreadable", retired
        message = str(refused.value)
        assert DEFERRED_ADDRESS_VERSION in message, message
        assert f"{DEFERRED_OCCURRENCE_PREFIX}[:@<start>-<end>:]<label>:<surface>" in message, (
            "the refusal must name the form it replaced, or an operator holding a pre-change "
            f"store cannot tell a version change from a bug: {message!r}"
        )
    # And the four codes keep their stop conditions beside it: a refused old address is *not* an
    # unresolved occurrence and *not* a capture, so the refusal does not shadow the other three.
    with pytest.raises(MentionBindingError) as unresolved:
        index.require_occurrence(_mint("object", "Microsoft", (5, 14)))
    assert unresolved.value.code == "mention_occurrence_unresolved"
    with pytest.raises(MentionBindingError) as capture:
        index.require_occurrence(mint_capture_address("CAP-1"))
    assert capture.value.code == "mention_capture_is_not_a_mention"
    with pytest.raises(MentionBindingError) as ambiguous:
        _index(_occurrence(0, 4, "Acme"), _occurrence(9, 13, "Acme")).require_occurrence(
            _mint("object", "Acme", None)
        )
    assert ambiguous.value.code == "mention_occurrence_ambiguous"


def test_the_mint_and_the_parse_are_defined_once_each_and_nothing_else_builds_an_address() -> None:
    """One minter per identifier kind, and this is the source scan that keeps it one.

    ``MN-`` has one minter, enforced by :func:`test_nothing_outside_the_index_mints_a_mention_id`.
    An occurrence address now has one too, and the scan is here for the same reason: the retired
    collision existed *because* :mod:`parsers.shallow` built the string itself against a grammar
    that split on the first ``:``, and a source scan is the only thing that catches a second
    builder before a document contains a label that breaks it.

    Three shapes, three properties:

    * exactly one definition of each half of the grammar, anywhere in the repository;
    * no non-docstring string literal in the **production source** *begins with* a namespace
      prefix — the fragments of an f-string included, so ``f"surface:{x}"`` is caught as the
      ``"surface:"`` it is built from. Production source, not tests: a test has to be able to
      *name* the form to assert it (that is the form's specification, and this very file does it
      in a docstring), while a producer that assembles one is minting in its own namespace. The
      "begins with" test is what keeps a refusal message that happens to contain the English word
      ``capture:`` from reading as a construction;
    * every module that touches the grammar at all imports both halves rather than re-deriving
      them, and the parser reaches the grammar by import rather than by reaching upward into the
      producer package.
    """
    apps = tuple(sorted(path.name for path in (SHARED.parent).iterdir() if path.is_dir()))
    # Every app, not the three the mention layer sits in. "One minter per identifier kind" is a
    # claim about the repository, and a claim scoped to the three directories it happens to live in
    # is a claim that stops being true the first time a fourth app reaches for a participant
    # address. Parsed once and reused for every half of the scan, and read as ``utf-8-sig`` because
    # a migration in this repository carries a BOM and a scan that dies on an unparseable file is a
    # scan that quietly stops covering the rest of the tree.
    trees = {
        path: ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for app in apps
        for path in sorted((SHARED.parent / app).rglob("*.py"))
        if "__pycache__" not in path.parts
    }
    defined: dict[str, list[str]] = {"mint_occurrence_address": [], "parse_deferred_address": []}
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in defined:
                defined[node.name].append(path.relative_to(SHARED.parent).as_posix())
    assert defined == {
        "mint_occurrence_address": ["shared/domain/mention_occurrence_index.py"],
        "parse_deferred_address": ["shared/domain/mention_occurrence_index.py"],
    }, defined
    # The capture end has a minter too, so the vocabulary has no orphan half.
    assert [
        path.relative_to(SHARED.parent).as_posix()
        for path, tree in trees.items()
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "mint_capture_address"
    ] == ["shared/domain/mention_occurrence_index.py"]

    offenders: list[str] = []
    for path, tree in trees.items():
        if "tests" in path.relative_to(SHARED.parent).parts:
            continue
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node.value in docstrings:
                continue
            for prefix in (DEFERRED_OCCURRENCE_PREFIX, DEFERRED_CAPTURE_PREFIX):
                if node.value.startswith(f"{prefix}:"):
                    offenders.append(
                        f"{path.relative_to(SHARED.parent).as_posix()}:{node.lineno} builds "
                        f"{node.value!r}"
                    )
    assert not offenders, (
        "a module outside the index builds an occurrence-address prefix (FR-094, and the "
        "collision the retired grammar had):\n  " + "\n  ".join(sorted(offenders))
    )

    # The parser reaches the producer-side contract, and the producer reaches the grammar, both by
    # import - which is what makes the one-definition assertion above the whole story.
    seam = SHARED.parent / "interpretation" / "extractors" / "signals" / "mentions.py"
    producer = seam.read_text(encoding="utf-8")
    assert "from domain.mention_occurrence_index import" in producer
    for named in ("mint_occurrence_address", "mint_capture_address", "parse_deferred_address"):
        assert f"    {named},\n" in producer, f"{named} is imported, not re-derived"


# --------------------------------------------------------------------------- #
# The mutation tests: remove a guard, and the collision it prevented must come back
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# One minter, no clock, no randomness
# --------------------------------------------------------------------------- #


def test_nothing_outside_the_index_mints_a_mention_id() -> None:
    """The source scan, because "one minter" is a property of the repository and not of a file.

    Every ``MN-`` string built anywhere outside :mod:`domain.mention_occurrence_index` is a second
    answer to "which mention is this". ``signal_corpus`` and the structural-conflict suite carry
    ``MN-A``/``MN-B`` as *fixture* refs, which is a different thing: they are read by name, never
    derived, and no derivation could be checked against them. So the scan looks for the two shapes
    a *derivation* takes — the prefix concatenated onto something, and the prefix assigned to a
    name — and exempts neither test nor corpus fixture by name, only by shape.
    """
    roots = (
        SHARED / "domain",
        SHARED.parent / "interpretation" / "extractors",
        SHARED.parent / "interpretation" / "parsers",
        SHARED.parent / "control-plane" / "semantic_path",
    )
    offenders: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if path.resolve() == INDEX_SOURCE.resolve():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
                    left, right = node.left, node.right
                    derived = isinstance(left, ast.Constant) and left.value == MENTION_ID_PREFIX
                    derived = derived or (
                        isinstance(right, ast.Constant) and right.value == MENTION_ID_PREFIX
                    )
                    if derived:
                        offenders.append(f"{path.name}:{node.lineno} concatenates MN-")
                if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id.endswith("MENTION_ID_PREFIX")
                    for target in node.targets
                ):
                    offenders.append(f"{path.name}:{node.lineno} assigns an MN- prefix")
    assert not offenders, "a second MN- minter exists:\n  " + "\n  ".join(sorted(offenders))
    # And the index itself is where the one prefix lives.
    assert INDEX_SOURCE.read_text(encoding="utf-8").count(f'{MENTION_ID_PREFIX}"') == 1


def test_the_index_has_no_clock_and_no_randomness() -> None:
    """Constitution Domain Invariant 12, asserted on the source.

    A mention id is a join key: the same occurrence read twice, in two processes, at two times, must
    produce the same string or the graph fills with duplicates of itself. ``uuid4`` would make every
    id unique and every join a miss; ``datetime.now`` would do the same at replay. The scan reads
    the AST, so a docstring *naming* the banned calls — which this file's own does — cannot read as
    a call.
    """
    tree = ast.parse(INDEX_SOURCE.read_text(encoding="utf-8"))
    banned = {"uuid4", "now", "utcnow", "time", "monotonic", "perf_counter", "random"}
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports |= {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not {name for name in imports if name in {"uuid", "random", "time", "secrets", "os"}}
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & banned, called & banned
    # Iteration is over sorted keys, never over a bare set/dict.
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.iter, (ast.Set, ast.Dict)):
            raise AssertionError(
                f"{INDEX_SOURCE.name}:{node.lineno} iterates an unordered container"
            )


_REPLAY_SCRIPT = """
import sys
sys.path.insert(0, ".")
from domain.mention_occurrence_index import (
    MentionOccurrence,
    MentionOccurrenceIndex,
    mint_occurrence_address,
)

index = MentionOccurrenceIndex(
    capture_ref="CAP-1", segment_ref="SEG-1", extractor_ref="deterministic-extractor-set",
    occurrences=[
        MentionOccurrence(kind="org", surface="Acme", start=0, end=4),
        MentionOccurrence(kind="org", surface="Microsoft", start=5, end=14),
    ],
)
print("IDS", [index.mention_id_for(o) for o in index.occurrences])
print("RESOLVED", index.require_occurrence(
    mint_occurrence_address(label="object", surface="Acme", start=0, end=4)
).mention_id)
print("ADDRESS", mint_occurrence_address(label="nmod:of", surface="acme"))
print("SCOPE", index.capture_ref, index.segment_ref, index.extractor_ref)
"""


def _run_in_a_child(root: Path, script: str) -> str:
    """Run ``script`` in a fresh interpreter whose import path is ``root`` and nothing else.

    The discipline both mutation tests and the replay test share, and it is the reason this is a
    helper rather than four copies of ``subprocess.run``: the repository is never written to. The
    copy is on a temporary path and the import path is set per child, so a mutated module cannot
    be imported by accident by anything else in the run.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    done = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout


def _replay_in_a_child(root: Path) -> str:
    return _run_in_a_child(root, _REPLAY_SCRIPT)


def _sibling_root() -> Path:
    """A flat copy of the two packages the index needs, on this file's own import path."""
    root = Path(tempfile.mkdtemp(prefix="mention-index-replay-"))
    for package in ("domain", "semantic"):
        shutil.copytree(
            SHARED / package, root / package, ignore=shutil.ignore_patterns("__pycache__")
        )
    return root


def test_replay_in_a_second_process_mints_identical_ids() -> None:
    """Domain Invariant 12, in a fresh interpreter, twice, and compared as strings.

    In-process determinism is weak evidence: both runs would share every module-level cache and
    every import, so a counter or a set's iteration order would be identical by construction. A
    child process shares none of that, and two children share only the source.

    The occurrence order is **reversed** in one of the two runs by a separate in-process
    assertion, so "identical ids" cannot be an artefact of one fixed insertion order: an index that
    hashed its way through a ``set`` would agree with itself here and disagree with a reader.
    """
    forwards = _index(_occurrence(*_ACME), _occurrence(*_MICROSOFT))
    backwards = _index(_occurrence(*_MICROSOFT), _occurrence(*_ACME))
    assert forwards.keys == backwards.keys
    assert [key.as_tuple() for key in forwards.keys] == [
        key.as_tuple() for key in backwards.keys
    ]

    root = _sibling_root()
    try:
        first = _replay_in_a_child(root)
        second = _replay_in_a_child(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert first == second, (first, second)
    # And the child's ids are the ones this process derives, which is the join working across
    # processes - not merely two children agreeing with each other.
    assert "MN-" in first
    expected = {
        forwards.mention_id_for(_occurrence(*_ACME)),
        forwards.mention_id_for(_occurrence(*_MICROSOFT)),
    }
    for mention_id in expected:
        assert mention_id in first, (mention_id, first)
    assert "CAP-1 SEG-1 deterministic-extractor-set" in first
    # The **address** is a fixed point too, and that is the same requirement one level down: a
    # label containing the separator is minted the same way in a fresh interpreter, or a
    # deferred address would not survive a round trip through a store.
    assert f"ADDRESS {_address('nmod:of', 'acme', None)}" in first, first


# --------------------------------------------------------------------------- #
# The mutation test: drop the capture key and the collision test must fail
# --------------------------------------------------------------------------- #

_MUTANT_SCRIPT = """
import sys
sys.path.insert(0, ".")
from domain.mention_occurrence_index import MentionOccurrence, MentionOccurrenceIndex

def ids(capture):
    index = MentionOccurrenceIndex(
        capture_ref=capture, segment_ref="SEG-1", extractor_ref="deterministic-extractor-set",
        occurrences=[MentionOccurrence(kind="org", surface="Acme", start=0, end=4)],
    )
    return index.mention_id_for(MentionOccurrence(kind="org", surface="Acme", start=0, end=4))

a, b = ids("CAP-1"), ids("CAP-2")
print("DISTINCT", a != b)
"""


def test_dropping_the_capture_key_collides_two_captures() -> None:
    """The capture key is load-bearing, demonstrated by removing it from the mint.

    The property is asserted in
    :func:`test_two_captures_of_one_segment_are_two_mentions`; this shows the assertion is not
    vacuous by rebuilding the module with the capture key out of
    :func:`domain.mention_occurrence_index.mint_mention_id`'s material and re-running the same
    question. The repository is never written to: the copy is on a temporary path and the import
    path is set per child, the same discipline :mod:`test_constitution_has_teeth` uses.
    """
    root = _sibling_root()
    target = (root / "domain" / "mention_occurrence_index.py").resolve()
    original = target.read_text(encoding="utf-8")
    anchor = 'return MENTION_ID_PREFIX + digest128(canonical_material(list(key.as_tuple())))'
    assert anchor in original, "the mint's single line moved; re-anchor this mutation"
    target.write_text(
        original.replace(
            anchor,
            "return MENTION_ID_PREFIX + digest128(canonical_material([\n"
            "        key.segment_ref,\n"
            "        list(key.span),\n"
            "        key.normalized_surface,\n"
            "        key.extractor_ref,\n"
            "    ]))",
            1,
        ),
        encoding="utf-8",
    )
    try:
        mutated = _run_in_a_child(root, _MUTANT_SCRIPT)
        unmutated = _run_in_a_child(SHARED, _MUTANT_SCRIPT)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert "DISTINCT True" in unmutated, unmutated
    assert "DISTINCT False" in mutated, (
        "dropping the capture key from the mint tuple did NOT collide the two captures, so "
        f"test_two_captures_of_one_segment_are_two_mentions is not guarding: {mutated!r}"
    )


#: Asks the two questions the address encoding has to answer, and prints what it found rather
#: than raising, so a mutated module produces a report instead of a traceback: which triples fail
#: to read back as themselves, and which distinct triples share one address.
_ADDRESS_MUTANT_SCRIPT = """
import sys
sys.path.insert(0, ".")
from domain.mention_occurrence_index import mint_occurrence_address, parse_deferred_address

CASES = [
    ("object", "Acme", (0, 4)),
    ("nmod:of", "acme", None),
    ("nmod", "of:acme", None),
    ("value", "a:b:c", (1, 6)),
    ("value", "jane@acme.example", (35, 52)),
    ("value", "a|b", None),
    ("value", "line one\\nline two", (0, 17)),
    ("value", "", (0, 0)),
    ("", "Acme", None),
]

def mint(label, surface, span):
    return mint_occurrence_address(
        label=label, surface=surface,
        start=None if span is None else span[0], end=None if span is None else span[1],
    )

round_trip_failures = 0
for label, surface, span in CASES:
    parsed = parse_deferred_address(mint(label, surface, span))
    if parsed is None or (parsed.label, parsed.surface, parsed.span) != (label, surface, span):
        round_trip_failures += 1
        print("ROUNDTRIP_FAIL", repr(label), repr(surface))

by_address = {}
collisions = 0
for label, surface, span in CASES:
    address = mint(label, surface, span)
    if address in by_address and by_address[address] != (label, surface, span):
        collisions += 1
        print("COLLISION", by_address[address], "==", (label, surface, span))
    by_address[address] = (label, surface, span)
print("ROUNDTRIP_FAILURES", round_trip_failures)
print("COLLISIONS", collisions)
"""


def test_dropping_the_self_delimiting_payload_brings_the_collision_back() -> None:
    """The injectivity property is not vacuous: remove the guard and the exact collision returns.

    :func:`test_the_address_encoding_is_injective_so_no_two_occurrences_share_one_string` and
    :func:`test_the_address_round_trips_over_every_adversarial_input` assert the property; this
    asserts that the assertions have teeth, by rebuilding the module with the payload built by
    joining the fields on ``:`` — the retired encoding's own idea of a payload — and re-running
    the same two questions in a child process against the **real** parser. Only the encoder is
    mutated, so what the child reports is the encoder's fault and not a consequence of having
    changed both halves at once.

    **The failure is reported on a colon-bearing surface, and that is the point.** With the
    payload joined on ``:``, ``("nmod:of", "acme")`` and ``("nmod", "of:acme")`` become the same
    payload, the same digest and the same address — the defect the whole change is about, and the
    one the platform actually had.
    """
    root = _sibling_root()
    target = (root / "domain" / "mention_occurrence_index.py").resolve()
    original = target.read_text(encoding="utf-8")
    anchor = """    payload = canonical_material(
        [
            str(label or ""),
            str(surface or ""),
            None if start is None else int(start),
            None if end is None else int(end),
        ]
    )"""
    assert anchor in original, "the encoder's payload line moved; re-anchor this mutation"
    target.write_text(
        original.replace(
            anchor,
            """    payload = ":".join(
        [
            str(label or ""),
            str(surface or ""),
            str(None if start is None else int(start)),
            str(None if end is None else int(end)),
        ]
    )""",
            1,
        ),
        encoding="utf-8",
    )
    try:
        mutated = _run_in_a_child(root, _ADDRESS_MUTANT_SCRIPT)
        unmutated = _run_in_a_child(SHARED, _ADDRESS_MUTANT_SCRIPT)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert "ROUNDTRIP_FAILURES 0" in unmutated, unmutated
    assert "COLLISIONS 0" in unmutated, unmutated
    assert "ROUNDTRIP_FAILURES 0" not in mutated, (
        "removing the self-delimiting payload did NOT break the round trip, so "
        "test_the_address_round_trips_over_every_adversarial_input is not guarding: "
        f"{mutated!r}"
    )
    assert "COLLISIONS 0" not in mutated, (
        "removing the self-delimiting payload did NOT collide two distinct occurrences, so "
        "test_the_address_encoding_is_injective_so_no_two_occurrences_share_one_string is not "
        f"guarding: {mutated!r}"
    )
    # Named, not merely counted: the collision has to be *the* one the platform had, on a
    # colon-bearing surface, or the mutation has proved something weaker than the defect.
    assert "COLLISION ('nmod:of', 'acme', None) == ('nmod', 'of:acme', None)" in mutated, mutated
    assert "ROUNDTRIP_FAIL" in mutated, mutated
