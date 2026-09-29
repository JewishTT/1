"""The syntactic producer: a parsed clause, as a relation signal.

Feature 021, brief §29; spec FR-042, FR-043; ``data-model.md`` part 3;
``repair/A2-identity-subsystem.md`` D6.3 H6.

**What this producer reads.** A clause of running text, parsed by the pinned shallow
parser in :mod:`parsers.shallow`, normalised by
:func:`domain.predicate_voice.normalize_predicate`, and reported as one
:class:`~extractors.signals.signal.RelationSignal` carrying a
:class:`~domain.predicate_signature.PredicateSignature`. Nothing else. It resolves nothing,
admits nothing and emits no claim, and that absence is structural rather than a promise: this
module imports no ``RelationClaim``, no candidate, no graph and no projection symbol, so it
could not set one even by mistake (FR-020).

**It emits no operator.** The brief's requirement is exact: this producer "must NOT directly
emit ``works_for``, ``founded``, ``owner_of`` unless the lexical/semantic mapping layer
explicitly says so". So :attr:`RelationSignal.relation_ref` is ``None`` on every signal
here, unconditionally, and what the platform knows about the predicate travels as the
signature - ``work(A0:,A1:at)``, a structural projection - plus the document's own words as
the surface. Deciding that ``work(A0:,A1:at)`` is ``works_for`` is a lexical-semantic claim
brief §20 reserves to explicit mapping, and a producer that made it would be unmappable,
undatable and unre-derivable from the text.

**The signature is the product, and the surface is kept beside it.** ``John acquired Acme``
and ``Acme was acquired by John`` produce the *same* ``identity_projection()`` and therefore
one ``logical_candidate_id``, while producing two signals with two surfaces and two
``signal_id``s. That is brief §18, end to end, over a real parser: a signature replaces the
raw words in logical identity and the raw words survive as evidence. ``test_sc001_end_to_end_
over_the_syntactic_producer`` is the test, and it **passes** - it is not marked ``xfail``.

**Where the producer is silent, and why that is not a gap.** The parser declares a
construction or it refuses, and :class:`~parsers.shallow.Refusal` records which. Brief §30
requires a missing parser capability to mean "no syntactic signals" and *not* a batch
failure, which only holds if the reason is machine-readable - so :class:`SyntacticExtraction`
carries a refusal ledger and :meth:`SyntacticExtraction.refusals_by_code` turns it into a
count. ``unsupported_construction`` is a **number** over a corpus, not a silence, and a
caller that wants to know how much of a document this producer could read asks for the count
rather than inferring it from an empty tuple.

**N-ary readings reach the real participant field, and the shape is in the address.**
``John sold Acme to Microsoft in 2020`` has four canonical slots, and
:class:`~extractors.signals.signal.RelationSignal` is natively n-ary as of Phase 4A, so all
four are declared as :class:`~domain.relation_participant.RelationParticipant` values with the
slot each one fills. This producer used to keep the first two as the signal's participants and
park *every* participant in ``extra["participants"]`` as a list of dicts - a documented
workaround for a substrate that could only hold two ends. The workaround cost three things and
has now been replaced: the two dropped ends were invisible to any contract, the list was
untyped, and because ``extra`` is excluded from the address material, a four-slot reading and a
two-slot reading of the same two mentions addressed to the **same** ``signal_id``. Declared
shape is part of what was seen, so it is part of the address.

**What it will not do.** It does not assign a role name.
:attr:`~domain.relation_participant.RelationParticipant.role_hypothesis` would be the place
for "buyer" or "seller", and this producer writes the *position label* there instead, because
two producers guessing different role names for one ``A1`` must produce one logical candidate
(FR-009) and a free-text role would fork the id. It does not resolve a relative pronoun's
antecedent beyond a comma-bracketed relative clause with a single matrix NP. And it does not
read a table, a link, a heading or a metadata field: those are peers in this package, not this
producer's business.
"""


from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from domain.predicate_signature import Polarity  # noqa: F401  (re-exported for callers)
from domain.predicate_voice import SyntacticConstruction, normalize_voice
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis

from extractors.signals.protocol import (
    ExtractionScope,
    ProducerDeclaration,
)
from extractors.signals.signal import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalKind,
)
from parsers.shallow import (
    H6_STOP_CONDITION,
    PARSER_VERSION,
    SHALLOW_CAPABILITY,
    DeclaredChannel,
    ParserContractError,
    Refusal,
    RefusalCode,
    RefusalStage,
    SlotBinding,
    SyntacticReading,
    assign_slots,
    logical_candidate_id_of,
    parse,
    refusal_counts,
    tokenise,
)

#: The producer's identity, and the parser version that goes with it. The two are separate
#: fields because a rule change inside the parser is a different event from a change to this
#: producer, and FR-034's independence count is over producers: two parser versions behind
#: one ``producer_ref`` would be one source reading the page two ways, which is exactly the
#: ambiguity FR-034 exists to prevent.
PRODUCER_REF = "syntactic/pinned-shallow-clause"
INDEPENDENCE_FAMILY = "prose"
PRODUCER_VERSION = PARSER_VERSION

#: The pair ceiling this producer works under. It is a *ceiling*, and the producer reports
#: zero: a clause parser reads one clause left to right and never enumerates a mention pair,
#: so ``pairs_considered`` on every signal below is 0 and this number is the limit it asserts
#: it never approaches. The lexical producer declares a ceiling for the same reason and says
#: the same thing in its neighbourhood.
MAX_PAIRS_CONSIDERED = 10_000


@dataclass(frozen=True, slots=True)
class SyntacticExtraction:
    """What one batch of records produced: signals, readings, and the refusal ledger.

    The ledger is not a diagnostic extra. brief §30's guarantee - a missing parser capability
    means no syntactic signals and never a batch failure - is only checkable if the reason is
    counted, and a count needs the refusals to travel with the signals rather than be logged
    and dropped.
    """

    signals: tuple[RelationSignal, ...] = ()
    readings: tuple[SyntacticReading, ...] = ()
    refusals: tuple[Refusal, ...] = ()

    def refusals_by_code(self) -> dict[str, int]:
        """``{code: count}``, keys sorted, over every refusal in the batch."""
        return refusal_counts(self.refusals)

    def count(self, code: str | RefusalCode) -> int:
        """How many refusals carried ``code``.

        The named-code query brief §30 asks for, so a caller can measure one gap -
        ``unsupported_construction``, ``coordinated_clause`` - without reading the detail
        strings.
        """
        wanted = str(code)
        return sum(1 for refusal in self.refusals if refusal.code == wanted)

    def signals_for_construction(
        self, construction: SyntacticConstruction
    ) -> tuple[RelationSignal, ...]:
        """The signals whose reading declared ``construction``, in document order.

        Provided because "which constructions can this parser actually declare on our
        corpus" is the question the coverage note in
        :data:`~parsers.shallow.PARSER_LIMITATIONS` invites, and answering it by re-parsing
        the text would be answering it with a second run rather than with the one that
        happened.
        """
        return tuple(
            signal
            for signal, reading in zip(self.signals, self.readings, strict=True)
            if reading.construction is construction
        )


class SyntacticExtractor:
    """Parsed clauses, as ``SYNTAX`` signals carrying a predicate signature.

    Implements :class:`~extractors.signals.protocol.RelationSignalExtractor` structurally.
    :meth:`extract` is the protocol method and returns signals only; :meth:`report` runs the
    same parse and hands back the refusal ledger as well, and it is what
    :func:`syntactic_signals` uses. The split exists because the protocol's contract is
    "a tuple of signals, always" and a producer that also has to report *why* it found
    nothing needs somewhere to put the answer.
    """

    def declares(self) -> ProducerDeclaration:
        return ProducerDeclaration(
            producer_ref=PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            kinds=(SignalKind.SYNTAX,),
            reads=(
                "one clause of running text, tokenised by a pinned shallow parser and read "
                "left to right. The parser declares a construction, a head lemma and a set of "
                "argument positions; the reading is then normalised by normalize_predicate, "
                "which assigns the canonical argument slots. Reported as a structural "
                "signature - 'acquire(A0:,A1:)' - and as the document's own words."
            ),
            cannot_read=(
                "role names, and that is not a small loss: the parser says an argument is the "
                "nmod:by phrase, not that it is the seller, because two producers guessing "
                "'buyer' and 'vendor' for one slot must produce one logical candidate. It "
                "cannot tell a predicate from an adjective ('John is elected' is refused "
                "rather than read), cannot tell a bare PP complement from a copular one "
                "('John is at Acme' is refused), cannot read a reduced relative ('John, who "
                "founded Acme' is refused for an unoccupied required slot), cannot unify "
                "'is CEO of' with 'was appointed CEO of', and cannot read a coordinated "
                "clause at all. It also cannot read a table, a link, a heading or a metadata "
                "field - those are peers in this package."
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes=(
                "No LLM and no learned parameter is anywhere in this path: the parser is "
                "regex and table lookups over a closed function-word inventory, and its "
                f"capability is pinned as {SHALLOW_CAPABILITY.to_dict()}. Every clause it "
                "cannot read is a named refusal, not a nearest-row guess, and a document it "
                "cannot read at all yields zero signals and no exception - which is brief "
                "section 30's requirement, not a nicety. "
                + H6_STOP_CONDITION
            ),
        )

    def extract(
        self, record: object, *, scope: ExtractionScope
    ) -> tuple[RelationSignal, ...]:
        """Every syntactic signal in ``record``, and nothing else.

        Never raises. One unparseable record costs this producer its findings on that
        record, not the batch, and the reason is available from :meth:`report`.
        """
        return self.report(record, scope=scope).signals

    def report(self, record: object, *, scope: ExtractionScope) -> SyntacticExtraction:
        """The signals, the readings behind them, and the refusals, for one record."""
        text, overrides = _text_of(record)
        language = overrides.get("language") or "en"
        channel = DeclaredChannel(
            subject=overrides.get("declared_subject", ""),
            head=overrides.get("declared_head", ""),
            label=overrides.get("channel_label", ""),
        )
        readings, refusals = parse(text, language=language, channel=channel)
        signals: list[RelationSignal] = []
        emitted: list[SyntacticReading] = []
        for ordinal, reading in enumerate(readings):
            signal = self._signal_for(
                reading,
                ordinal=ordinal,
                text=text,
                scope=scope,
                overrides=overrides,
            )
            if signal is None:
                continue
            signals.append(signal)
            emitted.append(reading)
        return SyntacticExtraction(
            signals=tuple(signals), readings=tuple(emitted), refusals=refusals
        )

    def _signal_for(
        self,
        reading: SyntacticReading,
        *,
        ordinal: int,
        text: str,
        scope: ExtractionScope,
        overrides: Mapping[str, str],
    ) -> RelationSignal | None:
        """One declared reading as one signal, or ``None`` if it has no two participants.

        ``None`` is a real case rather than a formatting accident: a reading can occupy one
        canonical slot (a pronoun subject, a headless PP with no declared subject), and
        :class:`~extractors.signals.signal.RelationSignal` refuses a self-connection and a
        single-ended signal. Those readings arrive as refusals from the normaliser, so
        nothing is lost by declining to build a signal here - and inventing a second mention
        to make the shape fit would be a fabricated participant.
        """
        try:
            bindings = assign_slots(reading)
        except ParserContractError:
            # The producer's plan and the normaliser disagreed, which is a defect rather than
            # a corpus condition. Refuse the reading and say so; never emit a signal whose
            # participants were guessed.
            return None
        if len(bindings) < 2:
            return None
        participants = tuple(
            _participant_of(binding, position)
            for position, binding in enumerate(bindings)
        )
        return RelationSignal(
            # **Every** slot the reading filled, with the slot it filled. This used to be
            # written to ``extra["participants"]`` as a list of dicts, which was a documented
            # workaround for a signal shape that could only hold two ends: the four-slot
            # reading of "John sold Acme to Microsoft in 2020" kept two participants and
            # parked two in an untyped bag that no contract, no validation and - because
            # ``extra`` is excluded from the address material - no identity knew about. Two
            # signals declaring different arities over the same two mentions addressed to one
            # ``signal_id``. The field is typed and in the address now.
            participants=participants,
            kind=SignalKind.SYNTAX,
            # The clause's own predicate words, not an operator's name. The platform may
            # later decide that "acquired by" means `acquired_from`; that decision belongs to
            # a SemanticRegime and is recorded as a second reading, not smuggled in here.
            relation_surface=reading.predicate_span,
            # How this producer saw the connection, from the closed nine. `event_frame` and
            # not `predicate_text`, and the distinction is not tidiness: the predicate words
            # alone are not this producer's observation, the *frame* is. `predicate_text` is
            # the basis of a cue-phrase producer, and a signal whose basis is predicate text
            # is obliged to carry its words - a rule that happens to be satisfiable here, but
            # claiming a weaker basis than the one actually used would be a record that
            # understates its own evidence.
            basis=SignalBasis.EVENT_FRAME,
            # **Read off the reading, not asserted.** The parser states the polarity it saw
            # on :attr:`SyntacticReading.polarity`, and this is the one field on the signal
            # that is a fact about the clause rather than a fact about how it was read - so
            # copying it is right and defaulting it would be wrong in the direction that
            # matters: a denial reported as an assertion is the specific failure FR-012's
            # aspect split exists to stop. Phase 4B reopened the negated-clause path in
            # :mod:`parsers.shallow` (which used to refuse "John is not the CEO of Acme"
            # with the reason that this field did not exist), so a denied reading arrives
            # here with ``reading.polarity is Polarity.DENIED`` and lands on the signal as a
            # denial.
            polarity=reading.polarity,
            neighbourhood=Neighbourhood(

                characters_scanned=len(reading.clause),
                # Zero, and the zero is the point. `pairs_considered` means one thing across
                # every producer: how many mention pairs were *compared*. A clause parser
                # compares none - it reads one clause deterministically and declares what it
                # found. `characters_scanned` already records how much was read.
                pairs_considered=0,
                scope_read=(
                    f"one clause ({len(tokenise(reading.clause))} tokens), read left to right "
                    f"by the pinned shallow parser {SHALLOW_CAPABILITY.parser_version} "
                    f"(configuration {SHALLOW_CAPABILITY.configuration_hash}); no mention pair "
                    "was enumerated and no other document was read"
                ),
                precision=(
                    f"exact; constructor {reading.constructor}, channel "
                    f"{reading.channel_label or 'sentence'}"
                ),
                notes=f"clause: {reading.clause}",
            ),
            # Unconditionally None. See the module docstring: emitting `works_for` here is
            # the thing brief §29 forbids, and this field is the only place it could happen.
            relation_ref=None,
            # The slot order is the direction, so it is read from the parse rather than
            # guessed. AMBIGUOUS would be wrong - the slots *are* the direction - and a
            # default would be a decision nobody made.
            direction=DirectionHypothesis.SUBJECT_TO_OBJECT,
            context_ref=overrides.get("context_ref") or scope.context_ref,
            semantic_regime_ref=(
                overrides.get("semantic_regime_ref") or scope.semantic_regime_ref
            ),
            capture_ref=overrides.get("document_ref") or scope.document_ref,
            # Exact about the structure, silent about the world. That the clause matched a
            # pinned construction rule is a fact about the text; that the relation holds is
            # not, and no number here could express the second thing.
            producer_confidence=1.0,
            signal_ordinal=ordinal,
            tenant_id=scope.tenant_id,
            # Stated by the producer and then stamped by the registry, which is what every
            # peer here does. It matters beyond convention: ``run_producer`` re-addresses a
            # stamped signal, so a producer that left these blank would see its own
            # ``signal_id`` move the moment the registry ran, and a reading joined to a
            # signal by that id would silently come apart.
            producer_ref=PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            notes=(
                f"constructor {reading.constructor}; observed frame "
                f"{reading.observed_construction_frame.value}"
            ),
            extra={
                "constructor": reading.constructor,
                "construction": str(reading.construction),
                "predicate_surface": reading.predicate_surface,
                "predicate_span": reading.predicate_span,
                # The OBSERVED frame. This is evidence, and it is the reason an active and a
                # passive realisation are two signals: the demotion to
                # `verb_active_transitive` happens at V1 in the signature, and the surface's
                # own frame survives here where a reader can see it.
                "observed_construction_frame": str(reading.observed_construction_frame),
                "head_function_word": reading.head_function_word or "",
                "predicate_signature": reading.signature.to_dict(),
                "rendered_predicate": reading.rendered_predicate,
                "normalization_trace": _trace_of(reading),
                "parser_capability": SHALLOW_CAPABILITY.to_dict(),
                "clause": reading.clause,
            },
        )



def _participant_of(binding: SlotBinding, position: int) -> RelationParticipant:
    """One filled slot as one :class:`RelationParticipant`, and what it declines to assert.

    Four of the six fields are determined and two are deliberately not:

    - :attr:`~domain.relation_participant.RelationParticipant.slot` is the canonical
      ``ArgumentSlot`` :func:`assign_slots` checked against ``normalize_voice``, so the
      participant and the signature cannot disagree about which position this end fills.
    - :attr:`~domain.relation_participant.RelationParticipant.ordinal` is the position **as
      observed** - ``assign_slots``' order, which is the parser's edges order and not a
      canonical reordering. The distinction matters: the canonical order is the identity's
      business, and the observed order is the evidence's.
    - :attr:`~domain.relation_participant.RelationParticipant.role_hypothesis` carries the
      *position label* (``nsubj``, ``obj``, ``nmod:in``), never a role name. The module
      docstring's whole argument is here: "buyer" and "seller" are guesses, two producers
      guessing differently for one slot must produce one candidate, and a free-text role in
      the identity term would fork it. The label is what the parser actually observed.
    - :attr:`~domain.relation_participant.RelationParticipant.confidence` is 1.0 for the same
      reason the signal's :attr:`RelationSignal.producer_confidence` is: this producer is exact
      about the structure - the clause matched a pinned rule - and saying less would understate
      what it knows. It is not a probability that the relation holds, and it is excluded from
      the address, so it cannot manufacture corroboration either way.

    **``argument_shape`` is left at its default and that is a decision.** A participant here may
    be a value - ``John sold Acme to Microsoft in 2020`` puts ``2020`` in ``A2`` - and the
    honest shape is ``"value"``. The pinned parser nevertheless labels it ``nmod:in`` and
    nothing else, and states in ``PARSER_LIMITATIONS`` that it applies no temporal test at
    all (``test_gap_a_no_complement_is_labelled_temporal_and_every_one_is_retained`` asserts
    exactly that absence). Deciding here that ``nmod:in`` means "value" would re-introduce the
    temporal classification the parser deliberately declined to make, on the strength of one
    preposition. So the field is populated with the default and the claim is *not* made; the
    shape is set when a typed, testable source for it exists, which is FR-012's stated
    ``QUANTITY → argument_shape = "value"`` mapping. Phase 4C deleted the ``QUANTITY`` *kind*,
    so this attribute is the whole of the mapping's landing place and the only way a measured
    value is recorded as one.
    """
    return RelationParticipant(
        mention_ref=binding.argument.mention_ref,
        slot=binding.slot,
        role_hypothesis=binding.argument.position_label,
        ordinal=position,
        confidence=1.0,
    )


def _trace_of(reading: SyntacticReading) -> list[str]:

    """The normalisation trace, recovered by re-running the authority on the declared parse.

    ``CanonicalArgumentAssignment`` holds the trace and
    :class:`SyntacticReading` does not carry the assignment, so the trace is obtained by
    calling ``normalize_voice`` on exactly the structures the reading was built from. That
    is a second call rather than a stored copy, and it is the right way round: the trace is
    corpus-visible evidence, and copying a field onto a record invites the record and the
    computation to disagree.
    """
    return list(
        normalize_voice(
            reading.predicate,
            reading.syntactic_structure,
            reading.dependency_structure,
        ).normalization_trace
    )


def _text_of(record: object) -> tuple[str, Mapping[str, str]]:
    """The text to parse and any per-record reference overrides.

    A string is the whole contract for the common case. A mapping is accepted so a caller
    that already holds a parsed document can pass the frame and regime *that document* was
    read under, and so a document-structure channel can declare the subject and governor
    that ``CONSTRUCTION_TABLE`` row 9 requires for a headless PP.
    """
    if isinstance(record, str):
        return record, {}
    if isinstance(record, Mapping):
        text = str(record.get("text") or record.get("markdown") or record.get("markup") or "")
        overrides = {
            key: str(record[key])
            for key in (
                "context_ref",
                "semantic_regime_ref",
                "document_ref",
                "language",
                "declared_subject",
                "declared_head",
                "channel_label",
            )
            if record.get(key)
        }
        return text, overrides
    return "", {}


def syntactic_signals(
    records: Iterable[object], *, scope: ExtractionScope
) -> SyntacticExtraction:
    """Drive the syntactic producer over records, and return the ledger with the signals.

    Not a bare tuple, unlike its peers in this package, and the difference is the point: a
    caller has to be able to ask *why* a corpus produced no syntactic signals without
    re-parsing it. The signals are still bounded, stamped and de-duplicated by
    :func:`~extractors.signals.protocol.run_producer` - this function adds the ledger, not a
    second code path around the checks.
    """
    from extractors.signals.protocol import run_producer

    producer = SyntacticExtractor()
    records = list(records)
    signals = run_producer(producer, records, scope=scope)
    # The readings are joined to the *stamped and de-duplicated* signals by signal id rather
    # than by position, because ``run_producer`` may drop a duplicate and the two tuples
    # would then no longer be index-aligned - a silent misalignment that would put one
    # reading's participants under another reading's signal. A signal with no reading here
    # would be a bug in the producer, and it is dropped rather than guessed at.
    by_id: dict[str, SyntacticReading] = {}
    refusals: list[Refusal] = []
    for record in records:
        reported = producer.report(record, scope=scope)
        refusals.extend(reported.refusals)
        for signal, reading in zip(reported.signals, reported.readings, strict=True):
            by_id[signal.signal_id] = reading
    readings = tuple(
        by_id[signal.signal_id] for signal in signals if signal.signal_id in by_id
    )
    return SyntacticExtraction(
        signals=signals, readings=readings, refusals=tuple(refusals)
    )


def syntactic_candidate_ids(
    extraction: SyntacticExtraction,
    mentions_by_surface: Mapping[str, object],
    *,
    tenant_id: str,
) -> tuple[tuple[str, str], ...]:
    """``(signal_id, logical_candidate_id)`` per signal whose participants are all bound.

    Fail-closed: a reading with an unbound participant is *omitted*, and the caller sees a
    shorter tuple rather than an id minted over fewer participants than the sentence has.
    That is the whole of brief §18's end-to-end claim from a producer's side - two surfaces,
    one identity - and it needs a mention binding the producer cannot supply itself.

    **The polarity is the reading's own**, and Phase 4B changed this call from a literal
    :attr:`~domain.predicate_signature.Polarity.ASSERTED` to ``reading.polarity``. Passing
    ``ASSERTED`` here was harmless only while the parser refused every negated clause; now
    that it records them, a hard-coded ``ASSERTED`` would have computed the *denial's*
    logical id as though the clause asserted it, and "John is not the CEO of Acme" and
    "John is the CEO of Acme" would be one logical candidate. Polarity is in the identity
    material (part 5.1), which is what makes that a fork rather than a labelling difference.
    """
    pairs: list[tuple[str, str]] = []
    for signal, reading in zip(extraction.signals, extraction.readings, strict=True):
        try:
            pairs.append(
                (signal.signal_id, logical_candidate_id_of(
                    reading,
                    mentions_by_surface,
                    tenant_id=tenant_id,
                    polarity=reading.polarity,
                ))
            )
        except ParserContractError:
            continue
    return tuple(pairs)


__all__ = [
    "H6_STOP_CONDITION",
    "INDEPENDENCE_FAMILY",
    "MAX_PAIRS_CONSIDERED",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "RefusalCode",
    "RefusalStage",
    "SyntacticExtraction",
    "SyntacticExtractor",
    "syntactic_candidate_ids",
    "syntactic_signals",
]

