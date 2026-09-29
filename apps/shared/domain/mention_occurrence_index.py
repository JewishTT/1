"""``MentionOccurrenceIndex`` — the one thing that mints ``MN-…``, and the inverse it publishes.

Feature 021, brief §25 and §26, spec FR-016, FR-018, FR-019, FR-094; ``repair/ARBITRATION.md`` §8;
``data-model.md`` part 10.1.

**One name per thing, and this is the name.** ``ARBITRATION`` §8 fixes three: the pipeline **stage**
is ``MENTION_BINDING``, the **structure** is :class:`MentionOccurrenceIndex`, and the **id form** is
``MN-…``. ``MentionBinding`` is not a fourth object and this module does not introduce one.

**What the gap was, and it is not "a helper class".** Phase 4B moved the seven producers off
fabricated participant references and onto *deferred occurrence addresses* — then
``surface@<start>-<end>:<label>:<surface>`` and now the form :func:`mint_occurrence_address` writes.
That was the right call: a
producer sits below mention
extraction, so a producer that minted a mention identity would be inventing a durable record id from
a string match, which is FR-019 and brief §25 in as many words. But the shape a producer mints and
the shape the rest of the platform needs are not the same shape, and nothing resolved between them:
every ``participant.mention_ref`` a producer emitted was a real address of an occurrence and no
mention index that could answer for it existed. FR-016's "a reference *into the mention index*" had
no mention index to point into. This is that index.

**Why here, and the inversion it avoids.** The only existing ``MN-`` minter is
``semantic_path.execution.mention_id_for``, and that module imports :mod:`extractors.registry` and
:mod:`graph.relation_store` — it is the composition root, wired to ``apps/interpretation`` and
``apps/projection``. A producer importing it would take the edge producer → composition root, which
is the inversion the whole layering exists to prevent, and would drag the graph package into the
extraction layer. :mod:`domain` is the one place both can reach: ``apps/interpretation`` depends on
``apps/shared`` and so does ``apps/control-plane``, so ``domain`` sits strictly below both and
importing it from either adds no edge. That is the whole argument, and it is a dependency-graph
argument rather than an aesthetic one.

**The five keys, and the fourth one is the one people forget.** FR-018 names the lookup: *capture,
segment, offset/span, normalized surface, extractor occurrence* — five keys, and
:meth:`MentionOccurrenceKey.as_tuple` returns exactly those five and the mint is a function of that
tuple and nothing else.

* **capture** is first because its absence is a **collision bug**, not a simplification. A capture
  is a *retrieval* and a segment is a *document region*: one segment legitimately exists in two
  captures (the same page fetched twice, a crawl replay, a re-index), and a mint tuple without the
  capture addresses both to **one** mention id. Then "which fetch saw this mention" is unanswerable,
  the two captures' observations corroborate each other through a shared id, and FR-034's
  independence count silently doubles. An earlier design of this id had exactly that gap.
* **segment** — offsets with no segment are unresolvable, the same reason
  :class:`domain.relation_candidate.SpanRef` refuses a blank ``segment_ref``.
* **offset/span** — one key carrying two offsets, and a *position* rather than a length: two
  occurrences of ``Acme`` in one segment are two mentions.
* **normalized surface** — through
  :func:`domain.predicate_signature.normalize_surface_for_fingerprint` and **not** a second
  normaliser written here. That function is N1 + N2 (NFKC, casefold,
  whitespace collapse, edge punctuation stripped) and it already carries a docstring saying it
  "makes no judgement about what the form *means*". A second normalisation here would be a second
  answer to the same question, and the two would drift into disagreeing about what one mention is.
* **extractor occurrence** — how the surface was read is part of what was read, so the same
  surface at the same position read by two instruments is two mentions. Without it two extractors
  corroborate nothing because they are citing one id.

**What is deliberately **not** a key.** ``kind`` — the producer's own classification of the
occurrence. It is evidence, not identity, and two readings of one occurrence that disagree about
their kind are a *disagreement*, not two mentions; so it is checked at
:meth:`MentionOccurrenceIndex.bind`
and **refused** with ``mention_kind_disagreement`` rather than folded into the address. The
producer's ``label`` is the same case and is not even checked: it names which group of a cue
pattern matched, which is a fact about the pattern rather than about the mention. A *surface*
disagreement is the mirror image — it changes the key, so it never collides, and it is checked on
the offsets instead so two readers who disagree about what the document says at one position are
refused rather than recorded as two mentions of one position.

**The address grammar, and why it is a content address rather than a format.** Phase 4B's grammar
was ``surface[:@<start>-<end>:]<label>:<surface>`` with ``:`` as the field separator and the label
defined as the text up to the *first* separator. That is not a subtle edge: a syntactic
producer's labels are dependency arcs and several of them contain the separator (``nmod:of``,
``nsubj:pass``), so it minted ``surface:nmod:of:acme`` and the grammar read that back as label
``nmod`` and surface ``of:acme`` — **two distinct addresses sharing one string**. The platform
could not tell that misparse from a surface that genuinely contains a colon, and every fix that
leaves the shape alone (ban the character, pick a rarer separator, restrict labels) also refuses
text the document really contains. So :func:`mint_occurrence_address` writes the fields as the
platform's own :func:`domain.relation_identity.canonical_material` and prefixes the result with
its own :func:`domain.relation_identity.digest128`: the payload is self-delimiting, the address is
content-addressed, and the parser *verifies* rather than interprets. The old form is not decoded
under any circumstances — see :data:`DEFERRED_ADDRESS_VERSION`.

**Determinism is structural (constitution Domain Invariant 12).** No ``uuid4``, no clock, no
set-order iteration: the mint is a digest over a five-element tuple, the address is a digest over
its own material, the index iterates ``sorted`` keys, and :func:`mint_mention_id` is pure. Two
processes handed the same occurrences mint the same ids, in either order, which is what makes a
mention id usable as a join key at all.

**The published inverse, and why it is ``| None`` rather than a raise.**
:meth:`MentionOccurrenceIndex.read_occurrence` answers "what mention is this address?" and
``None`` means *no occurrence in this index is that address* — one answer covering all the ways it
can fail, because a caller that is asking usually has three cases to separate and does not yet know
which it is in. :meth:`MentionOccurrenceIndex.require_occurrence` is the fail-closed front door: it
separates them into named codes, because "the address did not resolve" and "the address
is ambiguous"
and "that is a capture, not a mention" are three different bugs for an operator and one message
would hide two of them.

**Where this stops.** A mention is not an entity. Resolving one to another is
coreference, it belongs
to :mod:`semantic.resolution` and it has a ``ResolutionDecisionRecord`` behind it. This module never
emits an ``ENT-`` or ``RES-`` literal and never accepts one (FR-019), and a mention it mints grants
no authority over the referent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from domain.predicate_signature import normalize_surface_for_fingerprint
from domain.relation_identity import canonical_material, digest128

#: The id form ``ARBITRATION`` §8 fixes, and the only prefix this module's ids carry. FR-019
#: reserves it to the mention layer, which is why :mod:`extractors.signals.mentions` mints
#: ``surface:``/``capture:`` deferred addresses and never one of these.
MENTION_ID_PREFIX = "MN-"

#: The deferred-occurrence namespace, and the platform's own. The **grammar** lives here rather
#: than beside the producer that mints it because two things have to agree about it forever: the
#: producer that writes the address and the index that reads it back. A grammar with two homes is
#: a grammar that drifts, and the drift is silent — the addresses keep their shape and stop
#: resolving. :mod:`extractors.signals.mentions` mints against these two constants and delegates
#: its parse to :func:`parse_deferred_address`, so the producer-side contract keeps its name,
#: its location and its refusals while there is exactly one definition of the form.
DEFERRED_OCCURRENCE_PREFIX = "surface"

#: The capture namespace, for the one end that is a retrieval rather than an occurrence: the
#: document a ``<meta>`` tag or a byline belongs to. A capture id is a real, content-addressed
#: durable id (:class:`domain.capture.Capture`), so this end is *already* resolvable and needs no
#: mention at all — see :meth:`MentionOccurrenceIndex.require_occurrence` for why asking this index
#: about one is refused rather than answered.
DEFERRED_CAPTURE_PREFIX = "capture"

#: Which encoding of the occurrence address this module writes and reads, and the only one it
#: reads. **Present because the encoding changed, and the change is not backward compatible.**
#: The retired form was ``surface[:@<start>-<end>:]<label>:<surface>`` with ``:`` as the field
#: separator and the label defined as the text up to the *first* separator — so a dependency-arc
#: label that itself contains one (``nmod:of``, ``nsubj:pass``) minted
#: ``surface:nmod:of:acme``, which the grammar read back as label ``nmod`` and surface
#: ``of:acme``. Two distinct addresses, one string: a non-injective encoding, and the platform
#: could not tell that misparse from a surface that genuinely contains a colon. Fixing it by
#: banning colons in surfaces, or by picking a "less likely" separator, or by restricting what a
#: label may be, would each leave the *defect class* in place — two inputs, one output — while
#: also refusing text the document really contains. So the class is removed instead, and the
#: version token is what makes the old strings fail **loudly**: they are not addresses any more,
#: they are refused with ``mention_address_unreadable`` rather than decoded into the wrong pair.
DEFERRED_ADDRESS_VERSION = "1"

#: The number of hex characters :func:`domain.relation_identity.digest128` returns, and therefore
#: the width of the one fixed-shape component in the address. It is load-bearing: the digest is
#: read by *position*, not by scanning for a separator, so nothing in the payload can be mistaken
#: for it however many separators the payload itself contains.
_DIGEST_HEX_CHARS = 32

#: The arity of the address payload, declared as a number so the claim "the payload is exactly the
#: label, the surface and the two offsets" is checkable against something rather than being an
#: index into a list. A field added to the mint and forgotten here would be read back as ``None``
#: at best and as the wrong occurrence at worst, which is the collision this module exists to
#: make impossible.
_ADDRESS_FIELD_COUNT = 4

#: The stable shape of the mint tuple, as the number of keys rather than their names. Declared so
#: the "five keys FR-018 names" claim is checkable against something: a sixth key added for
#: convenience is a collision, and a key dropped is a collision the other way.
MENTION_OCCURRENCE_KEY_COUNT = 5


class MentionBindingError(ValueError):
    """A deferred address cannot be bound to a mention, or a binding is incoherent.

    A ``ValueError`` carrying the stable snake_case ``code`` the extraction layer reports, in the
    same family as :class:`domain.relation_candidate.CandidateContractError` and
    :class:`extractors.signals.signal.SignalContractError`, so one caller can switch on any of them
    by ``.code`` rather than by type.

    Every refusal here is **fail-closed** (constitution IV): the alternative to a named refusal is
    an id that looks durable and resolves against nothing, and a record nobody can trace is worse
    than a record that was refused.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


# --------------------------------------------------------------------------- #
# The address grammar
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DeferredOccurrenceAddress:
    """One occurrence, read: the label whole, the surface whole, and the span or ``None``.

    Every field is **the whole** of what the producer saw, because there is no separator left to
    split at: :func:`mint_occurrence_address` writes the fields as the platform's own
    :func:`domain.relation_identity.canonical_material`, which is self-delimiting, and this is
    what reads them back. A label of ``nmod:of`` and a surface of ``a:b:c`` arrive as themselves.

    :attr:`span` is ``None`` for the unpositioned form, which is not a defect: a syntactic
    producer's positions are clause-relative token indices rather than character offsets in a
    segment, so it has no character span to state. What it costs is stated on
    :meth:`MentionOccurrenceIndex.read_occurrence`: an unpositioned address resolves only when it
    names exactly one registered occurrence, and is refused as ambiguous when it names several.
    """

    label: str
    surface: str
    span: tuple[int, int] | None

    @property
    def positioned(self) -> bool:
        return self.span is not None


@dataclass(frozen=True, slots=True)
class DeferredCaptureAddress:
    """``capture:<ref>`` — the retrieval a document-scoped observation belongs to."""

    capture_ref: str


def mint_capture_address(capture_ref: str) -> str:
    """The one way a ``capture:`` address is written.

    Not versioned, and the reason is that this end never had the defect: there is exactly one
    field and it is **the whole remainder**, so this encoding is injective by construction for any
    input at all. The occurrence end has four fields, which is why it needed a form whose field
    boundaries are stated rather than found.
    """
    return f"{DEFERRED_CAPTURE_PREFIX}:{str(capture_ref or '').strip()}"


def mint_occurrence_address(
    *,
    label: str,
    surface: str,
    start: int | None = None,
    end: int | None = None,
) -> str:
    """The one way an occurrence address is written, and it is **injective by construction**.

    ::

        surface@<start>-<end>:<version>:<digest>:<material>     # positioned
        surface:<version>:<digest>:<material>                   # unpositioned

    where ``material`` is ``canonical_material([label, surface, start, end])`` — the platform's own
    serialisation, not a new convention invented here — and ``digest`` is
    :func:`domain.relation_identity.digest128` of exactly that string.

    **Why this shape and not a cheaper one.** Three rules, in the order they matter.

    * **The payload is the platform's canonical material, so it is self-delimiting.** JSON renders
      a list with quoted, escaped strings and bare integers and nulls, and the element boundaries
      are *structural* rather than found. A label of ``nmod:of``, a surface of ``a:b:c``, a
      surface holding a newline, a tab, a ``|``, an ``@``, a non-ASCII letter, the empty string, or
      the literal text of a JSON array all survive verbatim and read back as themselves. This is
      the answer to the collision the retired form had: the payload contains no separator to
      collide with, because it does not use separators.
    * **The digest is the content address, and the substrate is content-addressed.** ``MN-`` ids
      are ``digest128(canonical_material(...))`` and an entity is ``digest128`` of its own
      material, so an occurrence address — a fact about a document position — is addressed the same
      way rather than by a format whose shape has to be agreed. It also makes the parser
      **verify** rather than interpret: a string this function did not write fails its own digest
      and is refused, so a truncated store value, a hand-edited record, or a corpus written under
      the retired grammar is a named refusal and never a decode into a different pair.
    * **The version token is what makes the retired grammar fail loudly.** Without it the digest
      slot would be the only discriminator, which works but tells an operator holding a pre-change
      corpus nothing. With it, ``surface:nmod:of:acme`` is ``mention_address_unreadable`` and the
      message names the form it replaced.

    **The position still comes first, and still for the same reason as before** — these
    producers' surfaces are URLs, email addresses and ``@``-handles, so the span is a fixed-shape
    leading component and no reader ever has to ask which ``@`` is the separator. That argument
    used to rest on the surface being "the whole remainder"; it now rests on the surface being
    self-delimiting, which is the stronger of the two.

    **Total, and deliberately so.** This formats and never refuses: the producer-side contract
    :func:`extractors.signals.mentions.deferred_occurrence` owns the named refusals
    (``participant_label_required``, ``participant_surface_required``,
    ``participant_occurrence_span_invalid``) and keeps their names and codes, and
    :func:`parse_deferred_address` is the fail-closed door that refuses anything the contract would
    not have minted — the two halves of one rule, in the shape every other contract here has. The
    one asymmetry the parser has to know about is a half-stated span: it is written as an
    unpositioned address carrying one offset, and refused as unreadable rather than read as either
    a positioned or an unpositioned one, because choosing between them would be guessing.

    Pure: no clock, no randomness, no iteration, and the digest is over the material rather than
    over a joined string, so no two different triples can share one payload (constitution VI,
    Domain Invariant 12).
    """
    payload = canonical_material(
        [
            str(label or ""),
            str(surface or ""),
            None if start is None else int(start),
            None if end is None else int(end),
        ]
    )
    framed = f"{DEFERRED_ADDRESS_VERSION}:{digest128(payload)}:{payload}"
    if start is None or end is None:
        return f"{DEFERRED_OCCURRENCE_PREFIX}:{framed}"
    return f"{DEFERRED_OCCURRENCE_PREFIX}@{int(start)}-{int(end)}:{framed}"


def parse_deferred_address(
    address: str,
) -> DeferredOccurrenceAddress | DeferredCaptureAddress | None:
    """The published inverse of the deferred-occurrence grammar, or ``None`` if it is not one.

    ``None`` rather than a raise, and for the same reason :meth:`MentionOccurrenceIndex.
    read_occurrence` returns ``None``: the caller asking has not yet established *which* way this
    string fails, and a parser that picks a failure mode for it is guessing. Everything that
    cannot parse is unreadable, which is exactly one answer.

    **Every component is read by position or by fixed width, never by scanning for a separator.**
    The prefix is literal, the span is ``<ascii digits>-<ascii digits>``, the version is the
    literal :data:`DEFERRED_ADDRESS_VERSION`, the digest is exactly :data:`_DIGEST_HEX_CHARS`
    characters, and the payload is the whole remainder. So the parse succeeds on exactly the
    strings :func:`mint_occurrence_address` writes, which is the whole of what "injective by
    construction" has to mean here.

    **It verifies, and that is the fail-closed part.** The digest is recomputed over the payload
    and compared, and the span stated in the prefix must be the span in the payload. A mismatch is
    ``None``, never a best reading: the alternative to refusing is an address naming a different
    occurrence from the one it was written for, which is a durable record of a misparse.

    **A blank label and a blank surface decode, and that is not a hole.** The retired grammar could
    not tell them from a *missing* field — ``surface::Acme`` was an empty label, ``surface:obj:``
    was an empty surface, and both were refused here as a string because the type that owns the
    rule could not see them. The payload states all four fields whether or not they are blank, so
    the blank is a **value** now, and it is refused where the rule lives rather than by a parser
    guessing: :func:`extractors.signals.mentions.deferred_occurrence` refuses to mint one with
    ``participant_label_required`` / ``participant_surface_required`` (FR-017), and
    :class:`MentionOccurrenceKey` refuses the same pair with
    ``mention_occurrence_surface_required``. Nothing here needs to second-guess a string it can now
    read exactly.

    **The retired grammar is unreadable, not misread.** ``surface:nmod:of:acme``,
    ``surface@0-4:object:Acme`` and every other address written before
    :data:`DEFERRED_ADDRESS_VERSION` fail at the version component and come back ``None``, so a
    corpus or a store written under the old form is refused by name instead of decoding into a
    label and a surface its writer never meant. Nothing here attempts to read them.
    """
    text = str(address or "")
    capture_prefix = f"{DEFERRED_CAPTURE_PREFIX}:"
    if text.startswith(capture_prefix):
        capture_ref = text[len(capture_prefix) :]
        return DeferredCaptureAddress(capture_ref) if capture_ref.strip() else None
    positioned_prefix = f"{DEFERRED_OCCURRENCE_PREFIX}@"
    plain_prefix = f"{DEFERRED_OCCURRENCE_PREFIX}:"
    declared: tuple[int, int] | None
    if text.startswith(positioned_prefix):
        span_text, separator, body = text[len(positioned_prefix) :].partition(":")
        if not separator:
            return None
        start_text, dash, end_text = span_text.partition("-")
        # ASCII digits, in canonical form. ``int`` alone would accept ``"1_0"``, ``"+4"`` and
        # ``" 7 "``, and each of those is a second string for the pair the first one addresses;
        # the form *is* the address, so the form is canonical.
        if not dash or not start_text.isascii() or not end_text.isascii():
            return None
        if not start_text.isdigit() or not end_text.isdigit():
            return None
        start, end = int(start_text), int(end_text)
        if str(start) != start_text or str(end) != end_text or start < 0 or end < start:
            return None
        declared = (start, end)
    elif text.startswith(plain_prefix):
        declared = None
        body = text[len(plain_prefix) :]
    else:
        return None
    version, separator, body = body.partition(":")
    if not separator or version != DEFERRED_ADDRESS_VERSION:
        return None
    digest, separator, payload = body.partition(":")
    if not separator or len(digest) != _DIGEST_HEX_CHARS or digest128(payload) != digest:
        return None
    try:
        material = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(material, list) or len(material) != _ADDRESS_FIELD_COUNT:
        return None
    label, surface, start, end = material
    if not isinstance(label, str) or not isinstance(surface, str):
        return None
    if start is None and end is None:
        span = None
    elif type(start) is int and type(end) is int and 0 <= start <= end:
        span = (start, end)
    else:
        return None
    if span != declared:
        return None
    return DeferredOccurrenceAddress(label, surface, span)


# --------------------------------------------------------------------------- #
# The key, the occurrence, the answer
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True, order=True)
class MentionOccurrenceKey:
    """The five keys FR-018 names, and nothing else.

    ``span`` is **one** key carrying two offsets rather than two keys, so
    :attr:`as_tuple` is five elements wide and the "five keys" claim in the spec is arithmetically
    true rather than a matter of reading. The normalisation happens in :meth:`of` and nowhere else,
    so a key cannot be built with a raw surface and then compared against a normalised one.

    ``order=True`` because the declaration order **is** :attr:`as_tuple`'s order and the index
    iterates sorted keys: an order derived from a hash rather than from the fields is the one
    dependency this module must not have (constitution VI).
    """

    capture_ref: str
    segment_ref: str
    span: tuple[int, int]
    normalized_surface: str
    extractor_ref: str

    def __post_init__(self) -> None:
        for name in ("capture_ref", "segment_ref", "extractor_ref"):
            if not str(getattr(self, name)).strip():
                raise MentionBindingError(
                    "mention_occurrence_key_incomplete",
                    f"{name} is part of the mint tuple and cannot be blank. capture_ref in "
                    "particular is not a convenience: without it two captures of one segment "
                    "address to one mention id, and the platform can no longer say which "
                    "retrieval saw the mention (FR-018)",
                )
        if not self.normalized_surface:
            raise MentionBindingError(
                "mention_occurrence_surface_required",
                "an occurrence with no surface text addresses a position and nothing else; "
                "'the extractor found no words here' is a finding to report, not a mention to "
                "mint (FR-017)",
            )
        if self.span[1] < self.span[0]:
            raise MentionBindingError(
                "mention_occurrence_span_invalid",
                f"end {self.span[1]} precedes start {self.span[0]}; a span read backwards is a "
                "position that cannot be looked up",
            )

    @classmethod
    def of(
        cls,
        *,
        capture_ref: str,
        segment_ref: str,
        start: int,
        end: int,
        surface: str,
        extractor_ref: str,
    ) -> MentionOccurrenceKey:
        """The key for one occurrence, normalising the surface once through the shared rule."""
        return cls(
            capture_ref=str(capture_ref or "").strip(),
            segment_ref=str(segment_ref or "").strip(),
            span=(int(start), int(end)),
            normalized_surface=normalize_surface_for_fingerprint(surface),
            extractor_ref=str(extractor_ref or "").strip(),
        )

    def as_tuple(self) -> tuple[str, str, tuple[int, int], str, str]:
        """The mint tuple, in the order :data:`MENTION_OCCURRENCE_KEY_COUNT` promises.

        This is the *only* thing :func:`mint_mention_id` digests, and it is returned in one place so
        the order is declared rather than assembled at each call site.
        """
        return (
            self.capture_ref,
            self.segment_ref,
            self.span,
            self.normalized_surface,
            self.extractor_ref,
        )


@dataclass(frozen=True, slots=True)
class MentionOccurrence:
    """One occurrence of a surface, read by one instrument at one position in one capture.

    ``capture_ref`` / ``segment_ref`` / ``extractor_ref`` are **not** here: they are the index's
    scope, and repeating them on every record is how a table of occurrences and an index of
    occurrences become two truths.
    """

    kind: str
    surface: str
    start: int
    end: int

    def key(self, index: MentionOccurrenceIndex) -> MentionOccurrenceKey:
        """This occurrence's mint key **in that index's scope** — the scope supplies three keys."""
        return MentionOccurrenceKey.of(
            capture_ref=index.capture_ref,
            segment_ref=index.segment_ref,
            start=self.start,
            end=self.end,
            surface=self.surface,
            extractor_ref=index.extractor_ref,
        )


@dataclass(frozen=True, slots=True)
class ResolvedMention:
    """What a deferred address resolved to: the id, the key it was minted from, and the record.

    All three, because the other two are what a reader needs when the resolution is *wrong*: the id
    alone cannot be recomputed (a caller has to re-derive the key to check it) and the record alone
    cannot be located (nothing says which mention id it became). :attr:`address` and
    :attr:`label` carry the input, so the round trip is legible from one value.
    """

    mention_id: str
    key: MentionOccurrenceKey
    occurrence: MentionOccurrence
    address: str = ""
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mention_id": self.mention_id,
            "address": self.address,
            "label": self.label,
            "key": list(self.key.as_tuple()),
            "occurrence": {
                "kind": self.occurrence.kind,
                "surface": self.occurrence.surface,
                "start": self.occurrence.start,
                "end": self.occurrence.end,
            },
        }


def mint_mention_id(key: MentionOccurrenceKey) -> str:
    """``MN-`` + 128-bit digest over the five keys. The only place a mention id is written.

    Through the same :func:`domain.relation_identity.digest128` /
    :func:`domain.relation_identity.canonical_material` pair every other content address on the
    platform uses, so an operator can recompute any ``MN-`` id from the record alone and a replay in
    a fresh process produces the same string. Idempotency falls out: one occurrence bound twice is
    one mention.
    """
    return MENTION_ID_PREFIX + digest128(canonical_material(list(key.as_tuple())))


def unbound_mention_id(material: str) -> str:
    """``MN-`` + digest over caller material, for a mention with **no addressable occurrence**.

    One exception to :func:`mint_mention_id`, and it is named rather than smuggled: a recorded
    corpus fixture cites a support mention that no occurrence backs, because the fixture is a
    constant and not an observation. It gets the same prefix and the same primitive so there is
    still one place that writes an ``MN-``, and it is deliberately **not** resolvable through
    :meth:`MentionOccurrenceIndex.read_occurrence` — asking would be asking for a binding that was
    never made, and answering it would be a lie about provenance.

    Nothing on the extraction path may call this. A producer binding its own address through this
    would be minting a mention identity from a string, which is FR-019 and the thing this whole
    module exists to make unnecessary.
    """
    return MENTION_ID_PREFIX + digest128(str(material))


# --------------------------------------------------------------------------- #
# The index
# --------------------------------------------------------------------------- #


class MentionOccurrenceIndex:
    """Occurrences of one segment of one capture, as read by one instrument, addressed.

    **Scoped, and the scope is three of the five keys.** An index is built for a
    ``(capture_ref, segment_ref, extractor_ref)`` triple and every key it mints is that triple plus
    an occurrence's span and normalised surface. So "one id per five-key tuple" is enforced by
    construction rather than by a check: a tuple that differs in any of the five is either in a
    different index or is a different occurrence, and there is no path by which two tuples in one
    index share an id.

    All three scope components are **required keyword-only** and none is defaulted, for the reason
    :class:`extractors.signals.protocol.ExtractionScope` requires a frame and a regime rather than
    defaulting them: each is somebody else's decision, and a default here would be a silent
    substitution of one retrieval, document or instrument for another. ``""`` is a legal *value*
    for an extractor that did not name itself and is refused as a *key*, so the scope cannot
    silently collapse.

    **Binding is a check, not an insert.** :meth:`bind` refuses an occurrence that contradicts one
    already in the index — a different ``kind`` at the same five keys, or a different surface at the
    same *offsets* — because both mean the two records disagree about what the document says, and
    the only way to "resolve" that is to pick one, which is the arbiter's decision and not this
    module's. The second check is on the offsets rather than on the key on purpose: two surfaces at
    the same offsets mint two *different* ids rather than colliding, which is right for the address
    and wrong to leave silent.

    **Iteration is over sorted keys.** Every accessor that returns more than one value returns
    them in :attr:`keys` order, so no caller can make an id depend on insertion order or on a set's
    hash order (constitution VI and Domain Invariant 12).
    """

    __slots__ = ("_capture_ref", "_segment_ref", "_extractor_ref", "_occurrences", "_spans")

    def __init__(
        self,
        *,
        capture_ref: str,
        segment_ref: str,
        extractor_ref: str,
        occurrences: Iterable[MentionOccurrence] = (),
    ) -> None:
        for name, value in (
            ("capture_ref", capture_ref),
            ("segment_ref", segment_ref),
            ("extractor_ref", extractor_ref),
        ):
            if not str(value).strip():
                raise MentionBindingError(
                    "mention_index_scope_required",
                    f"{name} is required and cannot be defaulted: the index's scope is three of "
                    "the five keys a mention id is minted from, and defaulting one would mint "
                    "addresses that cannot say which retrieval, which document or which "
                    "instrument produced them (FR-018)",
                )
        self._capture_ref = str(capture_ref).strip()
        self._segment_ref = str(segment_ref).strip()
        self._extractor_ref = str(extractor_ref).strip()
        index = self
        registered: dict[MentionOccurrenceKey, MentionOccurrence] = {}
        spans: dict[tuple[int, int], MentionOccurrence] = {}
        for occurrence in occurrences:
            _check_span(index, spans, occurrence)
            key = occurrence.key(index)
            _check_kind(registered, key, occurrence)
            registered[key] = occurrence
        # A plain dict, re-sorted on every read, rather than a read-only mapping: :meth:`bind`
        # has to be able to add, and ``sorted()`` on each accessor is what keeps the iteration
        # order a property of the keys instead of of the insertion sequence. Every accessor
        # therefore hands out a copy, so no caller can reach the dict and reorder it.
        self._occurrences: dict[MentionOccurrenceKey, MentionOccurrence] = registered
        self._spans = spans

    # -- scope ------------------------------------------------------------- #

    @property
    def capture_ref(self) -> str:
        return self._capture_ref

    @property
    def segment_ref(self) -> str:
        return self._segment_ref

    @property
    def extractor_ref(self) -> str:
        return self._extractor_ref

    # -- contents ---------------------------------------------------------- #

    def __len__(self) -> int:
        return len(self._occurrences)

    def __iter__(self) -> Iterator[MentionOccurrenceKey]:
        return iter(self.keys)

    def __contains__(self, key: object) -> bool:
        return key in self._occurrences

    @property
    def keys(self) -> tuple[MentionOccurrenceKey, ...]:
        """Every mint key in the index, in :attr:`MentionOccurrenceKey.as_tuple` order."""
        return tuple(sorted(self._occurrences))

    @property
    def occurrences(self) -> tuple[MentionOccurrence, ...]:
        """Every registered occurrence, in key order — the same order as :attr:`keys`."""
        return tuple(self._occurrences[key] for key in self.keys)

    def by_key(self) -> MappingProxyType:
        """The whole table as a read-only mapping, in key order — for a caller that wants it all.

        A snapshot rather than a view: :meth:`bind` can extend the index after this returns, and a
        caller holding a live view would see an order that changed underneath it.
        """
        return MappingProxyType(dict(sorted(self._occurrences.items())))

    def key_for(self, occurrence: MentionOccurrence) -> MentionOccurrenceKey:
        """The mint key this index would give ``occurrence``, without binding it."""
        if not isinstance(occurrence, MentionOccurrence):
            raise MentionBindingError(
                "invalid_mention_occurrence",
                "key_for takes a domain.mention_occurrence_index.MentionOccurrence, got "
                f"{type(occurrence).__name__}",
            )
        return occurrence.key(self)

    def mention_id_for(self, occurrence: MentionOccurrence) -> str:
        """The id this occurrence *would* get, minted without registering anything.

        Pure and order-independent, which is what makes a caller able to check an id it was handed
        against the record it was handed with.
        """
        return mint_mention_id(self.key_for(occurrence))

    def bind(self, occurrence: MentionOccurrence) -> ResolvedMention:
        """Register ``occurrence`` and return the mention it addresses.

        Idempotent: binding the same occurrence twice returns the same
        :class:`ResolvedMention`. Refuses an occurrence that contradicts one already registered —
        see the class docstring for why that is a refusal and not a merge.
        """
        _check_span(self, self._spans, occurrence)
        key = self.key_for(occurrence)
        _check_kind(self._occurrences, key, occurrence)
        self._occurrences[key] = occurrence
        return ResolvedMention(mint_mention_id(key), key, occurrence)

    def extend(self, occurrences: Iterable[MentionOccurrence]) -> tuple[ResolvedMention, ...]:
        """:meth:`bind` over several, returned in the order given and in key order respectively.

        The two orders are pinned separately: bindings follow the caller so a caller can zip them
        against whatever it passed in, and the index itself is sorted, so the *ids* do not depend
        on the order the occurrences arrived in.
        """
        return tuple(self.bind(occurrence) for occurrence in occurrences)

    # -- the published inverse --------------------------------------------- #

    def read_occurrence(self, address: str) -> ResolvedMention | None:
        """The mention this deferred address names, or ``None`` if it names none here.

        **The published inverse** of the address grammar, and the seam the whole module exists to
        provide: a producer's deferred occurrence address resolves to a real ``MN-``
        or it does not resolve at all, and it is never silently accepted unresolved.

        * A **positioned** address is looked up by all five keys at once. The scope supplies three
          and the address supplies the other two, so the lookup is exact and a miss is a miss.
        * An **unpositioned** address has no span to look up with, so it is matched on normalised
          surface within the scope. One match resolves. **No match, or more than one, returns
          ``None``** — and more than one is not resolved *because choosing among them would be
          inventing a position the producer never stated*. :meth:`require_occurrence` separates
          that case from the others and refuses it by name.
        * A ``capture:`` address returns ``None`` too, and for a structural reason rather than a
          lookup failure: a capture is a **fetch event**, not a mention, and this index answers
          questions about mentions. See :meth:`require_occurrence`.

        Pure, and over a fixed set, so two processes holding the same index answer the same way.
        """
        parsed = parse_deferred_address(address)
        if not isinstance(parsed, DeferredOccurrenceAddress):
            return None
        normalized = normalize_surface_for_fingerprint(parsed.surface)
        if parsed.positioned:
            key = MentionOccurrenceKey.of(
                capture_ref=self._capture_ref,
                segment_ref=self._segment_ref,
                start=parsed.span[0],
                end=parsed.span[1],
                surface=parsed.surface,
                extractor_ref=self._extractor_ref,
            )
            occurrence = self._occurrences.get(key)
            if occurrence is None:
                return None
            return ResolvedMention(
                mint_mention_id(key), key, occurrence, str(address), parsed.label
            )
        matches = [
            (key, occurrence)
            for key, occurrence in sorted(self._occurrences.items())
            if key.normalized_surface == normalized
        ]
        if len(matches) != 1:
            return None
        key, occurrence = matches[0]
        return ResolvedMention(mint_mention_id(key), key, occurrence, str(address), parsed.label)

    def require_occurrence(self, address: str) -> ResolvedMention:
        """:meth:`read_occurrence` as a fail-closed front door, with a named code per failure.

        The four refusals, and each names a different operator's bug:

        ``mention_address_unreadable``
            the string is not a deferred occurrence address at all — or it is one in the
            **retired** grammar, which is refused rather than misread. The message names the
            current form and the retired one, because the second is the one an operator with a
            stored corpus will actually be holding;
        ``mention_capture_is_not_a_mention``
            it is a ``capture:`` end — a real ``CAP-`` id, already addressable, and a *fetch event*
            rather than an occurrence, so it must not be given a mention. The stop condition is
            stated in the message: use the capture ref as it stands;
        ``mention_occurrence_unresolved``
            the address is well formed and names nothing this index holds;
        ``mention_occurrence_ambiguous``
            an unpositioned address names several occurrences. Resolving it would mean picking a
            position the producer never stated, so it is refused.
        """
        parsed = parse_deferred_address(address)
        if parsed is None:
            raise MentionBindingError(
                "mention_address_unreadable",
                f"{address!r} is not a deferred occurrence address in version "
                f"{DEFERRED_ADDRESS_VERSION!r}. A readable one is "
                f"{DEFERRED_OCCURRENCE_PREFIX}@<start>-<end>:{DEFERRED_ADDRESS_VERSION}:<digest>:"
                "<material> (positioned) or "
                f"{DEFERRED_OCCURRENCE_PREFIX}:{DEFERRED_ADDRESS_VERSION}:<digest>:<material> "
                "(unpositioned), where <material> is the label, the surface and the offsets as "
                "one canonical list, and the digest is that material's own content address. The "
                "form this replaced - "
                f"{DEFERRED_OCCURRENCE_PREFIX}[:@<start>-<end>:]<label>:<surface> - split the "
                "label at the first ':' and could not read a label that contained one, so a "
                "corpus written under it is refused here rather than decoded into a label and a "
                "surface its writer never meant. STOP: re-mint the address with "
                "extractors.signals.mentions.deferred_occurrence (or domain's own "
                "mint_occurrence_address); do not hand-edit one, and do not guess at a reading",
            )
        if isinstance(parsed, DeferredCaptureAddress):
            raise MentionBindingError(
                "mention_capture_is_not_a_mention",
                f"{address!r} addresses the retrieval {parsed.capture_ref!r}. A capture is a "
                "record of an act of retrieval, not an occurrence in a segment, so there is no "
                "mention to mint and this index must not invent one (I-2, domain/capture.py). "
                "STOP: use the capture ref as it stands - it is a real content-addressed id and "
                "needs no binding; do not mint an MN- for a document end",
            )
        resolved = self.read_occurrence(address)
        if resolved is not None:
            return resolved
        if not parsed.positioned:
            surface = normalize_surface_for_fingerprint(parsed.surface)
            occurrences = sorted(
                key for key in self._occurrences if key.normalized_surface == surface
            )
            if len(occurrences) > 1:
                raise MentionBindingError(
                    "mention_occurrence_ambiguous",
                    f"{address!r} names the surface {surface!r} with no position, and "
                    f"{len(occurrences)} occurrences in {self._segment_ref} of "
                    f"{self._capture_ref} read as that by {self._extractor_ref}: "
                    f"{[list(key.as_tuple()) for key in occurrences]}. Resolving it would mean "
                    "picking a position the producer never stated. STOP: have the producer "
                    "address the occurrence positionally (deferred_occurrence(..., start=, "
                    "end=)), or narrow the index's scope; do not take the first match",
                )
        raise MentionBindingError(
            "mention_occurrence_unresolved",
            f"{address!r} names surface {parsed.surface!r} at span {parsed.span} in segment "
            f"{self._segment_ref!r} of capture {self._capture_ref!r} as read by "
            f"{self._extractor_ref!r}, and this index holds "
            f"{len(self._occurrences)} occurrence(s), none of them that one. A producer "
            "addressing an occurrence the mention layer did not find has to be refused, not "
            "bound to whatever was nearest. STOP: register the occurrence, or accept the "
            "deferred address unresolved and resolve it in a layer that records the decision",
        )

    def read_capture(self, address: str) -> str | None:
        """The capture ref a ``capture:`` address names, or ``None`` for any other address.

        The retrieval end's own inverse, because a capture address needs no mention and refusing
        it outright (:meth:`require_occurrence`) would leave a caller with no way to read the one
        end that is already a durable id. A ``surface:`` address returns ``None`` here rather than
        raising: this method answers about captures and nothing else.
        """
        parsed = parse_deferred_address(address)
        if isinstance(parsed, DeferredCaptureAddress):
            return parsed.capture_ref
        return None

    def to_dict(self) -> dict[str, Any]:
        ordered = self.keys
        return {
            "capture_ref": self._capture_ref,
            "segment_ref": self._segment_ref,
            "extractor_ref": self._extractor_ref,
            "keys": [list(key.as_tuple()) for key in ordered],
            "mention_ids": [mint_mention_id(key) for key in ordered],
        }


def _check_span(
    index: MentionOccurrenceIndex,
    spans: dict[tuple[int, int], MentionOccurrence],
    candidate: MentionOccurrence,
) -> None:
    """Refuse two occurrences claiming the **same offsets** with different surfaces.

    The scope supplies three of the five keys, so within one index the offsets plus the surface
    decide the key entirely — and a different surface at the same offsets therefore mints a
    *different* id rather than colliding. That is the right thing for the address and the wrong
    thing to leave silent: the two records disagree about what the document says at one position,
    and two ids for it is exactly how a reader ends up with a duplicated segment nobody noticed.

    So the check is on the offsets, not on the key. Neither is merged: :func:`unbound_mention_id`'s
    exception is for a corpus constant, not for a live contradiction.
    """
    if not isinstance(candidate, MentionOccurrence):
        raise MentionBindingError(
            "invalid_mention_occurrence",
            "occurrences must hold domain.mention_occurrence_index.MentionOccurrence values, "
            f"got {type(candidate).__name__}",
        )
    existing = spans.get((candidate.start, candidate.end))
    if existing is not None and existing.surface != candidate.surface:
        raise MentionBindingError(
            "mention_span_disagreement",
            f"capture {index.capture_ref!r} segment {index.segment_ref!r} offsets "
            f"[{candidate.start}, {candidate.end}] are already registered as "
            f"{existing.surface!r} and are now offered as {candidate.surface!r}. Two readers "
            "disagree about what the document says at one position, and choosing between them is "
            "the arbiter's decision, not the index's. STOP: resolve it upstream and register one "
            "surface, or index the two captures separately so they cannot collide",
        )
    spans[(candidate.start, candidate.end)] = candidate


def _check_kind(
    registered: Mapping[MentionOccurrenceKey, MentionOccurrence],
    key: MentionOccurrenceKey,
    candidate: MentionOccurrence,
) -> None:
    """Refuse a second ``kind`` for one occurrence already at the same five keys.

    A producer's kind is **evidence about a mention, not part of its identity**, so it must not
    fork the address — and it must not be dropped either, because dropping it loses the
    disagreement. Refusing keeps both facts: the address stays one, and the record says the two
    classifications disagree.
    """
    existing = registered.get(key)
    if existing is not None and existing.kind != candidate.kind:
        raise MentionBindingError(
            "mention_kind_disagreement",
            f"capture {key.capture_ref!r} segment {key.segment_ref!r} span {list(key.span)} "
            f"surface {existing.surface!r} is already registered as kind {existing.kind!r} and is "
            f"now offered as {candidate.kind!r}. A producer's kind is evidence about a mention, "
            "not part of the mention's identity, so it must not fork the address - and it must "
            "not be dropped either. STOP: resolve the classification, or record the disagreement "
            "as two readings of one occurrence",
        )


__all__ = [
    "DEFERRED_ADDRESS_VERSION",
    "DEFERRED_CAPTURE_PREFIX",
    "DEFERRED_OCCURRENCE_PREFIX",
    "MENTION_ID_PREFIX",
    "MENTION_OCCURRENCE_KEY_COUNT",
    "DeferredCaptureAddress",
    "DeferredOccurrenceAddress",
    "MentionBindingError",
    "MentionOccurrence",
    "MentionOccurrenceIndex",
    "MentionOccurrenceKey",
    "ResolvedMention",
    "mint_capture_address",
    "mint_mention_id",
    "mint_occurrence_address",
    "parse_deferred_address",
    "unbound_mention_id",
]
