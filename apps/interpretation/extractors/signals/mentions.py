"""The **only** place a producer below the mention layer addresses a participant.

Feature 021, FR-094; spec FR-016 and FR-019; ``repair/ARBITRATION.md`` §8.

**Why this module exists at all, given brief §25 says producers may not mint mention
identities.** Because a producer still has to *name* the two ends of what it saw, and before
this module each of the seven construction sites invented a way to do it. There were five of
them and they disagreed with each other: ``surface:role:acme`` in the lexical producer,
``anchor:the team`` and ``href:https://...`` in the link producer, ``header:table0/role`` and
``cell:table0:ceo`` in the table producer, and ``document:current`` / ``attribute:role`` /
``jsonld:name`` in the metadata producer. Five namespaces, no authority, and — the part FR-094
is actually about — **four of the five put something other than a thing the document contains
where a participant goes**: a URL, a column *label*, a *field name*, and the literal string
``current`` standing in for a document nobody named. A ``Role: CTO`` line produced a signal
whose subject was ``attribute:role`` — the word "Role" in the markup posing as a thing in the
world — and whose object was the first 64 characters of a value, silently cut.

**What one minting rule fixes, and what it deliberately does not.** These are *deferred*
references: :class:`~domain.relation_participant.RelationParticipant.mention_ref` is documented
as a reference into the mention index and never a minted mention id (FR-016, FR-019,
constitution Invariant 2), and a deferred reference is the honest form for an extractor that
has read a surface occurrence and has not been handed a mention id for it. What the rule
enforces is that the reference names **an occurrence the document actually contains, in full,
at a position**:

* :func:`deferred_occurrence` takes the surface **whole**. There is no length ceiling anywhere
  in this module, and the surface is never sliced. The old ``content[:64]`` truncation is gone
  because a truncated address names a different string than the one in the document, and two
  values sharing a 64-character prefix would have been one participant.
* The position is in the reference, and it is the **first** component, so a reader never has to
  ask which of two ``@``s is the separator. A value that is an email address or a URL contains
  ``@``, and a link producer's target is ``https://…`` whose every path segment can contain one;
  with the position last, ``surface:meta_value:jane@acme.example@35-52`` had two and only
  ``rsplit`` recovered the span.
* **The fields are self-delimiting, so the address is injective for every input.** This is the
  second half of the same property, and it is the half that was broken: the retired grammar was
  ``surface[:@<start>-<end>:]<label>:<surface>`` with ``:`` as the field separator, and a
  syntactic producer's labels are dependency arcs that contain it (``nmod:of``, ``nsubj:pass``),
  so ``surface:nmod:of:acme`` was minted and read back as label ``nmod`` and surface ``of:acme``.
  Two distinct addresses, one string — and the platform could not tell that misparse from a
  surface that genuinely contains a colon. The fields are now the platform's own
  ``canonical_material`` and the address carries that material's ``digest128``, so it is
  content-addressed like every other identity on the substrate, the parser *verifies* rather than
  interprets, and an address written under the old form is refused by name instead of decoded into
  the wrong pair. :func:`deferred_occurrence` keeps its name, its location and its three refusal
  codes and delegates the writing to
  :func:`domain.mention_occurrence_index.mint_occurrence_address`; so does
  :func:`deferred_capture` to ``mint_capture_address``. **One minter per identifier kind** is not
  a tidiness rule here: it is the reason the collision could happen at all.
* :func:`deferred_capture` addresses **a capture the caller named**, and refuses a blank one
  with ``participant_capture_ref_required``. The literal ``document:current`` is the defect
  this replaces: ``current`` names no retrieval, so a metadata signal from two documents
  addressed one participant and every observation of "this document says it has an author"
  became the same participant.


**The label is structural, and that is the rule that is easy to get wrong.** A participant's
label comes from a closed platform vocabulary — a :class:`~domain.predicate_signature.
ArgumentSlot` token, a :class:`~semantic.contracts.RelationRole`, an HTML element name — and
never from a word the producer chose. ``surface:role:acme`` said "role" because the producer
thought about its cue that way, and the word is not in the document and not in any vocabulary;
``surface@118-122:cue_object:acme`` says which named group of the cue pattern matched, which is
a fact about the pattern and is readable by anyone re-running it.

**What this is not.** It is not resolution, and minting one of these grants no authority over
the referent. Two mentions of ``Acme`` in one document get two different references here, and
deciding they are the same thing is coreference — a later stage with a decision record. The
label goes in the *reference*, never into
:attr:`RelationParticipant.role_hypothesis`'s influence on identity: the participant's
:attr:`~domain.relation_participant.RelationParticipant.slot` remains the structural
:class:`ArgumentSlot`, and the label is not identity material beyond it (FR-009).

**The format is a published interface, and there is an inverse.**
:func:`read_occurrence` recovers ``(label, surface, span)`` from a reference, because a mention
binder holding only the string has to be able to, and re-deriving the parse in every caller is
how a format drifts. The test that keeps the two in step is
``test_read_occurrence_is_the_inverse_of_the_minter``.

**The grammar has one home and it is not here.** All three parts of the format — the two prefix
constants, **the encoder**, and the parse — live in :mod:`domain.mention_occurrence_index`,
because the other half of the seam needs them and that module is the only place below the mention
layer that can hold them: :mod:`apps.shared.semantic_path.execution` is the composition root and
importing it here would take the edge producer → composition root and pull the graph package into
extraction (FR-019, ``ARBITRATION`` §8). This module re-exports the constants and **delegates both
directions** — :func:`deferred_occurrence` to ``mint_occurrence_address``,
:func:`deferred_capture` to ``mint_capture_address``, :func:`read_occurrence` to
``parse_deferred_address`` — so a producer still reaches the vocabulary through
``extractors.signals.mentions`` and the producer-side contract keeps its name, its location and
its refusals. What moved is the *definition*, and the reason it had to move is a collision this
module's own history records: when the parser built ``surface:{label}:{surface}`` itself against a
grammar that split on the first ``:``, a label of ``nmod:of`` became the address of ``of:acme``.
A grammar with two homes drifts, and the drift is silent — addresses keep their shape and stop
resolving.


**The resolver is :func:`bind_participant_addresses`, and it is fail-closed.** The deferred
address is the right producer-side contract and it stays: this module still mints it, and no
producer mints an ``MN-`` (brief §25, FR-019). What was missing is the thing that *resolves* it,
and that is :class:`domain.mention_occurrence_index.MentionOccurrenceIndex` — the one minter of
``MN-…`` ids. :func:`bind_participant_addresses` is the seam between the two: given an index, a
producer's deferred address resolves to a real mention id, and a
``capture:`` end passes through as the ``CAP-`` id it already is. Anything that does not resolve
is **refused** with ``participant_address_unresolved`` naming the signal, the address and the
underlying code. It is never accepted unresolved, because an unresolved address that reaches
assembly is a participant that addresses nothing and reports as though it did not.

**Phase 4C added :func:`bind_producer_signals`, and the problem it solves is that the index was
built, tested, fail-closed, and called from nowhere.** :attr:`semantic_path.execution.SignalStep
.discovered` reached assembly with deferred addresses, and every one of them would have been
refused — the mention layer's records address whole entity spans at extractor granularity while
a producer addresses the cue group that matched, and a producer's scope is the producer. There
are two honest ways to reconcile that and this module takes the second: **register the producer's
own reads** (:func:`producer_occurrence_index`) rather than re-address them onto the mention
layer's spans, because the two are genuinely two observations of the document and FR-018's five
keys exist to keep them apart. The first — remapping a producer's end onto the mention layer's
span — would have been the orchestrator inventing a position nobody read. What a bound ``MN-``
is and is not is stated in full on :func:`bind_producer_signals`; the short version is that it
is a mention of the *producer's* occurrence and does not merge with the mention layer's.
"""


from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from domain.mention_occurrence_index import (
    DEFERRED_ADDRESS_VERSION,
    DEFERRED_CAPTURE_PREFIX,
    DEFERRED_OCCURRENCE_PREFIX,
    DeferredOccurrenceAddress,
    MentionBindingError,
    MentionOccurrence,
    MentionOccurrenceIndex,
    mint_capture_address,
    mint_occurrence_address,
    parse_deferred_address,
)
from domain.relation_participant import ParticipantEndKind

from extractors.signals.signal import RelationSignal, SignalContractError

#: What :func:`parse_deferred_address` returns for an ``surface:`` address rather than a
#: ``capture:`` one. Named so :func:`read_occurrence` asks the right question — the two shapes are
#: siblings, not a hierarchy, and a duck-typed check would accept a capture address as an
#: occurrence and hand a caller three fields of a two-field answer.
_OCCURRENCE_ADDRESS_TYPE = DeferredOccurrenceAddress

#: The deferred-occurrence namespace, and the platform's own: the same form
#: :mod:`parsers.shallow` mints for a clause's arguments and the same one
#: ``test_the_mention_reference_is_a_deferred_slot_address_and_not_a_minted_mention_id`` pins.
#: It is deliberately **not** ``MN-``: FR-019 reserves that prefix to the mention layer, and a
#: producer that minted one would be storing a fiction that looks like a durable record id.
#: Re-exported from :mod:`domain.mention_occurrence_index` rather than defined here, because the
#: resolver has to read the same two strings and two definitions of a published grammar is how it
#: drifts - see the module docstring. :data:`__all__` is what keeps the two names *used* rather
#: than dead imports, so a producer still reaches the vocabulary through this module.



def deferred_occurrence(
    *, label: str, surface: str, start: int | None = None, end: int | None = None
) -> str:
    """One occurrence of a surface, addressed whole and by position.

    **This is the producer-side contract and it does not change: same name, same location, same
    three refusal codes.** What changed is that it no longer *writes* the string. It validates and
    it delegates, to :func:`domain.mention_occurrence_index.mint_occurrence_address`, which is the
    one place an occurrence address is written — the same shape as
    :func:`domain.mention_occurrence_index.mint_mention_id` being the one place an ``MN-`` is
    written, and for the same reason. A grammar with two homes drifts, and this one had already
    drifted once: :mod:`parsers.shallow` built ``surface:{label}:{surface}`` itself and its
    dependency-arc labels contain ``:``, so ``surface:nmod:of:acme`` was minted and read back as
    label ``nmod`` and surface ``of:acme``. Two addresses, one string.

    The delegated form is::

        surface@<start>-<end>:<version>:<digest>:<material>     # positioned
        surface:<version>:<digest>:<material>                   # unpositioned

    where ``material`` is the label, the surface and the two offsets as one canonical list and
    ``digest`` is that material's own content address. **The fields are self-delimiting, so this
    is injective for every input** — a surface may contain ``:``, ``|``, ``@``, a newline, a
    non-ASCII letter or nothing at all, and a label may contain the separator that used to be the
    defect, because there is no separator in the payload to collide with. The position still comes
    first, for the reason it always did: these surfaces are URLs, email addresses and ``@``-handles,
    so no reader ever has to ask which ``@`` is the separator.

    **Nothing here guesses, and nothing here decodes.** An address written under the retired
    grammar is refused by :func:`read_occurrence` with ``participant_reference_unreadable`` and by
    the index with ``mention_address_unreadable``; it is never read as the label and surface its
    writer did not mean. A store or corpus holding one is a loud refusal, not a silent misread.

    A blank surface is refused with a code, because a participant that names nothing is a missing
    participant with no trace (FR-017). The surface is **never** shortened: not capped, not
    sliced. The one normalisation applied before the mint is collapsing runs of whitespace,
    because ``"Jane  Doe"`` and ``"Jane Doe"`` are the same string the reader sees and a reference
    that distinguished them would split one observation into two.
    """
    cleaned = " ".join(str(label or "").split())
    if not cleaned:
        raise SignalContractError(
            "participant_label_required",
            "a deferred occurrence says which named position of which structure it was read "
            "at, and '' says none. The label comes from a closed vocabulary - an "
            "ArgumentSlot token, a RelationRole, an element name - and never from a word the "
            "producer chose, because two producers labelling one mention differently would "
            "address it as two participants and corroborate nothing (FR-009)",
        )
    text = " ".join(str(surface or "").split())
    if not text:
        raise SignalContractError(
            "participant_surface_required",
            f"the occurrence read at {cleaned!r} has no surface text, so there is nothing to "
            "address. A producer that saw a position with no words there must decline to emit "
            "the signal rather than hand over a participant naming nothing (FR-017)",
        )
    if start is None and end is None:
        return mint_occurrence_address(label=cleaned, surface=text)
    if start is None or end is None or end < start:
        raise SignalContractError(
            "participant_occurrence_span_invalid",
            f"an occurrence address needs both offsets and a non-negative width; got "
            f"start={start!r}, end={end!r}. Half an address is a position that cannot be "
            "looked up, and an end before the start is a position in a document read "
            "backwards",
        )
    return mint_occurrence_address(label=cleaned, surface=text, start=start, end=end)


def read_occurrence(reference: str) -> tuple[str, str, tuple[int, int] | None]:
    """``(label, surface, span)`` from a reference :func:`deferred_occurrence` produced.

    Exists because the address is a **published interface** — a mention binder holding only the
    string has to be able to recover the position and the surface, and the fields are
    self-delimiting, so nothing in a surface can be mistaken for a separator. The inverse of the
    mint, in one place, so a binder is not re-deriving the parse.

    **The parse itself is
    :func:`domain.mention_occurrence_index.parse_deferred_address`**, and that is where it lives,
    because :class:`domain.mention_occurrence_index.MentionOccurrenceIndex` resolves these very
    strings and a second parser would be a second answer to "what does this address say". This
    function keeps the producer-side signature — a three-tuple, raising
    :class:`~extractors.signals.signal.SignalContractError` on an unreadable reference, which is
    what every existing caller in this package catches — over a parse that returns ``None``,
    because the index's ``None`` is answering a different question (does an occurrence here match
    this?) and its failure modes are three, not one.
    """
    parsed = parse_deferred_address(reference)
    occurrence = parsed if isinstance(parsed, _OCCURRENCE_ADDRESS_TYPE) else None
    if occurrence is None:
        raise SignalContractError(
            "participant_reference_unreadable",
            f"{reference!r} is not a deferred occurrence address in version "
            f"{DEFERRED_ADDRESS_VERSION!r}. A readable one is "
            f"{DEFERRED_OCCURRENCE_PREFIX}@<start>-<end>:{DEFERRED_ADDRESS_VERSION}:<digest>:"
            "<material> (positioned) or "
            f"{DEFERRED_OCCURRENCE_PREFIX}:{DEFERRED_ADDRESS_VERSION}:<digest>:<material> "
            "(unpositioned), where <material> is the label, the surface and the offsets as one "
            "canonical list. The form this replaced - "
            f"{DEFERRED_OCCURRENCE_PREFIX}[:@<start>-<end>:]<label>:<surface> - split the label "
            "at the first ':', so a label that contained one read as a different label and a "
            "different surface, and a reference that silently reads as a pair the writer never "
            "meant is a participant that addresses the wrong thing",
        )
    return occurrence.label, occurrence.surface, occurrence.span




def deferred_capture(*, capture_ref: str) -> str:
    """The retrieval a document-scoped observation belongs to, and it is **required**.

    This is where ``document:current`` died. A blank ``capture_ref`` used to be filled with the
    word ``current``, which names no retrieval: two documents' self-descriptions then addressed
    one participant, and a platform asking "who said this document has an author?" got an
    answer that was true of none of them (I-3, constitution IV).
    """
    ref = str(capture_ref or "").strip()
    if not ref:
        raise SignalContractError(
            "participant_capture_ref_required",
            "a document-scoped observation has to name the retrieval it came from, and '' "
            "names none. 'current' used to stand in here and it was a participant that "
            "resolved against no capture: two documents' bylines addressed one end, and the "
            "signal claimed a document nobody retrieved (I-3)",
        )
    return mint_capture_address(ref)



@dataclass(frozen=True)
class BoundParticipants:
    """One signal's participant ends, resolved from deferred addresses to real ids.

    ``mention_ids`` is **parallel to** the signal's ``participants`` tuple, position for
    position, because a participant's ``slot`` is what says which end is which and dropping the
    pairing would leave a reader to re-derive it from a set. ``refs`` is the address each id came
    from, in the same order, so the record says which occurrence of which document it resolved to
    rather than only what it became.
    """

    signal_id: str
    mention_ids: tuple[str, ...]
    refs: tuple[str, ...]
    capture_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "signal_id": self.signal_id,
            "mention_ids": list(self.mention_ids),
            "refs": list(self.refs),
            "capture_refs": list(self.capture_refs),
        }


def bind_participant_addresses(
    signals: Iterable[object],
    index: MentionOccurrenceIndex,
) -> tuple[BoundParticipants, ...]:
    """Resolve every deferred participant address in ``signals`` through ``index``.

    **The seam, and the only one.** A producer mints a deferred address
    (:func:`deferred_occurrence`) because it sits below mention extraction and must
    not invent a mention identity (brief §25, FR-019). This is where such an address becomes a
    real ``MN-…``: :class:`domain.mention_occurrence_index.MentionOccurrenceIndex` is the one minter
    of that prefix, and this function is what a producer hands its output to when an index is
    available. The deferred form stays the **producer-side** contract — the producer still never
    mints the id itself.

    **Fail-closed, with one code.** A ``surface:`` end is looked up in the index; a ``capture:``
    end is passed through as the ``CAP-`` id it already is, because a capture is a real
    content-addressed fetch event and not a mention. Anything else — an unreadable address, an
    occurrence the index does not hold, an unpositioned address that names several — is refused
    with ``participant_address_unresolved``, naming the signal, the address and the underlying
    code so an operator can tell a missing registration from an ambiguous one.

    **Why a refusal and not a warning.** An unresolved address that reaches assembly is a
    participant that addresses nothing: it groups under its own string, corroborates nothing, and
    reports as though it had been read. Failing loudly at the binding is the only place the
    information still exists to fix it (constitution IV, and I-3's "a finding is a finding").

    Order-independent and pure in ``index``: one binding per input signal, in the order given, and
    two processes with the same index and the same signals get the same answer (constitution VI,
    Domain Invariant 12).
    """
    bound: list[BoundParticipants] = []
    for signal in sorted(signals, key=_signal_order):
        mention_ids: list[str] = []
        refs: list[str] = []
        capture_refs: list[str] = []
        for participant in _participants_of(signal):
            reference = str(participant.mention_ref)
            # The participant's own declared end kind decides the path, and
            # :class:`domain.relation_participant.ParticipantEndKind` is where the decision and
            # its rejected alternative are recorded. A record that lies about its own end kind is
            # refused on construction, so this test is not a string sniff and cannot be fooled by
            # a surface that happens to start with the word "capture".
            if getattr(participant, "end_kind", None) is ParticipantEndKind.RETRIEVAL:
                # A retrieval, not an occurrence. Already a durable id; minting a mention for it
                # would put a second identity on one fact (I-2).
                capture_ref = index.read_capture(reference)
                if capture_ref is None:
                    raise SignalContractError(
                        "participant_capture_unreadable",
                        f"participant {reference!r} declares end_kind="
                        f"{ParticipantEndKind.RETRIEVAL.value!r} but the index's own inverse "
                        f"reads no retrieval in it, so it cannot be passed through as one. A "
                        "retrieval end is a durable id used as it stands; a string that claims "
                        "to be one and is not would make 'which fetch saw this' unanswerable "
                        "while looking like an answer (I-2, I-3)",
                    )
                capture_refs.append(capture_ref)
                mention_ids.append(reference)
                refs.append(reference)
                continue
            try:
                resolved = index.require_occurrence(reference)
            except MentionBindingError as exc:
                raise SignalContractError(
                    "participant_address_unresolved",
                    f"signal {getattr(signal, 'signal_id', '<unaddressed>')} from producer "
                    f"{getattr(signal, 'producer_ref', '<unnamed>')!r} addressed the end "
                    f"{reference!r}, and it does not resolve in the mention index for capture "
                    f"{index.capture_ref!r} segment {index.segment_ref!r} as read by "
                    f"{index.extractor_ref!r}: [{exc.code}] {exc.message}",
                ) from exc
            mention_ids.append(resolved.mention_id)
            refs.append(reference)
        bound.append(
            BoundParticipants(
                signal_id=str(getattr(signal, "signal_id", "")),
                mention_ids=tuple(mention_ids),
                refs=tuple(refs),
                capture_refs=tuple(capture_refs),
            )
        )
    return tuple(bound)


def _signal_order(signal: object) -> tuple[str, str]:
    """The sort key for a signal whose type this module does not import.

    ``signal_id`` is the content address, so sorting on it is sorting on content — never on
    ``id()``, and never on the address the producer happened to mint from a set. Reading it by
    name rather than importing :class:`~extractors.signals.signal.RelationSignal` keeps this
    module's imports at one edge instead of two and lets the binder be called with any
    participant-carrying record, which is what the golden path's own declared signal is.
    """
    return (str(getattr(signal, "producer_ref", "")), str(getattr(signal, "signal_id", "")))


def _participants_of(signal: object) -> Sequence[object]:
    """The signal's participant ends, or an empty tuple for a record that has none.

    A record with no participants is a record that made no observation of an end, and an empty
    tuple is the honest answer for it — the caller is not a producer and this module does not
    decide what its construction means.
    """
    return tuple(getattr(signal, "participants", ()) or ())


# --------------------------------------------------------------------------- #
# C3: the golden path, bound
# --------------------------------------------------------------------------- #

#: The ``kind`` recorded for an occurrence registered from a producer's own address.
#:
#: **A constant, and the reason is that ``kind`` is a checked field.** A producer's kind is
#: evidence about a mention rather than part of its identity, and
#: :meth:`MentionOccurrenceIndex.bind` *refuses* a second kind at the same five keys with
#: ``mention_kind_disagreement``. Registering each signal's own kind would therefore make the
#: metadata producer — which declares ``(METADATA, HIERARCHY, ATTRIBUTE, SCHEMA)`` and reads the
#: same ``<head>`` four ways — contradict itself at one span, and the index would be right to.
#: What the occurrence *is* has already been said by the signal that named it, and the bound
#: signal keeps its own ``kind``; the index holds occurrences, not classifications.
PRODUCER_OCCURRENCE_KIND = "producer-occurrence"


def producer_occurrence_index(
    signals: Sequence[RelationSignal],
    *,
    capture_ref: str,
    segment_ref: str,
) -> MentionOccurrenceIndex | None:
    """The one :class:`MentionOccurrenceIndex` a producer's own **positioned** addresses describe.

    **This is the reconciliation of the two addressings, and it is registration rather than
    re-addressing.** The mention layer addresses a whole entity span at extractor granularity —
    "John Smith" as one mention — while the lexical producer addresses the cue group that
    matched, which is "John". The spans do not coincide and they were never going to: they are
    two *different observations of the document*, read by two instruments, and
    :class:`~domain.mention_occurrence_index.MentionOccurrenceKey`'s five keys — capture, segment,
    span, normalised surface, **extractor** — exist precisely so that is two mentions rather than
    one. Remapping a producer's end onto the mention layer's span would have been the
    orchestrator inventing a position nobody read, which is resolution with no
    ``ResolutionDecisionRecord`` behind it. So the producer's own read is *registered* and
    resolves to the id that read really addresses.

    **What the resolved ``MN-`` is, stated plainly because it is easy to over-claim.** It is a
    mention of *the producer's occurrence*, not of the mention layer's. It does not merge with
    the mention layer's id and it must not be presented as though it did: corroboration across
    two instruments is computed after resolution, on entities, and two mention ids that resolve
    to one entity is exactly how two readers are correctly counted as two observations
    (``FR-018``). One consequence is deliberate and worth saying: a discovered signal will not
    group with the orchestrator's declared signal under
    :func:`semantic_path.assembly.pair_of`, because the two name different mentions. That is the
    right outcome — they are not the same observation — and it is the reason the golden path's
    declared hypothesis is unaffected by any producer.

    Returns ``None`` when no participant in the group carries a position, because there is then
    nothing to register and an index with no occurrences would resolve nothing while looking as
    though it had been consulted.
    """
    occurrences: list[MentionOccurrence] = []
    for signal in sorted(signals, key=_signal_order):
        for participant in _participants_of(signal):
            parsed = parse_deferred_address(str(participant.mention_ref))
            if not isinstance(parsed, DeferredOccurrenceAddress) or not parsed.positioned:
                continue
            occurrences.append(
                MentionOccurrence(
                    kind=PRODUCER_OCCURRENCE_KIND,
                    surface=parsed.surface,
                    start=parsed.span[0],
                    end=parsed.span[1],
                )
            )
    if not occurrences:
        return None
    return MentionOccurrenceIndex(
        capture_ref=capture_ref,
        segment_ref=segment_ref,
        extractor_ref=_producer_ref_of(signals),
        occurrences=occurrences,
    )


def _producer_ref_of(signals: Sequence[RelationSignal]) -> str:
    """The one producer these signals came from, refused rather than guessed.

    A group with two ``producer_ref`` values is not a group, and silently taking the first would
    mint one producer's occurrences under another's extractor key — which is a collision, since
    the extractor ref is one of the five keys an ``MN-`` is minted from.
    """
    refs = {str(getattr(signal, "producer_ref", "")) for signal in signals}
    if len(refs) != 1 or not next(iter(refs)).strip():
        raise SignalContractError(
            "producer_scope_ambiguous",
            f"a producer index is scoped to one extractor, and this group carries "
            f"{sorted(refs)}. An extractor ref is one of the five keys a mention id is minted "
            "from, so taking the first would address one producer's occurrences under another's "
            "key and two different reads would collide on one mention. Bind one producer at a "
            "time (FR-018)",
        )
    return next(iter(refs))


def bind_producer_signals(
    signals: Iterable[RelationSignal],
    *,
    capture_ref: str,
    segment_ref: str,
    mention_index: MentionOccurrenceIndex | None = None,
) -> tuple[RelationSignal, ...]:
    """Every discovered producer signal, with its participants bound to real ``MN-`` ids.

    **What this is for, and what it is not.** ``SignalStep.discovered`` reaches assembly with
    deferred addresses, and the binder would refuse every one of them on two different grounds:
    the mention layer's records address whole entity spans while a producer addresses the cue
    group that matched, and a producer's scope is the producer rather than the extractor set.
    :func:`producer_occurrence_index` registers the producer's own reads and
    :func:`bind_participant_addresses` resolves them, and this function is what puts the two
    together and hands assembly a signal whose participants are real mention ids — which is the
    only form assembly can group on, since it groups by
    :func:`~semantic_path.assembly.pair_of`.

    **A bound signal is a new record, and it says where it came from.** The address is derived
    material, so the ``signal_id`` changes; the deferred address each participant carried is
    kept in ``extra["bound_participants"]`` and the binding in ``notes``. Nothing is lost and
    nothing is silently re-addressed: a reader can recover exactly which occurrence of which
    document each end became, which is the record I-3 asks for and the reason this is a
    separate call over an already-written signal rather than a parameter on the producer.

    **Unpositioned addresses are refused unless the mention layer's own index is supplied, and
    that is not leniency — it is the only honest source.** The syntactic producer's positions
    are clause-relative token indices, so its addresses are the unpositioned form with
    no character span. There is no span to *register*, so a per-producer index cannot be built
    from them; the only index that holds positions for this segment is the mention layer's, and
    an unpositioned address resolves there **only when the segment holds that surface exactly
    once**. Two occurrences is :meth:`MentionOccurrenceIndex.require_occurrence`'s
    ``mention_occurrence_ambiguous``, and it is refused by name rather than broken by taking the
    first match: the index will not pick an order to break a tie that the producer never stated.

    Order-independent and pure in its arguments (constitution VI, Domain Invariant 12): signals
    are processed in a content-derived order, the index sorts its own keys, and the returned
    tuple is in input order so a caller can zip it against what it passed in.
    """
    captured = str(capture_ref or "").strip()
    if not captured:
        raise SignalContractError(
            "participant_capture_required",
            "a producer's occurrences are addressed by (capture, segment, extractor, span, "
            "surface) and the capture is the first of the five keys a mention id is minted from. "
            "Binding without one would mint ids that cannot say which retrieval produced them — "
            "the collision the capture key was added to prevent, arriving by another route. STOP: "
            "name the retrieval the producers ran over, or accept the deferred addresses "
            "unresolved and resolve them in a layer that records the decision (FR-018)",
        )
    segment = str(segment_ref or "").strip()
    if not segment:
        raise SignalContractError(
            "participant_segment_required",
            "offsets with no segment are unresolvable, and a mention id minted from one would "
            "address a position in a document nobody named. STOP: name the segment the "
            "producers read (FR-018)",
        )

    ordered = tuple(sorted(signals, key=_signal_order))
    by_producer: dict[str, list[RelationSignal]] = {}
    for signal in ordered:
        by_producer.setdefault(str(signal.producer_ref), []).append(signal)

    bound: dict[str, RelationSignal] = {}
    for producer_ref in sorted(by_producer):
        group = by_producer[producer_ref]
        try:
            index = producer_occurrence_index(
                group, capture_ref=captured, segment_ref=segment
            )
        except MentionBindingError as exc:
            # Registering what the producer read is itself a place the index can refuse: a
            # producer that read two different strings at one position is caught by
            # `mention_span_disagreement` while the index is being *built*, before any address is
            # looked up. That refusal is the index's and it is precise; what is added is the
            # producer it belongs to, which the index has no way of knowing.
            raise SignalContractError(
                "participant_address_unresolved",
                f"producer {producer_ref!r} addressed {len(group)} signal(s) whose occurrences "
                f"cannot be registered: [{exc.code}] {exc.message}",
            ) from exc
        for signal in sorted(group, key=_signal_order):
            # Keyed on the **pre-binding** id, because that is the only handle the caller has
            # on what it passed in: the bound signal's own id is a different string, and looking
            # the result up by the new one is a KeyError waiting for the first producer that
            # binds.
            bound[signal.signal_id] = _bind_one(signal, index, mention_index)
    # Input order, not sorted order: a caller zipping this against what it passed in needs the
    # pairing, and the pre-binding id is what it can pair on.
    return tuple(bound[signal.signal_id] for signal in ordered)


def _bind_one(
    signal: RelationSignal,
    index: MentionOccurrenceIndex | None,
    mention_index: MentionOccurrenceIndex | None,
) -> RelationSignal:
    """One signal's participants resolved, or a refusal that names which end and which code."""
    from_addresses: list[str] = []
    mention_ids: list[str] = []
    capture_refs: list[str] = []
    for participant in _participants_of(signal):
        reference = str(participant.mention_ref)
        from_addresses.append(reference)
        # The participant's own declared end kind chooses the path (C4's decision, recorded on
        # :class:`domain.relation_participant.ParticipantEndKind`). A retrieval is already a
        # durable id and passes through as itself; an occurrence is looked up.
        if getattr(participant, "end_kind", None) is ParticipantEndKind.RETRIEVAL:
            capture_ref = next(
                (
                    ref
                    for ref in (index.read_capture(reference) if index is not None else None,
                                mention_index.read_capture(reference)
                                if mention_index is not None
                                else None)
                    if ref is not None
                ),
                None,
            )
            if capture_ref is None:
                raise SignalContractError(
                    "participant_capture_unreadable",
                    f"signal {signal.signal_id} from producer {signal.producer_ref!r} has a "
                    f"participant {reference!r} that declares end_kind="
                    f"{ParticipantEndKind.RETRIEVAL.value!r}, and the index's own inverse reads "
                    "no retrieval in it. A retrieval end is a durable id used as it stands; a "
                    "string that claims to be one and is not would make 'which fetch saw this' "
                    "unanswerable while looking like an answer (I-2, I-3)",
                )
            capture_refs.append(capture_ref)
            mention_ids.append(reference)
            continue
        resolved = None
        for candidate_index in (index, mention_index):
            if candidate_index is None:
                continue
            try:
                resolved = candidate_index.require_occurrence(reference)
            except MentionBindingError as exc:
                _raise_unresolved(signal, reference, exc)
            else:
                break
        if resolved is None:
            raise SignalContractError(
                "participant_occurrence_unpositioned",
                f"signal {signal.signal_id} from producer {signal.producer_ref!r} addressed the "
                f"end {reference!r}, and it is an *unpositioned* address — a surface with no "
                "character offsets. This producer's positions are clause-relative token "
                "indices, so there is no span to register an occurrence from, and an index "
                "built only from a producer's own reads therefore cannot hold it. STOP: have "
                "the producer emit character offsets (deferred_occurrence(..., start=, end=)), "
                "or pass the mention layer's index so the surface resolves only where the "
                "segment holds it exactly once; do not pick a position (FR-016, FR-018)",
            )
        mention_ids.append(resolved.mention_id)
    return replace(
        signal,
        participants=tuple(
            _rebound(participant, mention_id)
            for participant, mention_id in zip(_participants_of(signal), mention_ids)
        ),
        notes=(
            f"{signal.notes} bound by the mention layer: "
            + ", ".join(
                f"{address} -> {mention_id}"
                for address, mention_id in zip(from_addresses, mention_ids)
            )
        ).strip(),
        extra={**signal.extra, "bound_participants": tuple(from_addresses)},
        signal_id="",
    )


def _rebound(participant: object, mention_id: str):
    """The same participant with its reference replaced and nothing else touched.

    ``replace`` rather than reconstruction from the six named fields, so a field added to
    :class:`~domain.relation_participant.RelationParticipant` after this function was written
    travels through it instead of being silently defaulted. ``mention_ref`` is the only thing
    that changes: the slot says which end this is, the role hypothesis and ordinal say what the
    producer read about it, and ``argument_shape`` says what it is — none of which is a function
    of which mention id the end became.
    """
    return replace(participant, mention_ref=mention_id)


def _raise_unresolved(signal: object, reference: str, exc: MentionBindingError) -> None:
    """Re-raise an index refusal as a signal-contract refusal that names the signal.

    The index's codes are precise and are preserved verbatim in the message, because "did not
    resolve" and "is ambiguous" are different bugs for an operator; what is added is **which
    signal and which producer** asked, which the index has no way of knowing.
    """
    raise SignalContractError(
        "participant_address_unresolved",
        f"signal {getattr(signal, 'signal_id', '<unaddressed>')} from producer "
        f"{getattr(signal, 'producer_ref', '<unnamed>')!r} addressed the end {reference!r}, and "
        f"it does not resolve: [{exc.code}] {exc.message}",
    ) from exc


__all__ = [
    "DEFERRED_ADDRESS_VERSION",
    "DEFERRED_CAPTURE_PREFIX",
    "DEFERRED_OCCURRENCE_PREFIX",
    "PRODUCER_OCCURRENCE_KIND",
    "BoundParticipants",
    "bind_participant_addresses",
    "bind_producer_signals",
    "deferred_capture",
    "deferred_occurrence",
    "producer_occurrence_index",
    "read_occurrence",
]



